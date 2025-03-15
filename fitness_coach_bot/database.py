import json
from datetime import datetime, timedelta
import json
from collections import defaultdict
import logging
import os
import time
import boto3
from boto3.dynamodb.conditions import Key, Attr
import decimal
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, use_dynamo=True):
        # Check if environment variable overrides the use_dynamo parameter
        env_use_dynamo = os.getenv('USE_DYNAMO_DB')
        if env_use_dynamo is not None:
            # Convert string to boolean
            use_dynamo = env_use_dynamo.lower() in ('true', 'yes', '1')
            logger.info(f"Using DynamoDB setting from environment: {use_dynamo}")
        
        self.use_dynamo = use_dynamo
        
        if use_dynamo:
            try:
                # Initialize DynamoDB client
                self.dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                
                # Define table names
                self.users_table = self.dynamodb.Table('fitness_bot_users')
                self.workouts_table = self.dynamodb.Table('fitness_bot_active_workouts')
                self.progress_table = self.dynamodb.Table('fitness_bot_progress')
                self.feedback_table = self.dynamodb.Table('fitness_bot_feedback')
                self.reminders_table = self.dynamodb.Table('fitness_bot_reminders')
                
                logger.info("Successfully initialized DynamoDB tables")
            except Exception as e:
                logger.error(f"Failed to initialize DynamoDB: {str(e)}")
                logger.info("Falling back to file-based storage")
                self.use_dynamo = False
        
        if not self.use_dynamo:
            # Legacy file-based paths (keep for backward compatibility)
            self.users_file = 'fitness_coach_bot/users.json'
            self.active_workouts_file = 'fitness_coach_bot/active_workouts.json'
            self.progress_file = 'fitness_coach_bot/progress.json'
            self.feedback_file = 'fitness_coach_bot/feedback.json'
            self.reminders_file = 'fitness_coach_bot/reminders.json'
            
            # Ensure files exist before attempting to read
            self._ensure_files_exist()
            
            # Initialize in-memory data structures
            self.users = self._read_json(self.users_file)
            self.progress = self._read_json(self.progress_file)
            self.feedback = self._read_json(self.feedback_file)
            self.preview_workouts = {}
            
            logger.info("Using file-based storage")
    
    def _prepare_for_dynamo(self, data):
        """Convert Python types to DynamoDB compatible types"""
        try:
            if isinstance(data, dict):
                # Process dict
                result = {}
                for k, v in data.items():
                    # Handle special fields that must be strings
                    if k in ['user_id', 'progress_id', 'workout_id', 'feedback_id']:
                        result[k] = str(v)
                    # Special handling for feedback state fields
                    elif k in ['emotional_state', 'physical_state']:
                        # Ensure these are valid strings and not None
                        if v is None:
                            if k == 'emotional_state':
                                result[k] = 'neutral'
                            else:
                                result[k] = 'ok'
                        else:
                            result[k] = str(v)
                    # Special handling for known boolean fields
                    elif k in ['workout_completed', 'premium', 'is_completed', 'active', 'is_active']:
                        # Convert all boolean-like values to 0/1 Decimal
                        if isinstance(v, bool):
                            result[k] = Decimal('1') if v else Decimal('0')
                        elif isinstance(v, str) and v.lower() in ('true', 'false'):
                            result[k] = Decimal('1') if v.lower() == 'true' else Decimal('0')
                        elif v in (0, 1):
                            result[k] = Decimal(str(v))
                        else:
                            logger.warning(f"Unexpected value for boolean field {k}: {v}, converting based on truthiness")
                            result[k] = Decimal('1') if v else Decimal('0')
                    else:
                        try:
                            result[k] = self._prepare_for_dynamo(v)
                        except Exception as e:
                            logger.warning(f"Error converting field {k}: {str(e)}")
                            # Fallback to string representation
                            result[k] = str(v)
                return result
            elif isinstance(data, list):
                # Process list
                return [self._prepare_for_dynamo(item) for item in data]
            elif isinstance(data, bool):
                # Convert boolean to integer (1 or 0) for DynamoDB
                return Decimal('1') if data else Decimal('0')
            elif isinstance(data, (float, int)):
                # Convert numbers to Decimal for DynamoDB
                try:
                    return Decimal(str(data))
                except (decimal.InvalidOperation, ValueError):
                    # If conversion fails, return as string
                    logger.warning(f"Error converting number {data} to Decimal, using string instead")
                    return str(data)
            elif data == '':
                # Convert empty strings to None
                return None
            elif isinstance(data, (datetime, str)):
                # Convert datetime to string, keep strings as is
                return str(data)
            else:
                # Safely convert other types to string
                try:
                    return str(data)
                except Exception as e:
                    logger.warning(f"Error converting {type(data)} to string: {str(e)}")
                    return "Error: unconvertible data"
        except Exception as e:
            logger.error(f"Unexpected error in _prepare_for_dynamo: {str(e)}", exc_info=True)
            # Last resort fallback
            return str(data) if data is not None else None

    def save_active_workout(self, user_id, workout):
        """Save active workout to database"""
        user_id = str(user_id)
        try:
            logger.info(f"Saving active workout for user {user_id}")
            logger.info(f"Workout data: {workout}")
            if self.use_dynamo:
                workout_data = self._prepare_for_dynamo(workout)
                workout_data['user_id'] = user_id
                self.workouts_table.put_item(Item=workout_data)
            else:
                workouts = self._read_json(self.active_workouts_file)
                workouts[user_id] = workout
                self._write_json(self.active_workouts_file, workouts)
            logger.info("Active workout saved successfully")
        except Exception as e:
            logger.error(f"Error saving active workout: {str(e)}", exc_info=True)
            raise

    def start_active_workout(self, user_id, workout):
        """Start new active workout"""
        return self.save_active_workout(user_id, workout)

    def get_active_workout(self, user_id):
        """Get active workout from database"""
        user_id = str(user_id)
        try:
            if self.use_dynamo:
                response = self.workouts_table.get_item(
                    Key={'user_id': user_id}
                )
                workout = response.get('Item', {})
            else:
                workouts = self._read_json(self.active_workouts_file)
                workout = workouts.get(user_id, {})
            logger.info(f"Retrieved active workout for user {user_id}")
            logger.info(f"Workout data: {workout}")
            return workout
        except Exception as e:
            logger.error(f"Error retrieving active workout: {str(e)}", exc_info=True)
            return None

    def save_preview_workout(self, user_id, workout):
        """Save preview workout to database"""
        user_id = str(user_id)
        try:
            logger.info(f"Saving preview workout for user {user_id}")
            if 'preview_workouts' not in self.__dict__:
                self.preview_workouts = {}
            self.preview_workouts[user_id] = workout
            logger.info("Preview workout saved successfully")
        except Exception as e:
            logger.error(f"Error saving preview workout: {str(e)}", exc_info=True)
            raise

    def get_preview_workout(self, user_id):
        """Get preview workout from database"""
        user_id = str(user_id)
        try:
            if 'preview_workouts' not in self.__dict__:
                self.preview_workouts = {}
            workout = self.preview_workouts.get(user_id)
            logger.info(f"Retrieved preview workout for user {user_id}")
            return workout
        except Exception as e:
            logger.error(f"Error retrieving preview workout: {str(e)}", exc_info=True)
            return None

    def clear_preview_workout(self, user_id):
        """Clear preview workout from database"""
        user_id = str(user_id)
        if 'preview_workouts' in self.__dict__ and user_id in self.preview_workouts:
            del self.preview_workouts[user_id]

    def finish_active_workout(self, user_id):
        """Finish active workout and remove from database"""
        user_id = str(user_id)
        
        try:
            if self.use_dynamo:
                self.workouts_table.delete_item(
                    Key={'user_id': user_id}
                )
                logger.info(f"Removed active workout for user {user_id} from DynamoDB")
            else:
                workouts = self._read_json(self.active_workouts_file)
                if str(user_id) in workouts:
                    del workouts[str(user_id)]
                    self._write_json(self.active_workouts_file, workouts)
                    logger.info(f"Removed active workout for user {user_id} from file")
                else:
                    logger.info(f"No active workout found for user {user_id}")
        except Exception as e:
            logger.error(f"Error finishing active workout: {str(e)}")

    def update_active_workout(self, user_id, workout):
        """Update active workout in database"""
        return self.save_active_workout(user_id, workout)

    def save_user_profile(self, user_id, profile_data, telegram_handle=None):
        """Save user profile data with telegram handle"""
        user_id = str(user_id)
        profile_data['telegram_handle'] = telegram_handle
        profile_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Log the profile data being saved
        logger.info(f"Saving user profile - ID: {user_id}, Data: {profile_data}")

        if self.use_dynamo:
            # Prepare the data for DynamoDB
            dynamo_profile = self._prepare_for_dynamo(profile_data)
            dynamo_profile['user_id'] = user_id
            self.users_table.put_item(Item=dynamo_profile)
        else:
            users = self._read_json(self.users_file)
            users[user_id] = profile_data
            self._write_json(self.users_file, users)

    def get_user_profile(self, user_id):
        """Get user profile data"""
        user_id = str(user_id)
        if self.use_dynamo:
            try:
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                profile = response.get('Item', {})
                
                # Convert any Decimal values back to float for easier handling
                for key, value in list(profile.items()):
                    if isinstance(value, Decimal):
                        profile[key] = float(value)
            except Exception as e:
                logger.error(f"Error retrieving user profile from DynamoDB: {str(e)}")
                profile = {}
        else:
            users = self._read_json(self.users_file)
            profile = users.get(user_id, {})

        # Log the retrieved profile
        logger.info(f"Retrieved user profile - ID: {user_id}, Profile: {profile}")

        return profile

    def save_workout_progress(self, user_id, workout_data):
        """Save workout progress to database"""
        user_id = str(user_id)  # Ensure user_id is string
        
        try:
            # Create a copy of workout data to avoid modifying the original
            workout_data = workout_data.copy()
            
            # Add timestamp if not present
            if 'date' not in workout_data:
                workout_data['date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Ensure user_id is string in workout_data
            workout_data['user_id'] = str(workout_data.get('user_id', user_id))
            
            # Add a unique progress_id for DynamoDB if not present
            if 'progress_id' not in workout_data:
                workout_data['progress_id'] = f"{user_id}_{workout_data.get('workout_id', datetime.now().strftime('%Y%m%d_%H%M%S'))}"
            
            # Sanitize/validate all fields to prevent conversion errors
            # These are the fields we expect in a progress record
            for field in ['exercises_completed', 'total_exercises']:
                if field in workout_data:
                    try:
                        workout_data[field] = int(workout_data[field])
                    except (ValueError, TypeError):
                        workout_data[field] = 0
            
            # Ensure boolean fields are properly formatted
            if 'workout_completed' in workout_data:
                workout_data['workout_completed'] = bool(workout_data['workout_completed'])
            
            if self.use_dynamo:
                try:
                    # Prepare data for DynamoDB
                    dynamo_data = self._prepare_for_dynamo(workout_data)
                    
                    # Ensure critical fields are strings
                    dynamo_data['user_id'] = str(dynamo_data['user_id'])
                    dynamo_data['progress_id'] = str(dynamo_data['progress_id'])
                    
                    # Save to DynamoDB
                    self.progress_table.put_item(Item=dynamo_data)
                    logger.info(f"Saved workout progress for user {user_id} to DynamoDB")
                except Exception as e:
                    logger.error(f"Error saving to DynamoDB: {str(e)}", exc_info=True)
                    # Fallback to file storage
                    logger.info("Falling back to file storage for progress")
                    self._save_progress_to_file(user_id, workout_data)
            else:
                self._save_progress_to_file(user_id, workout_data)
                
        except Exception as e:
            logger.error(f"Error saving workout progress: {str(e)}", exc_info=True)
            raise
    
    def _save_progress_to_file(self, user_id, workout_data):
        """Helper method to save progress to file"""
        try:
            # Load existing progress
            if not hasattr(self, 'progress'):
                self.progress = self._read_json(self.progress_file)
            
            # Initialize user's progress list if not exists
            if user_id not in self.progress:
                self.progress[user_id] = []
            
            # Add new workout data
            self.progress[user_id].append(workout_data)
            
            # Save to file
            self._write_json(self.progress_file, self.progress)
            logger.info(f"Saved workout progress for user {user_id} to file")
        except Exception as e:
            logger.error(f"Error saving progress to file: {str(e)}", exc_info=True)

    def get_user_progress(self, user_id):
        """Get user's workout progress"""
        user_id = str(user_id)
        if self.use_dynamo:
            response = self.progress_table.query(
                KeyConditionExpression=Key('user_id').eq(user_id)
            )
            return response.get('Items', [])
        else:
            progress = self._read_json(self.progress_file)
            return progress.get(user_id, [])

    def get_workout_streak(self, user_id):
        """Calculate current and longest workout streaks"""
        user_id = str(user_id)
        workouts = self.get_user_progress(user_id)
        if not workouts:
            return {"current_streak": 0, "longest_streak": 0}

        # Sort workouts by date, handling various date formats
        workout_dates = []
        for w in workouts:
            try:
                date_str = w['date']
                workout_date = None
                
                # Try parsing with different formats
                formats_to_try = [
                    '%Y-%m-%d %H:%M:%S',  # Format with time
                    '%Y-%m-%d',           # Format without time
                    '%d-%m-%Y',           # Alternative format
                    '%Y-%m-%d %H:%M',     # Format with hours and minutes only
                ]
                
                for date_format in formats_to_try:
                    try:
                        if ' ' in date_str and '%H' not in date_format:
                            # Skip date-only formats for strings with time
                            continue
                        workout_date = datetime.strptime(date_str, date_format).date()
                        break  # Stop trying formats if one succeeds
                    except ValueError:
                        continue
                
                # If all formats failed, try extracting just the date part
                if workout_date is None and ' ' in date_str:
                    date_part = date_str.split(' ')[0]
                    try:
                        workout_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                if workout_date:
                    workout_dates.append(workout_date)
                else:
                    logger.error(f"Failed to parse date '{date_str}' in any format")
                
            except Exception as e:
                logger.error(f"Error processing workout date: {str(e)}", exc_info=True)
        
        # Remove duplicates and sort
        workout_dates = sorted(set(workout_dates))

        if not workout_dates:
            return {"current_streak": 0, "longest_streak": 0}

        # Calculate streaks
        current_streak = 0
        longest_streak = 0
        streak_count = 0
        today = datetime.now().date()

        # Check if the last workout was today or yesterday to continue the streak
        last_workout = workout_dates[-1]
        if last_workout < today - timedelta(days=1):
            current_streak = 0
        else:
            # Count backwards from the last workout
            for i in range(len(workout_dates) - 1, -1, -1):
                if i == len(workout_dates) - 1:
                    streak_count = 1
                    continue

                if workout_dates[i] == workout_dates[i + 1] - timedelta(days=1):
                    streak_count += 1
                else:
                    break

            current_streak = streak_count

        # Calculate longest streak
        streak_count = 1
        for i in range(1, len(workout_dates)):
            if workout_dates[i] == workout_dates[i-1] + timedelta(days=1):
                streak_count += 1
            else:
                longest_streak = max(longest_streak, streak_count)
                streak_count = 1

        longest_streak = max(longest_streak, streak_count, current_streak)

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak
        }

    def get_workout_intensity_stats(self, user_id, days=30):
        """Get workout intensity statistics for the last N days"""
        user_id = str(user_id)
        workouts = self.get_user_progress(user_id)
        if not workouts:
            return []

        # Get date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # Group workouts by date
        daily_stats = defaultdict(lambda: {"total_exercises": 0, "completed_exercises": 0})

        for workout in workouts:
            try:
                date_str = workout['date']
                workout_date = None
                
                # Try parsing with different formats
                formats_to_try = [
                    '%Y-%m-%d %H:%M:%S',  # Format with time
                    '%Y-%m-%d',           # Format without time
                    '%d-%m-%Y',           # Alternative format
                    '%Y-%m-%d %H:%M',     # Format with hours and minutes only
                ]
                
                for date_format in formats_to_try:
                    try:
                        if ' ' in date_str and '%H' not in date_format:
                            # Skip date-only formats for strings with time
                            continue
                        workout_date = datetime.strptime(date_str, date_format).date()
                        break  # Stop trying formats if one succeeds
                    except ValueError:
                        continue
                
                # If all formats failed, try extracting just the date part
                if workout_date is None and ' ' in date_str:
                    date_part = date_str.split(' ')[0]
                    try:
                        workout_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                    except ValueError:
                        logger.error(f"Failed to parse date '{date_str}' in any format")
                        continue
                
                if not workout_date:
                    logger.error(f"Failed to parse date '{date_str}' in any format")
                    continue
                
                if start_date <= workout_date <= end_date:
                    date_key = workout_date.strftime('%Y-%m-%d')
                    total = workout.get('total_exercises', 0)
                    completed = workout.get('exercises_completed', 0)
                    
                    # Ensure values are integers
                    try:
                        total = int(total)
                        completed = int(completed)
                    except (ValueError, TypeError):
                        logger.warning(f"Non-integer exercise counts for workout on {date_key}: total={total}, completed={completed}")
                        total = 0 if total == 0 else 1
                        completed = 0 if completed == 0 else 1
                    
                    daily_stats[date_key]['total_exercises'] += total
                    daily_stats[date_key]['completed_exercises'] += completed
            except Exception as e:
                logger.error(f"Error processing workout for intensity stats: {str(e)}", exc_info=True)

        # Convert to list and sort by date
        stats = []
        for date, data in daily_stats.items():
            try:
                completion_rate = data['completed_exercises'] / data['total_exercises'] * 100 if data['total_exercises'] > 0 else 0
                stats.append({
                    "date": date,
                    "completion_rate": completion_rate,
                    "total_exercises": data['total_exercises']
                })
            except Exception as e:
                logger.error(f"Error calculating stats for date {date}: {str(e)}")
                
        return sorted(stats, key=lambda x: x['date'])

    def save_workout_feedback(self, user_id, workout_id, feedback_data):
        """Save workout feedback"""
        user_id = str(user_id)
        workout_id = str(workout_id)
        
        # Ensure feedback_data is properly structured
        if not isinstance(feedback_data, dict):
            logger.error(f"Invalid feedback data format: {feedback_data}")
            return False
            
        # Ensure we have the in-memory feedback structure
        if not hasattr(self, 'feedback'):
            self.feedback = {}
            
        # Initialize user's feedback if needed
        if user_id not in self.feedback:
            self.feedback[user_id] = {}

        # Add timestamp to feedback data if not present
        if 'timestamp' not in feedback_data:
            feedback_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        # Make sure we have both emotional and physical state set to something valid
        # This prevents None values from causing issues when analyzing feedback later
        if feedback_data.get('emotional_state') is None and feedback_data.get('physical_state') is None:
            logger.warning(f"Both emotional and physical states are None for feedback from user {user_id}")
            return False
            
        # Set default values for None states
        if feedback_data.get('emotional_state') is None:
            feedback_data['emotional_state'] = 'neutral'
            
        if feedback_data.get('physical_state') is None:
            feedback_data['physical_state'] = 'ok'
            
        # Log details about the feedback being saved
        logger.info(f"Saving feedback for user {user_id}, workout {workout_id}")
        logger.debug(f"Feedback data: {feedback_data}")

        try:
            if self.use_dynamo:
                # Prepare data for DynamoDB and ensure required fields
                dynamo_data = self._prepare_for_dynamo(feedback_data)
                dynamo_data['user_id'] = user_id
                dynamo_data['workout_id'] = workout_id
                dynamo_data['feedback_id'] = feedback_data.get('feedback_id', f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                # Save to DynamoDB
                self.feedback_table.put_item(Item=dynamo_data)
                logger.info(f"Saved feedback to DynamoDB for user {user_id}, workout {workout_id}")
            else:
                # Load feedback from file
                file_feedback = self._read_json(self.feedback_file)
                
                # Initialize structure if needed
                if user_id not in file_feedback:
                    file_feedback[user_id] = {}
                    
                # Save feedback
                file_feedback[user_id][workout_id] = feedback_data
                
                # Write back to file
                self._write_json(self.feedback_file, file_feedback)
                
                # Update in-memory representation
                self.feedback[user_id][workout_id] = feedback_data
                logger.info(f"Saved feedback to file for user {user_id}, workout {workout_id}")
                
            return True
        except Exception as e:
            logger.error(f"Error saving feedback: {str(e)}", exc_info=True)
            return False

    def get_user_feedback(self, user_id):
        """Get user's workout feedback history"""
        user_id = str(user_id)
        try:
            if self.use_dynamo:
                response = self.feedback_table.query(
                    KeyConditionExpression=Key('user_id').eq(user_id)
                )
                feedback_items = response.get('Items', [])
                
                # Convert the list of items to a dictionary with workout_id as key
                feedback = {}
                for item in feedback_items:
                    if 'workout_id' in item:
                        feedback[item['workout_id']] = item
                
            else:
                all_feedback = self._read_json(self.feedback_file)
                feedback = all_feedback.get(user_id, {})

            # If feedback is a list (from previous version) or not a dict, convert or use empty dict
            if isinstance(feedback, list):
                logger.warning(f"Feedback for user {user_id} is a list, converting to dict")
                feedback_dict = {}
                for item in feedback:
                    if isinstance(item, dict) and 'workout_id' in item:
                        feedback_dict[item['workout_id']] = item
                feedback = feedback_dict
            
            # If feedback is empty or not a dict, return an empty dict
            if not isinstance(feedback, dict):
                logger.warning(f"Invalid feedback format for user {user_id}, using empty dict")
                return {}

            # Sort feedback by timestamp to get the most recent ones first
            try:
                sorted_feedback = sorted(
                    [
                        (workout_id, data) 
                        for workout_id, data in feedback.items()
                        if isinstance(data, dict) and 'timestamp' in data  # Ensure data is valid
                    ],
                    key=lambda x: x[1]['timestamp'],
                    reverse=True
                )
                return dict(sorted_feedback)
            except Exception as sort_error:
                logger.error(f"Error sorting feedback: {sort_error}")
                return feedback  # Return unsorted feedback if sorting fails
        
        except Exception as e:
            logger.error(f"Error getting user feedback: {e}", exc_info=True)
            return {}  # Return empty dict on error

    def get_recent_feedback(self, user_id, limit=5):
        """Get user's recent workout feedback for adaptation"""
        try:
            feedback = self.get_user_feedback(user_id)
            
            # Handle empty feedback
            if not feedback:
                logger.info(f"No feedback found for user {user_id}, using default values")
                return {
                    'emotional_state': 'good',  # Default state if no feedback
                    'physical_state': 'ok',
                    'consecutive_negative': 0
                }
                
            recent = list(feedback.items())[:limit]

            logger.info(f"Getting recent feedback for user {user_id}")
            logger.info(f"Found {len(recent)} recent feedback entries")

            # Analyze recent feedback
            emotional_negative = 0
            physical_stats = {'too_easy': 0, 'ok': 0, 'tired': 0}

            for workout_id, data in recent:
                logger.info(f"Analyzing feedback for workout {workout_id}: {data}")
                
                # Get emotional state with default if missing
                emotional_state = data.get('emotional_state')
                if emotional_state == 'not_fun':
                    emotional_negative += 1
                
                # Get physical state with default if missing
                physical_state = data.get('physical_state', 'ok')
                if physical_state in physical_stats:
                    physical_stats[physical_state] += 1
                    
            # Determine predominant physical state
            predominant_physical = 'ok'  # Default
            max_count = physical_stats['ok']  # Start with 'ok' as baseline
            
            for state, count in physical_stats.items():
                if count > max_count:
                    max_count = count
                    predominant_physical = state
                    
            # Return analyzed feedback for adaptation
            return {
                'emotional_state': 'not_fun' if emotional_negative > (len(recent) // 2) else 'good',
                'physical_state': predominant_physical,
                'consecutive_negative': emotional_negative
            }
            
        except Exception as e:
            logger.error(f"Error getting recent feedback: {e}", exc_info=True)
            # Return default values on error
            return {
                'emotional_state': 'good',
                'physical_state': 'ok',
                'consecutive_negative': 0
            }

    def get_workouts_by_date(self, user_id, start_date, end_date):
        """Get workouts within date range"""
        user_progress = self.get_user_progress(user_id)
        result = []
        
        for workout in user_progress:
            try:
                date_str = workout['date']
                workout_date = None
                
                # Try parsing with different formats
                formats_to_try = [
                    '%Y-%m-%d %H:%M:%S',  # Format with time
                    '%Y-%m-%d',           # Format without time
                    '%d-%m-%Y',           # Alternative format
                    '%Y-%m-%d %H:%M',     # Format with hours and minutes only
                ]
                
                for date_format in formats_to_try:
                    try:
                        if ' ' in date_str and '%H' not in date_format:
                            # Skip date-only formats for strings with time
                            continue
                        workout_date = datetime.strptime(date_str, date_format).date()
                        break  # Stop trying formats if one succeeds
                    except ValueError:
                        continue
                
                # If all formats failed, try extracting just the date part
                if workout_date is None and ' ' in date_str:
                    date_part = date_str.split(' ')[0]
                    try:
                        workout_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                    except ValueError:
                        logger.error(f"Failed to parse date '{date_str}' in any format")
                        continue
                
                if not workout_date:
                    logger.error(f"Failed to parse date '{date_str}' in any format")
                    continue
                    
                if start_date <= workout_date <= end_date:
                    result.append(workout)
            except Exception as e:
                logger.error(f"Error processing workout in get_workouts_by_date: {str(e)}", exc_info=True)
                    
        return result

    def set_reminder(self, user_id, time):
        """Set workout reminder"""
        if self.use_dynamo:
            self.reminders_table.put_item(Item={'user_id': str(user_id), 'reminder_time': time})
        else:
            reminders = self._read_json(self.reminders_file)
            reminders[str(user_id)] = time
            self._write_json(self.reminders_file, reminders)

    def get_reminder(self, user_id):
        """Get user's reminder time"""
        if self.use_dynamo:
            response = self.reminders_table.get_item(
                Key={'user_id': str(user_id)}
            )
            return response.get('Item', {}).get('reminder_time')
        else:
            reminders = self._read_json(self.reminders_file)
            return reminders.get(str(user_id))

    def _ensure_files_exist(self):
        """Ensure all required JSON files exist and are properly initialized"""
        files = [
            self.users_file, 
            self.active_workouts_file, 
            self.progress_file,
            self.feedback_file,
            self.reminders_file
        ]
        
        for file in files:
            if not os.path.exists(file):
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(file), exist_ok=True)
                # Initialize file with empty dictionary
                self._write_json(file, {})
                logger.info(f"Created and initialized {file}")
            else:
                # Verify file is valid JSON
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {file}, reinitializing with empty dictionary")
                    self._write_json(file, {})

    def _read_json(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _write_json(self, file_path, data):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_detailed_progress_stats(self, user_id, days=30):
        """Get detailed progress statistics"""
        user_id = str(user_id)
        workouts = self.get_user_progress(user_id)

        if not workouts:
            return {
                "total_workouts": 0,
                "completion_rate": 0,
                "streaks": {"current": 0, "longest": 0},
                "weekly_stats": {},
                "monthly_stats": {}
            }

        # Calculate date ranges
        today = datetime.now().date()
        start_date = today - timedelta(days=days)

        # Initialize stats
        total_workouts = len(workouts)
        completed_workouts = sum(1 for w in workouts if w.get('workout_completed', False))
        completion_rate = int((completed_workouts / total_workouts * 100) if total_workouts > 0 else 0)

        # Get streak information
        streaks = self.get_workout_streak(user_id)

        # Weekly and monthly stats
        weekly_stats = defaultdict(lambda: {"workouts": 0, "completed": 0, "completion_rate": 0})
        monthly_stats = defaultdict(lambda: {"workouts": 0, "completed": 0, "completion_rate": 0})

        for workout in workouts:
            try:
                date_str = workout['date']
                workout_date = None
                
                # Try parsing with different formats
                formats_to_try = [
                    '%Y-%m-%d %H:%M:%S',  # Format with time
                    '%Y-%m-%d',           # Format without time
                    '%d-%m-%Y',           # Alternative format
                    '%Y-%m-%d %H:%M',     # Format with hours and minutes only
                ]
                
                for date_format in formats_to_try:
                    try:
                        if ' ' in date_str and '%H' not in date_format:
                            # Skip date-only formats for strings with time
                            continue
                        workout_date = datetime.strptime(date_str, date_format).date()
                        break  # Stop trying formats if one succeeds
                    except ValueError:
                        continue
                
                # If all formats failed, try extracting just the date part
                if workout_date is None and ' ' in date_str:
                    date_part = date_str.split(' ')[0]
                    try:
                        workout_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                    except ValueError:
                        logger.error(f"Failed to parse date '{date_str}' in any format")
                        continue
                
                if not workout_date:
                    logger.error(f"Failed to parse date '{date_str}' in any format")
                    continue
                
                if workout_date >= start_date:
                    # Weekly stats
                    week = workout_date.isocalendar()[1]  # Get week number
                    week_key = f"Week {week}"
                    weekly_stats[week_key]["workouts"] += 1
                    if workout.get('workout_completed', False):
                        weekly_stats[week_key]["completed"] += 1

                    # Monthly stats
                    month_key = workout_date.strftime('%B %Y')  # Month name and year
                    monthly_stats[month_key]["workouts"] += 1
                    if workout.get('workout_completed', False):
                        monthly_stats[month_key]["completed"] += 1
            except Exception as e:
                logger.error(f"Error processing workout for progress stats: {str(e)}", exc_info=True)

        # Calculate completion rates for each period
        for stats in weekly_stats.values():
            stats["completion_rate"] = int((stats["completed"] / stats["workouts"] * 100) if stats["workouts"] > 0 else 0)

        for stats in monthly_stats.values():
            stats["completion_rate"] = int((stats["completed"] / stats["workouts"] * 100) if stats["workouts"] > 0 else 0)

        return {
            "total_workouts": total_workouts,
            "completed_workouts": completed_workouts,
            "completion_rate": completion_rate,
            "streaks": streaks,
            "weekly_stats": dict(weekly_stats),
            "monthly_stats": dict(monthly_stats)
        }

    def save_subscription(self, user_id, subscription_data):
        """Save user subscription data"""
        user_id = str(user_id)
        
        if self.use_dynamo:
            try:
                # First get the current user profile
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                profile = response.get('Item', {})
                
                if not profile:
                    logger.warning(f"No user profile found for user {user_id} when saving subscription")
                    return False
                
                # Update with subscription data
                profile['subscription'] = subscription_data
                
                # Prepare for DynamoDB and save
                dynamo_profile = self._prepare_for_dynamo(profile)
                self.users_table.put_item(Item=dynamo_profile)
                logger.info(f"Saved subscription for user {user_id} to DynamoDB")
                return True
            except Exception as e:
                logger.error(f"Error saving subscription to DynamoDB: {str(e)}")
                return False
        else:
            # Load users from file if not already loaded
            if not hasattr(self, 'users'):
                self.users = self._read_json(self.users_file)
                
            if user_id not in self.users:
                logger.warning(f"No user profile found for user {user_id} when saving subscription")
                return False

            self.users[user_id]['subscription'] = subscription_data
            self._write_json(self.users_file, self.users)
            logger.info(f"Saved subscription for user {user_id} to file")
            return True

    def get_subscription(self, user_id):
        """Get user subscription data"""
        user_id = str(user_id)
        
        if self.use_dynamo:
            try:
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                user = response.get('Item', {})
            except Exception as e:
                logger.error(f"Error retrieving user from DynamoDB: {str(e)}")
                user = {}
        else:
            if not hasattr(self, 'users'):
                self.users = self._read_json(self.users_file)
            user = self.users.get(user_id, {})
            
        return user.get('subscription')

    def check_subscription_status(self, user_id):
        """Check if user has active subscription or is within trial period"""
        user_id = str(user_id)
        
        # Get user data differently depending on storage method
        if self.use_dynamo:
            try:
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                user = response.get('Item', {})
            except Exception as e:
                logger.error(f"Error retrieving user from DynamoDB: {str(e)}")
                return False
        else:
            if not hasattr(self, 'users'):
                self.users = self._read_json(self.users_file)
            user = self.users.get(user_id, {})

        if not user:
            logger.warning(f"User {user_id} not found in database during subscription check")
            return False

        subscription = user.get('subscription', {})
        
        # Check whitelist status (users with premium access)
        if subscription.get('premium', False):
            logger.info(f"User {user_id} has premium access - bypassing subscription check")
            return True
            
        if subscription.get('active', False):
            # Check if subscription is still valid
            expiry_date = datetime.strptime(subscription.get('expiry_date', '2000-01-01'), '%Y-%m-%d')
            is_valid = datetime.now() <= expiry_date
            logger.info(f"User {user_id} subscription valid: {is_valid}, expires: {expiry_date}")
            return is_valid
            
        return True  # For now, allow all users (no subscription requirement)
        
    def add_premium_status(self, user_id):
        """Add premium access to user subscription"""
        user_id = str(user_id)
        logger.info(f"Attempting to add premium status to user {user_id}")
        
        if self.use_dynamo:
            try:
                # First get the current user profile
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                profile = response.get('Item', {})
                
                if not profile:
                    logger.warning(f"No user profile found for user {user_id} when adding premium access")
                    return False
                
                # Update or create subscription data
                if 'subscription' not in profile:
                    profile['subscription'] = {}
                
                profile['subscription']['premium'] = True
                
                # Prepare for DynamoDB and save
                dynamo_profile = self._prepare_for_dynamo(profile)
                self.users_table.put_item(Item=dynamo_profile)
                logger.info(f"User {user_id} granted premium access in DynamoDB")
                return True
            except Exception as e:
                logger.error(f"Error adding premium status to DynamoDB: {str(e)}")
                return False
        else:
            # Load users from file if not already loaded
            if not hasattr(self, 'users'):
                self.users = self._read_json(self.users_file)
                
            if user_id not in self.users:
                logger.warning(f"No user profile found for user {user_id} when adding premium access")
                return False
                
            if 'subscription' not in self.users[user_id]:
                logger.info(f"Creating new subscription entry for user {user_id}")
                self.users[user_id]['subscription'] = {}
                
            logger.info(f"Setting premium=True for user {user_id}")
            self.users[user_id]['subscription']['premium'] = True
            
            # Log user data before saving
            logger.info(f"User data before save: {self.users[user_id]}")
            
            try:
                self._write_json(self.users_file, self.users)
                logger.info(f"User {user_id} granted premium access - save successful")
                
                # Double-check that premium status was actually saved
                reloaded_user = self._read_json(self.users_file).get(user_id, {})
                reloaded_premium = reloaded_user.get('subscription', {}).get('premium', False)
                logger.info(f"Verified premium status for user {user_id}: {reloaded_premium}")
                
                return True
            except Exception as e:
                logger.error(f"Error saving premium status: {e}")
                return False
        
    def remove_premium_status(self, user_id):
        """Remove premium access from user subscription"""
        user_id = str(user_id)
        logger.info(f"Attempting to remove premium status from user {user_id}")
        
        if self.use_dynamo:
            try:
                # First get the current user profile
                response = self.users_table.get_item(
                    Key={'user_id': user_id}
                )
                profile = response.get('Item', {})
                
                if not profile or 'subscription' not in profile:
                    logger.warning(f"No user profile or subscription found for user {user_id} when removing premium access")
                    return False
                
                profile['subscription']['premium'] = False
                
                # Prepare for DynamoDB and save
                dynamo_profile = self._prepare_for_dynamo(profile)
                self.users_table.put_item(Item=dynamo_profile)
                logger.info(f"Premium access removed for user {user_id} in DynamoDB")
                return True
            except Exception as e:
                logger.error(f"Error removing premium status from DynamoDB: {str(e)}")
                return False
        else:
            # Load users from file if not already loaded
            if not hasattr(self, 'users'):
                self.users = self._read_json(self.users_file)
            
            if user_id not in self.users or 'subscription' not in self.users[user_id]:
                logger.warning(f"No user profile or subscription found for user {user_id} when removing premium access")
                return False
                
            logger.info(f"Setting premium=False for user {user_id}")
            self.users[user_id]['subscription']['premium'] = False
            
            try:
                self._write_json(self.users_file, self.users)
                logger.info(f"Premium access removed for user {user_id} - save successful")
                return True
            except Exception as e:
                logger.error(f"Error removing premium status: {e}")
                return False

    def migrate_data_to_dynamo(self):
        """Migrate all data from JSON files to DynamoDB"""
        # Migrate users
        users = self._read_json(self.users_file)
        for user_id, profile in users.items():
            profile_copy = profile.copy()
            profile_copy['user_id'] = user_id
            self.users_table.put_item(Item=profile_copy)
        
        # Migrate active workouts
        workouts = self._read_json(self.active_workouts_file)
        for user_id, workout in workouts.items():
            workout_copy = workout.copy()
            workout_copy['user_id'] = user_id
            self.workouts_table.put_item(Item=workout_copy)
        
        # Migrate progress (requires restructuring)
        progress = self._read_json(self.progress_file)
        for user_id, entries in progress.items():
            for entry in entries:
                entry_copy = entry.copy()
                entry_copy['user_id'] = user_id
                entry_copy['progress_id'] = f"{user_id}_{entry['workout_id']}"
                entry_copy['timestamp'] = int(time.time())
                self.progress_table.put_item(Item=entry_copy)
        
        # ... migrate other data ...