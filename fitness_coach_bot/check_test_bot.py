#!/usr/bin/env python3
import os
import sys
import requests
from dotenv import load_dotenv
from pathlib import Path

def main():
    """
    Check if the test bot is running by making a getMe request to the Telegram API
    """
    # Load the test environment variables
    env_test_path = Path(__file__).parent / '.env.test'
    if env_test_path.exists():
        load_dotenv(env_test_path)
        print(f"Loaded test environment from {env_test_path}")
    else:
        print(f"Error: Test environment file not found at {env_test_path}")
        sys.exit(1)
    
    # Get the test bot token
    test_token = os.getenv('TELEGRAM_BOT_TOKEN_TEST')
    if not test_token:
        print("Error: Test bot token not found in .env.test file")
        sys.exit(1)
    
    # Make a getMe request to check if the bot is responsive
    url = f"https://api.telegram.org/bot{test_token}/getMe"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        bot_info = response.json()
        
        if bot_info.get('ok'):
            bot_data = bot_info.get('result', {})
            print("Test bot is running!")
            print(f"Bot username: @{bot_data.get('username')}")
            print(f"Bot name: {bot_data.get('first_name')}")
            print(f"Bot ID: {bot_data.get('id')}")
        else:
            print(f"Bot check failed: {bot_info.get('description')}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Telegram API: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 