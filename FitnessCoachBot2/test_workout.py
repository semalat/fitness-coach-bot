from workout_manager import WorkoutManager
from database import Database
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_workout_generation():
    # Initialize database and workout manager
    database = Database()
    manager = WorkoutManager(database=database)

    # Test cases for different profiles
    test_profiles = [
        {
            'fitness_level': 'Начинающий',
            'goals': 'Набор мышечной массы',
            'equipment': 'Доступ в спортзал'
        },
        {
            'fitness_level': 'Продвинутый',
            'goals': 'Набор мышечной массы',
            'equipment': 'Доступ в спортзал'
        },
        {
            'fitness_level': 'Средний',
            'goals': 'Общая физическая подготовка',
            'equipment': 'Доступ в спортзал'
        }
    ]

    expected_muscle_groups = {
        'разминка': 1,
        'грудь': 2,
        'спина': 2,
        'плечи': 1,
        'квадрицепс': 2,
        'задняя поверхность ног': 2,
        'бицепс': 1,
        'трицепс': 1,
        'пресс': 1
    }

    # Test workout generation with feedback adaptations
    test_user_id = "test_user_123"
    test_workout_id = "test_workout_1"

    # Test different feedback scenarios
    feedback_scenarios = [
        {
            'emotional_state': 'not_fun',
            'physical_state': 'tired'
        },
        {
            'emotional_state': 'fun',
            'physical_state': 'too_easy'
        },
        {
            'emotional_state': 'fun',
            'physical_state': 'ok'
        }
    ]

    for profile in test_profiles:
        logger.info(f"\nTesting profile: {profile}")

        # Test base workout generation
        workout = manager.generate_gym_workout(profile)
        logger.info(f"Generated base workout with {len(workout['exercises'])} exercises")

        # Test workouts with different feedback scenarios
        for feedback in feedback_scenarios:
            # Save test feedback
            database.save_workout_feedback(test_user_id, test_workout_id, feedback)

            # Generate workout with feedback adaptations
            adapted_workout = manager.generate_gym_workout(profile, test_user_id)
            logger.info(f"\nTesting adaptations for feedback: {feedback}")
            logger.info(f"Generated adapted workout with {len(adapted_workout['exercises'])} exercises")

            # Group exercises by target muscle
            muscle_groups = {}
            for exercise in adapted_workout['exercises']:
                target = exercise['target_muscle'].lower()
                if target not in muscle_groups:
                    muscle_groups[target] = []
                muscle_groups[target].append(exercise)

            # Print exercise distribution
            logger.info("\nExercise distribution by muscle group:")
            for muscle, exercises in muscle_groups.items():
                logger.info(f"{muscle}: {len(exercises)} exercises")
                # Verify the number of exercises matches expected structure
                if muscle in expected_muscle_groups:
                    expected = expected_muscle_groups[muscle]
                    actual = len(exercises)
                    logger.info(f"Expected {expected} exercises for {muscle}, got {actual}")
                    assert actual <= expected, f"Too many exercises for {muscle}"

            # Print sample exercises with their adjusted values
            logger.info("\nSample exercises with adaptations:")
            for exercise in adapted_workout['exercises'][:3]:
                logger.info(f"\nExercise: {exercise['name']}")
                logger.info(f"Target: {exercise['target_muscle']}")
                if 'difficulty' in exercise:
                    logger.info(f"Difficulty: {exercise['difficulty']}")
                if 'reps' in exercise:
                    logger.info(f"Reps: {exercise['reps']}")
                if 'sets' in exercise:
                    logger.info(f"Sets: {exercise['sets']}")
                if 'sets_rest' in exercise:
                    logger.info(f"Sets Rest: {exercise['sets_rest']} seconds")
                if 'weight' in exercise:
                    logger.info(f"Weight: {exercise['weight']} kg")

if __name__ == "__main__":
    test_workout_generation()