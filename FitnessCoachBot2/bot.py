import sys
import os
import signal
from pathlib import Path
from telegram.error import Conflict, NetworkError, TimedOut
import logging
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

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal, cleaning up...")
    if application:
        try:
            application.stop()
            logger.info("Application stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping application: {e}")
    sys.exit(0)

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

def cleanup_old_instances():
    """Attempt to clean up any existing bot instances"""
    pid_file = '/tmp/telegram_bot.pid'
    try:
        # Check if PID file exists and process is running
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to old instance with PID {old_pid}")
                    # Wait a bit to ensure the process is terminated
                    import time
                    time.sleep(2)
                except ProcessLookupError:
                    logger.info(f"No process found with PID {old_pid}")
                except Exception as e:
                    logger.error(f"Error killing old process: {e}")

                # Remove the old PID file
                try:
                    os.remove(pid_file)
                    logger.info("Removed old PID file")
                except Exception as e:
                    logger.error(f"Error removing PID file: {e}")

    except Exception as e:
        logger.error(f"Error in cleanup: {e}")

    # Save current PID
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"Saved current PID {os.getpid()} to file")
    except Exception as e:
        logger.error(f"Error saving PID: {e}")

def main():
    """Initialize and start the bot"""
    global application

    if not TOKEN:
        logger.error("Error: Telegram Bot Token not found. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    try:
        # Clean up old instances first
        cleanup_old_instances()

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Initialize components
        logger.info("Initializing bot components...")

        database = Database()
        logger.info("Database initialized")

        # Initialize WorkoutManager with database reference
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
            stop_signals=(signal.SIGINT, signal.SIGTERM)
        )

    except Conflict as e:
        logger.error(f"Bot instance conflict: {e}")
        logger.info("Attempting to restart after conflict...")
        # Wait a bit before trying to restart
        import time
        time.sleep(5)
        main()  # Recursive restart

    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        # Cleanup on error
        if application:
            try:
                application.stop()
            except Exception as stop_error:
                logger.error(f"Error stopping application: {stop_error}")
        raise

if __name__ == '__main__':
    main()