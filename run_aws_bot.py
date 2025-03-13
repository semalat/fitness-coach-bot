#!/usr/bin/env python3
import os
import sys
import logging
# Add python-dotenv to load .env file
from dotenv import load_dotenv

# Load .env file before importing other modules
load_dotenv(os.path.join(os.path.dirname(__file__), "fitness_coach_bot", ".env"))

# Set token directly in environment variables to ensure it's available
# Read token value directly from .env file if not already set
if not os.environ.get('TELEGRAM_BOT_TOKEN'):
    # Set the token directly from the value in .env file
    os.environ['TELEGRAM_BOT_TOKEN'] = "7477466593:AAGLQJFvjdV9keUQ7Jupn_0vCi3TQTXC-S8"
    
from fitness_coach_bot.database import Database
from fitness_coach_bot.bot import main as run_bot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # Check if we need to migrate data
    if len(sys.argv) > 1 and sys.argv[1] == '--migrate':
        logger.info("Starting data migration to DynamoDB...")
        db = Database(use_dynamo=True)
        db.migrate_data_to_dynamo()
        logger.info("Migration completed!")
        return
    
    # Make sure to use DynamoDB in the bot
    os.environ['USE_DYNAMO_DB'] = 'True'
    
    # Start the bot with DynamoDB storage
    logger.info("Starting the bot with DynamoDB storage...")
    run_bot()

if __name__ == "__main__":
    main() 