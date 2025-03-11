#!/usr/bin/env python3
"""
Testing version of the Fitness Coach Bot
"""
import os
import sys
import logging
from fitness_coach_bot.bot import main

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_test_bot():
    """Run the bot with test configuration"""
    # Check if test token is provided
    if len(sys.argv) > 1:
        test_token = sys.argv[1]
    else:
        test_token = os.environ.get("TEST_BOT_TOKEN")
        
    if not test_token:
        logger.error("No test token provided. Please set TEST_BOT_TOKEN environment variable or provide as argument")
        print("Usage: python test_bot.py <TEST_BOT_TOKEN>")
        return
        
    # Set the token environment variable
    os.environ["TELEGRAM_BOT_TOKEN"] = test_token
    
    # Add a prefix to database files to avoid conflicts with production
    os.environ["DB_PREFIX"] = "test_"
    
    print(f"Starting test bot with token: {test_token[:5]}...{test_token[-5:]}")
    
    # Run the main bot code
    main()

if __name__ == "__main__":
    run_test_bot() 