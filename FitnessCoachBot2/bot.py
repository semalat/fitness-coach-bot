import sys
import os
import signal
import fcntl
from pathlib import Path
from telegram.error import Conflict, NetworkError, TimedOut
import logging
import time
from telegram.ext import ApplicationBuilder, Application
from config import TOKEN, COMMANDS
from database import Database
from workout_manager import WorkoutManager
from reminder import ReminderManager
from handlers import BotHandlers

# Set up logging with more detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)
application = None  # Global application instance
PID_FILE = '/tmp/telegram_bot.pid'
LOCK_FILE = '/tmp/telegram_bot.lock'

# Add context manager for lock file
class LockManager:
    def __init__(self, lock_file):
        self.lock_file = lock_file
        self.lock_fd = None

    def __enter__(self):
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
        if self.lock_fd is not None:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)
                os.unlink(self.lock_file)
            except (IOError, OSError) as e:
                logger.error(f"Error releasing lock: {e}")

def acquire_lock():
    """Try to acquire the lock file"""
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (IOError, OSError) as e:
        logger.error(f"Could not acquire lock: {e}")
        return None

def release_lock(lock_fd):
    """Release the lock file"""
    if lock_fd is not None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            if os.path.exists(LOCK_FILE):
                os.unlink(LOCK_FILE)
                logger.info("Lock file released and removed")
        except (IOError, OSError) as e:
            logger.error(f"Error releasing lock: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received shutdown signal {signum}, cleaning up...")
    if application:
        try:
            application.stop()
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

    if not TOKEN:
        logger.error("Error: Telegram Bot Token not found. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    try:
        # Clean up old instances first
        if not cleanup_old_instances():
            logger.error("Could not clean up old instances. Exiting.")
            return

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)  # Handle terminal window close

        logger.info("Initializing bot components...")

        database = Database()
        logger.info("Database initialized")

        workout_manager = WorkoutManager(database=database)
        logger.info("Workout manager initialized")

        # Create application with proper configuration
        application = (
            ApplicationBuilder()
            .token(TOKEN)
            .concurrent_updates(False)  # Disable concurrent updates to prevent conflicts
            .connect_timeout(30)  # Increase timeout
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(30)
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

        # Start the bot with more robust configuration
        logger.info("Starting bot...")
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        )

    except Conflict as e:
        logger.error(f"Bot instance conflict: {e}")
        cleanup_files()
        logger.info("Exiting due to conflict...")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        # Cleanup on error
        if application:
            try:
                application.stop()
            except Exception as stop_error:
                logger.error(f"Error stopping application: {stop_error}")
        cleanup_files()
        raise

if __name__ == '__main__':
    try:
        main()
    finally:
        # Ensure cleanup happens even if main crashes
        cleanup_files()