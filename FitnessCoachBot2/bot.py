import sys
import os
import signal
from pathlib import Path
from telegram.error import Conflict
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
        application.stop()
    sys.exit(0)

async def setup_commands(application: Application) -> None:
    """Set up bot commands."""
    await application.bot.set_my_commands([
        (command, description) for command, description in COMMANDS.items()
    ])
    logger.info("Bot commands set up successfully")

def cleanup_old_instances():
    """Attempt to clean up any existing bot instances"""
    try:
        # Try to send a stop signal to potentially running instances
        with open('/tmp/telegram_bot.pid', 'r') as f:
            old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to old instance with PID {old_pid}")
            except ProcessLookupError:
                pass  # Process already gone
    except FileNotFoundError:
        pass  # No previous instance found

    # Save current PID
    with open('/tmp/telegram_bot.pid', 'w') as f:
        f.write(str(os.getpid()))

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

        # Create application
        application = (
            ApplicationBuilder()
            .token(TOKEN)
            .concurrent_updates(False)  # Disable concurrent updates
            .build()
        )
        logger.info("Application builder initialized")

        # Initialize reminder manager with bot instance
        reminder_manager = ReminderManager(application.bot, database)
        logger.info("Reminder manager initialized")

        # Initialize handlers
        handlers = BotHandlers(database, workout_manager, reminder_manager)
        logger.info("Bot handlers initialized")

        # Add handlers to application
        handlers.register_handlers(application)  # Use the new register_handlers method
        logger.info("All handlers added to application")

        # Set up commands
        application.job_queue.run_once(setup_commands, when=0)

        # Start the bot
        logger.info("Starting bot...")
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            close_loop=False
        )

    except Conflict as e:
        logger.error(f"Bot instance conflict: {e}")
        logger.info("Attempting to restart after conflict...")
        # Wait a bit before trying to restart
        import time
        time.sleep(5)
        main()  # Recursive restart

    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        # Cleanup on error
        if application:
            application.stop()
        raise

if __name__ == '__main__':
    main()