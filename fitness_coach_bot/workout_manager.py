import pandas as pd
from datetime import datetime
import logging
import math
import os
import json
from fitness_coach_bot.sheets_service import GoogleSheetsService
import copy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WorkoutManager:
    def __init__(self, database=None):
        # Keep Google Sheets service for exercise data
        self.sheets_service = None
        try:
            # Check if all required env vars are present and not empty
            required_env_vars = [
                'GOOGLE_TYPE', 'GOOGLE_PROJECT_ID', 'GOOGLE_PRIVATE_KEY_ID',
                'GOOGLE_PRIVATE_KEY', 'GOOGLE_CLIENT_EMAIL', 'GOOGLE_CLIENT_ID',
                'GOOGLE_CLIENT_X509_CERT_URL'
            ]
            
            missing_vars = [var for var in required_env_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.warning(f"Missing Google API credentials: {', '.join(missing_vars)}")
                logger.warning("Will use local file or default exercises instead")
                raise ValueError("Missing required Google credentials")
            
            # Initialize sheets service only if all credentials are present
            self.sheets_service = GoogleSheetsService()
            self.spreadsheet_id = "1iWPhDOwO54ocsc4XdbgJ6ddWe7LBxWG-9oYN0fGWWws"
            self.range_name = "'ИТОГ'!A1:O"
            logger.info("Google Sheets service initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Google Sheets service: {e}")
            self.sheets_service = None
            
        self.db = database
        
        # Load exercises from Google Sheets or local file as fallback
        self._load_exercises()

        # Define level multipliers
        self.level_multipliers = {
            'начинающий': {
                'time': 0.7,
                'reps': 0.7,
                'circuits_rest': 1.25,
                'exercises_rest': 1.5,
                'circuits': 1.0
            },
            'средний': {
                'time': 1.0,
                'reps': 1.0,
                'circuits_rest': 1.0,
                'exercises_rest': 1.0,
                'circuits': 1.0
            },
            'продвинутый': {
                'time': 1.3,
                'reps': 1.3,
                'circuits_rest': 0.75,
                'exercises_rest': 0.75,
                'circuits': 1.0
            }
        }

        # Define feedback adaptation multipliers
        self.physical_state_multipliers = {
            'tired': {
                'reps': 0.8,
                'time': 0.8,
                'weight': 0.85,
                'sets': -1,  # Reduce by 1
                'rest': 1.3  # Increase rest time by 30%
            },
            'ok': {
                'reps': 1.0,
                'time': 1.0,
                'weight': 1.0,
                'sets': 0,   # No change
                'rest': 1.0  # No change
            },
            'too_easy': {
                'reps': 1.2,
                'time': 1.2,
                'weight': 1.15,
                'sets': 1,   # Increase by 1
                'rest': 0.8  # Decrease rest time by 20%
            }
        }

        # Define workout structures based on goals for bodyweight exercises
        self.bodyweight_structures = {
            'похудение': {
                'разминка': 2,
                'ноги': 2,
                'пресс': 2,
                'ягодицы': 1,
                'спина': 1,
                'руки': 2,
                'заминка': 2
            },
            'набор мышечной массы': {
                'разминка': 3,
                'ноги': 2,
                'пресс': 2,
                'ягодицы': 1,
                'плечи': 1,
                'спина': 2,
                'руки': 2,
                'заминка': 2
            },
            'общая физическая подготовка': {
                'разминка': 3,
                'ноги': 2,
                'пресс': 2,
                'ягодицы': 1,
                'плечи': 1,
                'спина': 2,
                'руки': 2,
                'заминка': 2
            }
        }

        # Define multipliers and modifiers for different goals
        self.goal_multipliers = {
            'набор мышечной массы': {
                'reps': 0.8,
                'weight': 1.2,
                'sets': -1,  # subtract 1 from base
                'sets_rest': 1.5
            },
            'общая физическая подготовка': {
                'reps': 1.0,
                'weight': 1.0,
                'sets': 0,  # no change
                'sets_rest': 1.0
            },
            'похудение': {
                'reps': 1.5,
                'weight': 0.7,
                'sets': 1,  # add 1 to base
                'sets_rest': 2/3  # approximately 0.67
            }
        }

        # Define level multipliers for weight
        self.level_weight_multipliers = {
            'продвинутый': 1.3,
            'средний': 1.0,
            'начинающий': 0.6
        }

        # Define gender multipliers for weight
        self.gender_weight_multipliers = {
            'мужской': 1.0,
            'женский': 0.6
        }

        # Define gym workout structure
        self.gym_workout_structure = {
            'разминка': 1,
            'грудь': 1,
            'спина': 1,
            'плечи': 1,
            'квадрицепс': 1,
            'задняя поверхность ног': 1,
            'бицепс': 1,
            'трицепс': 1,
            'пресс': 1
        }

        # Define muscle group specific workout structures
        self.muscle_group_workouts = {
            'грудь_бицепс': {
                'разминка': 1,
                'грудь': 2,
                'бицепс': 2,
                'икры': 1,
                'пресс': 1
            },
            'спина_трицепс': {
                'разминка': 1,
                'спина': 2,
                'трицепс': 2,
                'плечи': 1,
                'пресс': 1
            },
            'ноги': {
                'разминка': 1,
                'квадрицепс': 2,
                'задняя поверхность ног': 2,
                'предплечья': 1,
                'пресс': 1
            }
        }

        # Define difficulty level mappings
        self.difficulty_levels = {
            'beginner': ['начальный', 'средний'],
            'intermediate': ['средний', 'продвинутый'],
            'advanced': ['продвинутый', 'средний']
        }

        # Define alternative muscle groups for fallbacks
        self.alternative_muscles = {
            'руки': ['руки', 'плечи', 'грудь', 'верх тела'],
            'плечи': ['плечи', 'руки', 'грудь', 'верх тела'],
            'спина': ['спина', 'верх тела', 'руки'],
            'ягодицы': ['ягодицы', 'ноги', 'пресс'],
            'пресс': ['пресс', 'корпус', 'спина'],
            'ноги': ['ноги', 'ягодицы'],
            'грудь': ['грудь', 'верх тела', 'плечи'],
            'квадрицепс': ['квадрицепс', 'ноги', 'передняя поверхность ног'],
            'задняя поверхность ног': ['задняя поверхность ног', 'ноги', 'ягодицы'],
            'бицепс': ['бицепс', 'руки', 'верх тела'],
            'трицепс': ['трицепс', 'руки', 'верх тела'],
            'разминка': ['разминка', 'кардио'],
            'заминка': ['заминка', 'растяжка', 'кардио']
        }


    def _apply_feedback_adaptations(self, user_id, exercise_data, is_gym_workout=True):
        """Apply adaptations based on user feedback"""
        if not self.db:
            return exercise_data

        # Get recent feedback analysis
        feedback = self.db.get_recent_feedback(user_id)
        physical_state = feedback.get('physical_state', 'ok')
        emotional_state = feedback.get('emotional_state', 'good')

        # Log feedback and adaptation process
        logger.info(f"Applying adaptations for user {user_id}")
        logger.info(f"User feedback - Physical: {physical_state}, Emotional: {emotional_state}")
        logger.info(f"Original exercise data: {exercise_data}")

        # Get multipliers for the current physical state
        multipliers = self.physical_state_multipliers.get(physical_state, 
                                                        self.physical_state_multipliers['ok'])
        logger.info(f"Using adaptation multipliers: {multipliers}")

        # Apply adaptations based on physical state
        if is_gym_workout:
            # Adjust gym workout parameters
            if 'reps' in exercise_data:
                old_reps = exercise_data['reps']
                exercise_data['reps'] = max(1, round(exercise_data['reps'] * multipliers['reps']))
                logger.info(f"Adjusted reps: {old_reps} -> {exercise_data['reps']}")

            if 'weight' in exercise_data:
                old_weight = exercise_data['weight']
                exercise_data['weight'] = max(0, round(exercise_data['weight'] * multipliers['weight']))
                logger.info(f"Adjusted weight: {old_weight} -> {exercise_data['weight']}")

            if 'sets' in exercise_data:
                old_sets = exercise_data['sets']
                exercise_data['sets'] = max(1, exercise_data['sets'] + multipliers['sets'])
                logger.info(f"Adjusted sets: {old_sets} -> {exercise_data['sets']}")

            if 'sets_rest' in exercise_data:
                old_rest = exercise_data['sets_rest']
                exercise_data['sets_rest'] = max(30, round(exercise_data['sets_rest'] * multipliers['rest']))
                logger.info(f"Adjusted rest time: {old_rest} -> {exercise_data['sets_rest']}")
        else:
            # Adjust bodyweight workout parameters
            if 'time' in exercise_data:
                old_time = exercise_data['time']
                exercise_data['time'] = max(10, round(exercise_data['time'] * multipliers['time']))
                logger.info(f"Adjusted time: {old_time} -> {exercise_data['time']}")

            if 'reps' in exercise_data:
                old_reps = exercise_data['reps']
                exercise_data['reps'] = max(1, round(exercise_data['reps'] * multipliers['reps']))
                logger.info(f"Adjusted reps: {old_reps} -> {exercise_data['reps']}")

            if 'exercises_rest' in exercise_data:
                old_rest = exercise_data['exercises_rest']
                exercise_data['exercises_rest'] = max(15, round(exercise_data['exercises_rest'] * multipliers['rest']))
                logger.info(f"Adjusted rest time: {old_rest} -> {exercise_data['exercises_rest']}")

        logger.info(f"Final adapted exercise data: {exercise_data}")
        return exercise_data

    def _get_gym_workout_base(self, user_profile, allowed_difficulties):
        """Get base parameters for gym workout generation"""
        # Get goal multipliers
        goal = user_profile.get('goals', 'общая физическая подготовка').lower()
        goal_mults = self.goal_multipliers.get(goal, self.goal_multipliers['общая физическая подготовка'])

        # Get level and gender multipliers for weight
        level_weight_mult = self.level_weight_multipliers.get(
            user_profile.get('fitness_level', 'начинающий').lower(),
            self.level_weight_multipliers['начинающий']
        )
        gender_weight_mult = self.gender_weight_multipliers.get(
            user_profile.get('sex', 'мужской').lower(),
            self.gender_weight_multipliers['мужской']
        )

        # Filter exercises for gym equipment
        gym_workouts = self.exercises_df[
            (self.exercises_df['equipment'].str.lower() == 'зал') &
            (self.exercises_df['difficulty'].str.lower().isin([d.lower() for d in allowed_difficulties]))
        ]

        # For warmup, use only gym warmup exercises
        warmup_workouts = gym_workouts[gym_workouts['target_muscle'].str.lower() == 'разминка']

        if len(gym_workouts) == 0:
            logger.warning("No gym exercises found")
            return None, None, None, None

        return gym_workouts, warmup_workouts, goal_mults, (level_weight_mult, gender_weight_mult)

    def _process_gym_exercise(self, exercise, goal_mults, weight_mults):
        """Process a single gym exercise with multipliers"""
        level_weight_mult, gender_weight_mult = weight_mults
        
        # Get base values
        base_reps = self._safe_float_convert(exercise.get('base_reps', 12))
        base_weight = self._safe_float_convert(exercise.get('weight', 0))
        base_sets = self._safe_float_convert(exercise.get('sets', 3))
        base_sets_rest = self._safe_float_convert(exercise.get('base_sets_rest', 60))

        # Apply multipliers
        reps = round(base_reps * goal_mults['reps'])
        weight = round(base_weight * goal_mults['weight'] * level_weight_mult * gender_weight_mult)
        sets = max(1, round(base_sets + goal_mults['sets']))  # Ensure at least 1 set
        sets_rest = round(base_sets_rest * goal_mults['sets_rest'])

        exercise_data = {
            'name': exercise['name'],
            'target_muscle': exercise['target_muscle'],
            'difficulty': exercise.get('difficulty', ''),
            'reps': reps,
            'weight': weight,
            'sets': sets,
            'sets_rest': sets_rest,
            'current_set': 1
        }

        # Add GIF URL if available
        self._add_gif_url(exercise, exercise_data)

        return exercise_data

    def generate_gym_workout(self, user_profile, user_id=None):
        """Generate a gym workout with feedback adaptations"""
        level_map = {
            "Начинающий": "beginner",
            "Средний": "intermediate",
            "Продвинутый": "advanced"
        }

        level = level_map.get(user_profile.get('fitness_level', 'beginner'), 'beginner')
        allowed_difficulties = self.difficulty_levels[level]

        # Get base workout parameters
        base_params = self._get_gym_workout_base(user_profile, allowed_difficulties)
        if base_params[0] is None:
            return self._get_default_workout()

        gym_workouts, warmup_workouts, goal_mults, weight_mults = base_params

        exercises = []
        used_exercises = set()

        # Generate workout based on gym structure
        for muscle, count in self.gym_workout_structure.items():
            # Use appropriate workout set based on muscle group
            suitable_workouts = warmup_workouts if muscle.lower() == 'разминка' else gym_workouts

            selected_exercises = self._get_exercises_for_muscle(
                muscle, suitable_workouts, count, used_exercises
            )

            for exercise in selected_exercises:
                exercise_data = self._process_gym_exercise(exercise, goal_mults, weight_mults)
                exercises.append(exercise_data)
                used_exercises.add(exercise['name'])

        # Apply feedback adaptations to each exercise if user_id is provided
        if user_id and self.db:
            exercises = [self._apply_feedback_adaptations(user_id, ex, True) for ex in exercises]

        if not exercises:
            logger.warning("No exercises were generated for gym workout")
            return self._get_default_workout()

        logger.info(f"Generated gym workout with {len(exercises)} exercises")
        
        # Process workout for API response
        if exercises:
            # Final steps to create the workout object
            workout = {
                'exercises': exercises,
                'total_exercises': len(exercises),
                'current_exercise': 0,
                'workout_type': 'gym'
            }
            
            # Ensure correct types for storage
            return self._prepare_workout_for_storage(workout)
        else:
            return self._get_default_workout()

    def generate_muscle_group_workout(self, user_profile, muscle_group, user_id=None):
        """Generate a workout focusing on specific muscle groups"""
        level_map = {
            "Начинающий": "beginner",
            "Средний": "intermediate",
            "Продвинутый": "advanced"
        }

        level = level_map.get(user_profile.get('fitness_level', 'beginner'), 'beginner')
        allowed_difficulties = self.difficulty_levels[level]

        # Get the workout structure for the specified muscle group
        if muscle_group not in self.muscle_group_workouts:
            logger.warning(f"Invalid muscle group: {muscle_group}")
            return self._get_default_workout()

        structure = self.muscle_group_workouts[muscle_group]

        # Get base workout parameters
        base_params = self._get_gym_workout_base(user_profile, allowed_difficulties)
        if base_params[0] is None:
            return self._get_default_workout()

        gym_workouts, warmup_workouts, goal_mults, weight_mults = base_params

        exercises = []
        used_exercises = set()

        # Generate workout based on muscle group structure
        for muscle, count in structure.items():
            # Use appropriate workout set based on muscle group
            suitable_workouts = warmup_workouts if muscle.lower() == 'разминка' else gym_workouts

            selected_exercises = self._get_exercises_for_muscle(
                muscle, suitable_workouts, count, used_exercises
            )

            for exercise in selected_exercises:
                exercise_data = self._process_gym_exercise(exercise, goal_mults, weight_mults)
                exercises.append(exercise_data)
                used_exercises.add(exercise['name'])

        # Apply feedback adaptations if user_id is provided
        if user_id and self.db:
            exercises = [self._apply_feedback_adaptations(user_id, ex, True) for ex in exercises]

        if not exercises:
            logger.warning(f"No exercises were generated for muscle group: {muscle_group}")
            return self._get_default_workout()

        logger.info(f"Generated {muscle_group} workout with {len(exercises)} exercises")
        return {
            'exercises': exercises,
            'total_exercises': len(exercises),
            'current_exercise': 0,
            'workout_type': 'gym'
        }

    def _load_exercises(self):
        """Load exercises from Google Sheets with fallback to local file"""
        try:
            if self.sheets_service:
                # First try to load from Google Sheets
                logger.info("Attempting to load exercises from Google Sheets")
                data = self.sheets_service.get_sheet_data(self.spreadsheet_id, self.range_name)
                if not data:
                    raise ValueError("No data received from Google Sheets")

                # Get headers from first row
                headers = data[0]
                expected_columns = [
                    'name', 'target_muscle', 'difficulty', 'efficiency',
                    'gif', 'equipment', 'fitness_goals', 'base_time',
                    'base_reps', 'base_circuits', 'base_circuits_rest',
                    'base_exercises_rest', 'weight', 'sets', 'base_sets_rest'
                ]

                # Ensure all headers are present
                for col in expected_columns:
                    if col not in headers:
                        headers.append(col)

                # Pad rows with empty values if needed
                rows = []
                for row in data[1:]:
                    padded_row = row + [''] * (len(headers) - len(row))
                    rows.append(padded_row)

                # Create DataFrame
                self.exercises_df = pd.DataFrame(rows, columns=headers)

                # Clean up string values
                for col in ['equipment', 'target_muscle', 'difficulty']:
                    if col in self.exercises_df.columns:
                        self.exercises_df[col] = self.exercises_df[col].fillna('').astype(str).str.strip().str.lower()

                logger.info(f"Loaded {len(self.exercises_df)} exercises from Google Sheets")
                
                # Also save to local file for backup
                try:
                    exercises_file = os.path.join('fitness_coach_bot', 'data', 'exercises.json')
                    os.makedirs(os.path.dirname(exercises_file), exist_ok=True)
                    with open(exercises_file, 'w', encoding='utf-8') as f:
                        json.dump(self.exercises_df.to_dict('records'), f, ensure_ascii=False)
                    logger.info(f"Saved exercises to local file as backup: {exercises_file}")
                except Exception as e:
                    logger.warning(f"Could not save exercises to local file: {e}")
                
                return
            
            # If Google Sheets service not available, try local file
            logger.info("Google Sheets service not available, trying local file")
            raise Exception("Fallback to local file")
            
        except Exception as e:
            logger.warning(f"Error loading exercises from Google Sheets: {e}")
            
            # Try to load from local JSON file
            try:
                exercises_file = os.path.join('fitness_coach_bot', 'data', 'exercises.json')
                
                if os.path.exists(exercises_file):
                    with open(exercises_file, 'r', encoding='utf-8') as f:
                        logger.info(f"Loading exercises from local file: {exercises_file}")
                        self.exercises_df = pd.DataFrame(json.load(f))
                        logger.info(f"Loaded {len(self.exercises_df)} exercises from local file")
                        return
                        
                logger.warning(f"Local exercises file not found at {exercises_file}")
            except Exception as local_e:
                logger.error(f"Error loading exercises from local file: {local_e}")
            
            # If all else fails, use default exercises
            logger.warning("Using default exercise data as fallback")
            self.exercises_df = self._get_default_exercises()
            logger.info(f"Created {len(self.exercises_df)} default exercises")

    def _get_default_exercises(self):
        # Create a default set of exercises if we can't load from Google Sheets or local file
        default_exercises = [
            {
                "name": "Приседания", 
                "target_muscle": "ноги",
                "difficulty": "начинающий",
                "equipment": "нет",
                "type": "compound",
                "base_reps": 10,
                "base_time": 0
            },
            {
                "name": "Отжимания", 
                "target_muscle": "грудь",
                "difficulty": "начинающий",
                "equipment": "нет",
                "type": "compound",
                "base_reps": 10,
                "base_time": 0
            },
            {
                "name": "Планка", 
                "target_muscle": "пресс",
                "difficulty": "начинающий",
                "equipment": "нет",
                "type": "isolation",
                "base_reps": 0,
                "base_time": 30
            },
            {
                "name": "Скручивания", 
                "target_muscle": "пресс",
                "difficulty": "начинающий",
                "equipment": "нет",
                "type": "isolation",
                "base_reps": 15,
                "base_time": 0
            },
            {
                "name": "Выпады", 
                "target_muscle": "ноги",
                "difficulty": "средний",
                "equipment": "нет",
                "type": "compound",
                "base_reps": 12,
                "base_time": 0
            }
        ]
        return pd.DataFrame(default_exercises)

    def _safe_float_convert(self, value, default=0):
        """Safely convert value to float"""
        if pd.isna(value) or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _get_exercises_for_muscle(self, muscle, suitable_workouts, count, used_exercises=None):
        """Get exercises for a specific muscle group with fallback options"""
        if used_exercises is None:
            used_exercises = set()

        # Try exact match first
        muscle_exercises = suitable_workouts[
            suitable_workouts['target_muscle'].str.lower() == muscle.lower()
        ]

        # If no exercises found or not enough, try alternative muscle groups
        if len(muscle_exercises) < count and muscle.lower() in self.alternative_muscles:
            alternative_muscles = self.alternative_muscles[muscle.lower()]
            additional_exercises = suitable_workouts[
                (suitable_workouts['target_muscle'].str.lower().isin(alternative_muscles)) &
                (~suitable_workouts.index.isin(muscle_exercises.index))
            ]
            muscle_exercises = pd.concat([muscle_exercises, additional_exercises])

        # Remove already used exercises
        muscle_exercises = muscle_exercises[~muscle_exercises['name'].isin(used_exercises)]

        if len(muscle_exercises) == 0:
            logger.warning(f"No exercises found for muscle group: {muscle}")
            return []

        # Select required number of exercises, up to what's available
        available_count = len(muscle_exercises)
        if available_count < count:
            logger.warning(f"Only {available_count} exercises available for {muscle}, requested {count}")

        selected = muscle_exercises.sample(n=min(count, available_count))
        return selected.to_dict('records')

    def _get_default_workout(self):
        """Return default workout if no suitable workout found"""
        return {
            'exercises': [
                {
                    'name': 'Приседания',
                    'target_muscle': 'ноги',
                    'reps': 15,
                    'sets': 3,
                    'sets_rest': 60,
                    'current_set': 1,
                    'weight': 0
                }
            ],
            'total_exercises': 1,
            'current_exercise': 0,
            'workout_type': 'gym'
        }

    def generate_bodyweight_workout(self, user_profile, user_id=None):
        """Generate a bodyweight workout with feedback adaptations"""
        level = user_profile.get('fitness_level', 'начинающий').lower()
        goal = user_profile.get('goals', 'общая физическая подготовка').lower()

        # Get level multipliers
        level_mults = self.level_multipliers.get(level, self.level_multipliers['начинающий'])

        # Get workout structure based on goal
        structure = self.bodyweight_structures.get(goal, self.bodyweight_structures['общая физическая подготовка'])

        # Filter exercises for bodyweight only
        bodyweight_workouts = self.exercises_df[self.exercises_df['equipment'].str.lower() == 'нет']

        if len(bodyweight_workouts) == 0:
            logger.warning("No bodyweight exercises found")
            return self._get_default_workout()

        exercises = []
        used_exercises = set()

        # Generate workout based on structure
        for muscle, count in structure.items():
            selected_exercises = self._get_exercises_for_muscle(
                muscle, bodyweight_workouts, count, used_exercises
            )

            for exercise in selected_exercises:
                base_time = self._safe_float_convert(exercise.get('base_time', 0))
                base_reps = self._safe_float_convert(exercise.get('base_reps', 0))
                base_circuits = self._safe_float_convert(exercise.get('base_circuits', 2))
                base_exercises_rest = self._safe_float_convert(exercise.get('base_exercises_rest', 30))

                # Apply multipliers
                time = round(base_time * level_mults['time']) if base_time > 0 else 0
                reps = round(base_reps * level_mults['reps']) if base_reps > 0 else 0
                circuits = round(base_circuits * level_mults['circuits'])
                exercises_rest = round(base_exercises_rest * level_mults['exercises_rest'])

                exercise_data = {
                    'name': exercise['name'],
                    'target_muscle': exercise['target_muscle'],
                    'difficulty': exercise.get('difficulty', ''),
                    'time': time,
                    'reps': reps,
                    'circuits': circuits,
                    'exercises_rest': exercises_rest,
                    'current_circuit': 1
                }

                # Add GIF URL if available
                self._add_gif_url(exercise, exercise_data)

                exercises.append(exercise_data)
                used_exercises.add(exercise['name'])

        # Apply feedback adaptations to each exercise if user_id is provided
        if user_id and self.db:
            exercises = [self._apply_feedback_adaptations(user_id, ex, False) for ex in exercises]

        if not exercises:
            logger.warning("No exercises were generated for bodyweight workout")
            return self._get_default_workout()

        # Calculate workout level circuits rest based on the level multiplier
        base_circuits_rest = 60  # Base value for circuits rest
        circuits_rest = round(base_circuits_rest * level_mults['circuits_rest'])

        # If user is tired, increase rest time
        if user_id and self.db:
            feedback = self.db.get_recent_feedback(user_id)
            if feedback.get('physical_state') == 'tired':
                circuits_rest = round(circuits_rest * self.physical_state_multipliers['tired']['rest'])

        logger.info(f"Generated bodyweight workout with {len(exercises)} exercises")
        
        # Create final workout object
        workout = {
            'exercises': exercises,
            'workout_name': f"{goal.title()} тренировка",
            'total_exercises': len(exercises),
            'current_exercise': 0,
            'current_circuit': 1,
            'circuits_rest': circuits_rest,
            'workout_type': 'bodyweight'
        }
        
        # Ensure correct types for storage
        return self._prepare_workout_for_storage(workout)

    def _add_gif_url(self, source_exercise, target_exercise):
        """Add GIF URL to exercise data if available"""
        gif_url = source_exercise.get('gif', '')
        if pd.notna(gif_url) and isinstance(gif_url, str):
            gif_url = gif_url.strip()
            if gif_url and (gif_url.startswith('http://') or gif_url.startswith('https://')):
                target_exercise['gif_url'] = gif_url

    def _generate_gym_overview(self, workout):
        """Generate detailed overview for gym workout"""
        overview = "🏋️‍♂️ Ваша программа тренировок в зале:\n\n"

        # Group exercises by muscle
        muscle_groups = {}
        for exercise in workout['exercises']:
            muscle = exercise['target_muscle']
            if muscle not in muscle_groups:
                muscle_groups[muscle] = []
            muscle_groups[muscle].append(exercise)

        # Build overview
        for muscle, exercises in muscle_groups.items():
            overview += f"\n💪 {muscle.title()}:\n"
            for ex in exercises:
                overview += f"• {ex['name']}\n"
                overview += f"  📊 {ex['reps']} повторений x {ex['sets']} подходов\n"
                if ex.get('weight', 0) > 0:
                    overview += f"  🏋️ Вес: {ex['weight']} кг\n"
                overview += f"  ⏰ Отдых: {ex['sets_rest']} сек\n\n"

        return overview

    def _generate_bodyweight_overview(self, workout, goal):
        """Generate detailed overview of bodyweight workout"""
        overview = "🏃‍♂️ Программа тренировки с собственным весом:\n\n"
        overview += f"🎯 Цель тренировки: {goal.title()}\n\n"

        # Group exercises by muscle
        muscle_groups = {}
        for exercise in workout['exercises']:
            muscle = exercise['target_muscle']
            if muscle not in muscle_groups:
                muscle_groups[muscle] = []
            muscle_groups[muscle].append(exercise)

        # Build overview
        for muscle, exercises in muscle_groups.items():
            overview += f"\n💪 {muscle.title()}:\n"
            for ex in exercises:
                overview += f"• {ex['name']}\n"
                if ex.get('time', 0) > 0:
                    overview += f"  ⏱ {ex['time']} сек"
                elif ex.get('reps', 0) > 0:
                    overview += f"  📊 {ex['reps']} повторений"
                overview += f" x {ex['circuits']} кругов\n"
                overview += f"  ⏰ Отдых: {ex['exercises_rest']} сек\n\n"

        return overview

    def _prepare_workout_for_storage(self, workout):
        """Convert workout values for storage (e.g., convert to Decimal for DynamoDB)"""
        # Make a deep copy to avoid modifying the original
        storage_workout = copy.deepcopy(workout)
        
        # Ensure numeric values are properly formatted as integers
        if 'circuits_rest' in storage_workout:
            storage_workout['circuits_rest'] = int(storage_workout['circuits_rest'])
        
        if 'total_exercises' in storage_workout:
            storage_workout['total_exercises'] = int(storage_workout['total_exercises'])
        
        # Process each exercise
        for exercise in storage_workout.get('exercises', []):
            if 'time' in exercise:
                exercise['time'] = int(exercise['time'])
            if 'reps' in exercise:
                exercise['reps'] = int(exercise['reps'])
            if 'sets' in exercise:
                exercise['sets'] = int(exercise['sets'])
            if 'circuits' in exercise:
                exercise['circuits'] = int(exercise['circuits'])
            if 'exercises_rest' in exercise:
                exercise['exercises_rest'] = int(exercise['exercises_rest'])
            if 'current_set' in exercise:
                exercise['current_set'] = int(exercise['current_set'])
        
        return storage_workout