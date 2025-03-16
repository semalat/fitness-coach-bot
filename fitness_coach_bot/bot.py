import sys
import os
import signal
import platform
from pathlib import Path
from dotenv import load_dotenv
from telegram.error import Conflict, NetworkError, TimedOut
import logging
import time
from telegram.ext import ApplicationBuilder, Application, PicklePersistence
from fitness_coach_bot.config import TOKEN, COMMANDS
from fitness_coach_bot.database import Database
from fitness_coach_bot.workout_manager import WorkoutManager
from fitness_coach_bot.reminder import ReminderManager
from fitness_coach_bot.handlers import BotHandlers

# Check platform
IS_WINDOWS = platform.system() == 'Windows'

# Platform-specific imports
if not IS_WINDOWS:
    import fcntl

# Set up logging with more detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def load_environment():
    """Load environment variables from .env file"""
    env_paths = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.getcwd(), 'fitness_coach_bot', '.env'),
        '/home/ec2-user/fitness-coach-bot/fitness_coach_bot/.env'
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            logger.info(f"Loading environment from: {env_path}")
            load_dotenv(env_path)
            return True
    
    logger.error("No .env file found in any of the expected locations")
    return False

if not load_environment():
    logger.error("Failed to load environment variables")
    # Don't exit here, this prevents testing
    # Instead, we'll check this condition in main()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
else:
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

application = None  # Global application instance

# Use platform-specific temp directory for pid files
if IS_WINDOWS:
    temp_dir = os.environ.get('TEMP', os.path.join(os.environ.get('USERPROFILE', 'C:'), 'Temp'))
else:
    temp_dir = '/tmp'

PID_FILE = os.path.join(temp_dir, 'telegram_bot.pid')
LOCK_FILE = os.path.join(temp_dir, 'telegram_bot.lock')

# Add context manager for lock file
class LockManager:
    def __init__(self, lock_file):
        self.lock_file = lock_file
        self.lock_fd = None
        self.locked = False

    def __enter__(self):
        if IS_WINDOWS:
            try:
                # Windows lock implementation using fileExists check
                if os.path.exists(self.lock_file):
                    # Check if the process is still running
                    try:
                        with open(self.lock_file, 'r') as f:
                            pid = int(f.read().strip())
                        
                        # Try to check if process exists (Windows approach)
                        import ctypes
                        kernel32 = ctypes.windll.kernel32
                        handle = kernel32.OpenProcess(1, 0, pid)
                        if handle:
                            kernel32.CloseHandle(handle)
                            logger.error(f"Process with PID {pid} still running")
                            return None
                    except (IOError, ValueError, OSError):
                        # If we can't read the PID or the process doesn't exist
                        pass
                
                # Create new lock file
                with open(self.lock_file, 'w') as f:
                    f.write(str(os.getpid()))
                self.locked = True
                return True
            except Exception as e:
                logger.error(f"Windows lock error: {e}")
                return None
        else:
            # Unix implementation using fcntl
            try:
                self.lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self.lock_fd
            except (IOError, OSError) as e:
                logger.error(f"Could not acquire lock: {e}")
                if self.lock_fd:
                    os.close(self.lock_fd)
                return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if IS_WINDOWS:
            if self.locked:
                try:
                    if os.path.exists(self.lock_file):
                        os.remove(self.lock_file)
                except (IOError, OSError) as e:
                    logger.error(f"Error releasing Windows lock: {e}")
        else:
            if self.lock_fd is not None:
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                    os.close(self.lock_fd)
                    os.unlink(self.lock_file)
                except (IOError, OSError) as e:
                    logger.error(f"Error releasing lock: {e}")

def acquire_lock():
    """Try to acquire the lock file"""
    if IS_WINDOWS:
        try:
            # Windows implementation
            if os.path.exists(LOCK_FILE):
                return None
            with open(LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except (IOError, OSError) as e:
            logger.error(f"Could not acquire Windows lock: {e}")
            return None
    else:
        # Unix implementation
        try:
            lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except (IOError, OSError) as e:
            logger.error(f"Could not acquire lock: {e}")
            return None

def release_lock(lock_fd):
    """Release the lock file"""
    if IS_WINDOWS:
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except (IOError, OSError) as e:
                logger.error(f"Error releasing Windows lock: {e}")
    else:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
                os.unlink(LOCK_FILE)
            except (IOError, OSError) as e:
                logger.error(f"Error releasing lock: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received shutdown signal {signum}, cleaning up...")
    if application:
        try:
            # Properly handle async stop
            import asyncio
            try:
                # Get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    # Run the coroutine to stop the application
                    loop.run_until_complete(application.stop())
                except Exception:
                    # Fallback
                    asyncio.run(application.stop())
            except Exception as e:
                logger.error(f"Error in async handling: {e}")
            logger.info("Application stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping application: {e}")

    cleanup_files()
    logger.info("Cleanup completed, exiting...")
    sys.exit(0)

def cleanup_files():
    """Clean up PID and lock files"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("Removed PID file")
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")

    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Removed lock file")
    except Exception as e:
        logger.error(f"Error removing lock file: {e}")

def cleanup_old_instances():
    """Attempt to clean up any existing bot instances"""
    try:
        # Try to acquire lock first
        with LockManager(LOCK_FILE) as lock_fd:
            if not lock_fd:
                logger.error("Another instance is already running")
                return False

            # Check if PID file exists and process is running
            if os.path.exists(PID_FILE):
                try:
                    with open(PID_FILE, 'r') as f:
                        old_pid = int(f.read().strip())
                    
                    # Platform-specific process checking
                    if IS_WINDOWS:
                        try:
                            # Windows approach to check if process exists
                            import ctypes
                            kernel32 = ctypes.windll.kernel32
                            handle = kernel32.OpenProcess(1, 0, old_pid)
                            process_exists = handle != 0
                            if handle:
                                kernel32.CloseHandle(handle)
                                
                            if process_exists:
                                # Windows approach to terminate process
                                logger.info(f"Found running instance with PID {old_pid}")
                                os.system(f"taskkill /PID {old_pid} /F")
                                logger.info(f"Sent termination signal to old instance with PID {old_pid}")
                        except Exception as e:
                            logger.error(f"Error checking/killing Windows process: {e}")
                    else:
                        # Unix approach
                        try:
                            # Check if process exists
                            os.kill(old_pid, 0)
                            # If we get here, process exists
                            logger.info(f"Found running instance with PID {old_pid}")
                            os.kill(old_pid, signal.SIGTERM)
                            logger.info(f"Sent SIGTERM to old instance with PID {old_pid}")
                            # Wait for process to terminate
                            for _ in range(5):  # Wait up to 5 seconds
                                time.sleep(1)
                                try:
                                    os.kill(old_pid, 0)
                                except ProcessLookupError:
                                    logger.info("Old instance terminated successfully")
                                    break
                            else:
                                # If process still exists after timeout, force kill
                                try:
                                    os.kill(old_pid, signal.SIGKILL)
                                    logger.info(f"Force killed old instance with PID {old_pid}")
                                except ProcessLookupError:
                                    pass
                        except ProcessLookupError:
                            logger.info(f"No process found with PID {old_pid}")
                        except Exception as e:
                            logger.error(f"Error killing old process: {e}")
                except Exception as e:
                    logger.error(f"Error reading PID file: {e}")

            # Remove old files
            cleanup_files()

            # Save current PID
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
            logger.info(f"Saved current PID {os.getpid()} to file")

            return True

    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
        cleanup_files()
        return False

async def setup_commands(application: Application) -> None:
    """Set up bot commands."""
    try:
        await application.bot.set_my_commands([
            (command, description) for command, description in COMMANDS.items()
        ])
        logger.info("Bot commands set up successfully")
    except Exception as e:
        logger.error(f"Error setting up commands: {e}")

async def error_handler(update, context):
    """Handle bot errors"""
    logger.error(f"Update {update} caused error {context.error}")

    if isinstance(context.error, Conflict):
        logger.warning("Conflict error detected, attempting cleanup...")
        cleanup_old_instances()
    elif isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("Network error detected, will retry...")
    else:
        logger.error("Unknown error occurred", exc_info=context.error)

def main():
    """Initialize and start the bot"""
    global application

    # Check environment variables were loaded
    if not TOKEN:
        logger.error("Error: Telegram Bot Token not found. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return 1

    try:
        # Clean up old instances first
        if not cleanup_old_instances():
            logger.error("Could not clean up old instances. Exiting.")
            return 1

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # SIGHUP is not available on Windows
        if not IS_WINDOWS:
            signal.signal(signal.SIGHUP, signal_handler)  # Handle terminal window close

        logger.info("Initializing bot components...")

        database = Database()
        logger.info("Database initialized")

        workout_manager = WorkoutManager(database=database)
        logger.info("Workout manager initialized")

        # Platform-specific persistence path
        persistence_path = os.path.join(temp_dir, 'telegram_bot_persistence')
        
        # Create application with proper configuration
        persistence = PicklePersistence(filepath=persistence_path)
        application = (
            ApplicationBuilder()
            .token(TOKEN)
            .concurrent_updates(False)  # Disable concurrent updates to prevent conflicts
            .connect_timeout(30)  # Increase timeout
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(30)
            .persistence(persistence)  # Enable persistence which automatically enables job queue
            .build()
        )
        logger.info("Application builder initialized")

        # Add error handler
        application.add_error_handler(error_handler)
        logger.info("Error handler added")

        # Initialize reminder manager with bot instance
        reminder_manager = ReminderManager(application.bot, database)
        logger.info("Reminder manager initialized")

        # Initialize handlers
        handlers = BotHandlers(database, workout_manager, reminder_manager)
        logger.info("Bot handlers initialized")

        # Add handlers to application
        handlers.register_handlers(application)
        logger.info("All handlers added to application")

        # Set up commands
        application.job_queue.run_once(setup_commands, when=0)

        # Define platform-specific stop signals
        if IS_WINDOWS:
            stop_signals = (signal.SIGINT, signal.SIGTERM)
        else:
            stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

        # Start the bot with more robust configuration
        logger.info("Starting bot...")
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=stop_signals
        )

    except Conflict as e:
        logger.error(f"Bot instance conflict: {e}")
        cleanup_files()
        logger.info("Exiting due to conflict...")
        return 1  # Return error code instead of sys.exit

    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        # Cleanup on error
        if application:
            try:
                # Fix the unawaited coroutine warning by handling stop properly
                import asyncio
                try:
                    # Create a new event loop if needed
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    # Run the stop coroutine
                    loop.run_until_complete(application.stop())
                except Exception:
                    # Fallback for simpler environments
                    asyncio.run(application.stop())
            except Exception as stop_error:
                logger.error(f"Error stopping application: {stop_error}")
        cleanup_files()
        return 1  # Return error code instead of sys.exit

    return 0  # Return success code

if __name__ == "__main__":
    sys.exit(main())  # Only call sys.exit when running as a script