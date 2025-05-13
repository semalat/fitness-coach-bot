#!/usr/bin/env python3
import os
import sys
import threading
import requests
import time
from dotenv import load_dotenv
from pathlib import Path
from threading import Thread

def main():
    """
    Load the test environment, set up the webhook server, and run the bot with test token
    """
    # Add the project root to sys.path for absolute imports
    project_root = str(Path(__file__).parent.parent.absolute())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Load the test environment variables
    env_test_path = Path(__file__).parent / '.env.test'
    if env_test_path.exists():
        load_dotenv(env_test_path)
        print(f"Loaded test environment from {env_test_path}")
    else:
        # Try to create a minimal .env.test file for testing
        create_test_env_file(env_test_path)
        if env_test_path.exists():
            load_dotenv(env_test_path)
            print(f"Created and loaded test environment from {env_test_path}")
        else:
            print(f"Error: Test environment file not found at {env_test_path}")
            sys.exit(1)
    
    # Set the bot token from test environment
    test_token = os.getenv('TELEGRAM_BOT_TOKEN_TEST')
    if not test_token:
        print("Error: Test bot token not found in .env.test file")
        sys.exit(1)
        
    # Replace the production token with the test token
    os.environ['TELEGRAM_BOT_TOKEN'] = test_token
    print(f"Using TEST bot token: {test_token[:5]}...")
    
    # Set a DB prefix for test data
    os.environ['DB_PREFIX'] = 'test_'
    
    # For testing payments, we need to force bot into polling mode
    # This allows the pre-checkout query to be handled correctly
    print("Starting bot in polling mode for proper payment handling")
    os.environ['USE_WEBHOOK'] = 'False'  # Force polling mode

    # Start a health check server on a separate thread to verify server is running
    from flask import Flask
    app = Flask("health_check")
    
    @app.route('/', methods=['GET'])
    def health():
        return "Health check OK", 200
    
    def run_health_server():
        app.run(host='0.0.0.0', port=8080, debug=False)
    
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("Started health check server on port 8080")
    
    # Import and run the modified main function that properly handles payments
    print("Starting test bot...")
    modified_main()

def modified_main():
    """Modified version of main() from bot.py that fixes payment processing for testing"""
    from fitness_coach_bot.bot import cleanup_old_instances, signal_handler, PID_FILE
    from fitness_coach_bot.database import Database
    from fitness_coach_bot.workout_manager import WorkoutManager
    import signal
    import os
    from telegram.ext import ApplicationBuilder, PicklePersistence
    import logging
    
    # Get logger
    logger = logging.getLogger("fitness_coach_bot.bot")
    
    # Get token
    from fitness_coach_bot.config import TOKEN
    
    try:
        # Ensure we have a valid token
        if not TOKEN:
            logger.error("No Telegram Bot Token provided in environment variables")
            return False
            
        logger.info("Starting bot...")
        
        # Clean up old instances
        cleanup_old_instances()
        
        # Write PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
            
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
            
        # Initialize bot services
        database = Database()
        workout_manager = WorkoutManager(database)
        
        # Set up persistence
        persistence_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_persistence')
        persistence = PicklePersistence(filepath=persistence_path)
        
        # Initialize application with persistent data
        application_builder = ApplicationBuilder()
        application_builder.token(TOKEN)
        application_builder.persistence(persistence)
        app = application_builder.build()
        
        # Important: Initialize ReminderManager with both app.bot and database
        from fitness_coach_bot.reminder import ReminderManager
        reminder_manager = ReminderManager(app.bot, database)
        
        # Initialize handlers - Fix: BotHandlers takes 3 arguments (plus self), not 4
        from fitness_coach_bot.handlers import BotHandlers
        handlers = BotHandlers(database, workout_manager, reminder_manager)
        
        # Register the handlers with the application
        handlers.register_handlers(app)
        
        # Important: Set up error handler
        app.add_error_handler(lambda update, context: logger.error(f"Update {update} caused error {context.error}"))
        
        # Run the bot in polling mode to properly handle payment callbacks
        app.run_polling(allowed_updates=['message', 'callback_query', 'pre_checkout_query'])
        return True
        
    except Exception as e:
        logger.error(f"Error in modified_main function: {e}", exc_info=True)
        from fitness_coach_bot.bot import cleanup_files
        cleanup_files()
        return False

def create_test_env_file(env_path):
    """Create a minimal .env.test file for webhook testing"""
    try:
        with open(env_path, 'w') as f:
            f.write("""# Test environment variables
TELEGRAM_BOT_TOKEN_TEST=your_test_bot_token
TELEGRAM_PROVIDER_TOKEN=381764678:TEST:54321
YOOMONEY_SHOP_ID=test_shop_id
YOOMONEY_API_KEY=test_api_key
WEBHOOK_PORT=5001
PUBLIC_WEBHOOK_URL=http://localhost:5001
DEBUG=True
""")
        print(f"Created test environment file at {env_path}")
        print("Please edit it to add your actual test bot token and other credentials")
    except Exception as e:
        print(f"Error creating test environment file: {e}")

if __name__ == '__main__':
    main() 