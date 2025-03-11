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
    try:
        main()
    except Exception as e:
        logger.error(f"Error running test bot: {e}", exc_info=True)

if __name__ == "__main__":
    # Add the current directory to PYTHONPATH
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    
    # Run the test bot
    run_test_bot() 