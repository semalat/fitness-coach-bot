#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Mock the Google Sheets service before importing any other modules
class MockGoogleSheetsService:
    def __init__(self):
        print("Using Mock Google Sheets Service")
    
    def create_workout(self, user_id, profile_data):
        print(f"[MOCK] Creating workout for user {user_id} with profile {profile_data}")
        return {
            "exercises": [
                {"name": "Mock Push-ups", "sets": 3, "reps": 10, "description": "Mock exercise description"},
                {"name": "Mock Squats", "sets": 3, "reps": 15, "description": "Mock exercise description"},
                {"name": "Mock Plank", "sets": 2, "time": "30 seconds", "description": "Mock exercise description"}
            ],
            "warmup": ["Mock Jumping Jacks", "Mock Arm Circles"],
            "cooldown": ["Mock Stretching"],
            "duration": "30 minutes",
            "calories": "150-200"
        }
    
    def save_feedback(self, user_id, workout_data, feedback):
        print(f"[MOCK] Saving feedback for user {user_id}: {feedback}")
        return True
    
    def get_user_workouts(self, user_id):
        print(f"[MOCK] Getting workouts for user {user_id}")
        return []

def main():
    """
    Load the test environment, mock Google Sheets, and run the bot with test token
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
    
    # Mock the Google Sheets service
    import sys
    import types
    
    # Create a mock module for sheets_service
    mock_sheets = types.ModuleType('fitness_coach_bot.sheets_service')
    mock_sheets.GoogleSheetsService = MockGoogleSheetsService
    
    # Add it to sys.modules to intercept imports
    sys.modules['fitness_coach_bot.sheets_service'] = mock_sheets
    
    # Import and run the main bot function
    try:
        from fitness_coach_bot.bot import main
        main()
    except Exception as e:
        print(f"Error running bot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 