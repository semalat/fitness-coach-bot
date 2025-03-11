#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

def main():
    """
    Load the test environment and run the bot with test token
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
    
    # Import and run the main bot function
    from fitness_coach_bot.bot import main
    main()

if __name__ == '__main__':
    main() 