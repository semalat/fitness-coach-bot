#!/usr/bin/env python3
"""
Basic tests for Fitness Coach Bot
"""
import os
import sys
import pytest

# Add the project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_imports():
    """Test that all modules can be imported correctly"""
    # Import the main bot module
    from fitness_coach_bot.bot import main
    assert callable(main)
    
    # Import workout manager
    from fitness_coach_bot.workout_manager import WorkoutManager
    assert WorkoutManager is not None
    
    # Import database
    from fitness_coach_bot.database import Database
    assert Database is not None
    
    # Import handlers
    from fitness_coach_bot.handlers import BotHandlers
    assert BotHandlers is not None
    
    # Test basic functionality
    assert True, "Basic test passed" 