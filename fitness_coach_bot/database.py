import json
from datetime import datetime, timedelta
import json
from collections import defaultdict
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        """Initialize database and load existing data"""
        self.users = self._load_from_file('users.json')
        self.workouts = self._load_from_file('workouts.json')
        self.progress = self._load_from_file('progress.json')
        self.reminders = self._load_from_file('reminders.json')
        self.feedback = self._load_from_file('feedback.json')
        self.active_workouts = self._load_from_file('active_workouts.json')

    def save_active_workout(self, user_id, workout):
        """Save active workout to database"""
        user_id = str(user_id)
        try:
            logger.info(f"Saving active workout for user {user_id}")
            logger.info(f"Workout data: {workout}")
            self.active_workouts[user_id] = workout
            self._save_to_file('active_workouts.json', self.active_workouts)
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
            workout = self.active_workouts.get(user_id)
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
        if str(user_id) in self.active_workouts:
            del self.active_workouts[str(user_id)]
            self._save_to_file('active_workouts.json', self.active_workouts)

        # Add debug logging
        logger.info(f"Loaded users from database: {self.users}")

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

        self.users[user_id] = profile_data
        self._save_to_file('users.json', self.users)

    def get_user_profile(self, user_id):
        """Get user profile data"""
        user_id = str(user_id)
        profile = self.users.get(user_id)

        # Log the retrieved profile
        logger.info(f"Retrieved user profile - ID: {user_id}, Profile: {profile}")

        return profile

    def save_workout_progress(self, user_id, workout_data):
        """Save workout completion data"""
        user_id = str(user_id)
        if user_id not in self.progress:
            self.progress[user_id] = []

        workout_data['date'] = datetime.now().strftime('%Y-%m-%d')
        self.progress[user_id].append(workout_data)
        self._save_to_file('progress.json', self.progress)

    def get_user_progress(self, user_id):
        """Get user's workout progress"""
        return self.progress.get(str(user_id), [])

    def get_workout_streak(self, user_id):
        """Calculate current and longest workout streaks"""
        user_id = str(user_id)
        workouts = self.get_user_progress(user_id)
        if not workouts:
            return {"current_streak": 0, "longest_streak": 0}

        # Sort workouts by date
        workout_dates = sorted(set(
            datetime.strptime(w['date'], '%Y-%m-%d').date()
            for w in workouts
        ))

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
            workout_date = datetime.strptime(workout['date'], '%Y-%m-%d').date()
            if start_date <= workout_date <= end_date:
                daily_stats[workout_date.strftime('%Y-%m-%d')]['total_exercises'] += workout['total_exercises']
                daily_stats[workout_date.strftime('%Y-%m-%d')]['completed_exercises'] += workout['exercises_completed']

        # Convert to list and sort by date
        stats = [
            {
                "date": date,
                "completion_rate": stats['completed_exercises'] / stats['total_exercises'] * 100 if stats['total_exercises'] >0 else 0,
                "total_exercises": stats['total_exercises']
            }
            for date, stats in daily_stats.items()
        ]

        return sorted(stats, key=lambda x: x['date'])

    def save_workout_feedback(self, user_id, workout_id, feedback_data):
        """Save workout feedback"""
        user_id = str(user_id)
        if user_id not in self.feedback:
            self.feedback[user_id] = {}

        # Add timestamp to feedback data
        feedback_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.feedback[user_id][workout_id] = feedback_data
        self._save_to_file('feedback.json', self.feedback)

        # Log the feedback
        logger.info(f"Saved feedback for user {user_id}, workout {workout_id}: {feedback_data}")

    def get_user_feedback(self, user_id):
        """Get user's workout feedback history"""
        user_id = str(user_id)
        feedback = self.feedback.get(user_id, {})

        # Sort feedback by timestamp to get the most recent ones first
        sorted_feedback = sorted(
            [
                (workout_id, data) 
                for workout_id, data in feedback.items()
            ],
            key=lambda x: x[1]['timestamp'],
            reverse=True
        )

        return dict(sorted_feedback)
    
    def get_recent_feedback(self, user_id, limit=5):
        """Get user's recent workout feedback for adaptation"""
        feedback = self.get_user_feedback(user_id)
        recent = list(feedback.items())[:limit]

        logger.info(f"Getting recent feedback for user {user_id}")
        logger.info(f"Found {len(recent)} recent feedback entries")

        if not recent:
            logger.info(f"No feedback found for user {user_id}, using default values")
            return {
                'emotional_state': 'good',  # Default state if no feedback
                'physical_state': 'ok',
                'consecutive_negative': 0
            }

        # Analyze recent feedback
        emotional_negative = 0
        physical_stats = {'too_easy': 0, 'ok': 0, 'tired': 0}

        for workout_id, data in recent:
            logger.info(f"Analyzing feedback for workout {workout_id}: {data}")
            if data.get('emotional_state') == 'not_fun':
                emotional_negative += 1
            physical_state = data.get('physical_state', 'ok')
            if physical_state in physical_stats:
                physical_stats[physical_state] += 1

        # Determine predominant states
        emotional_state = 'not_fun' if emotional_negative >= len(recent) // 2 else 'good'
        physical_state = max(physical_stats.items(), key=lambda x: x[1])[0]

        result = {
            'emotional_state': emotional_state,
            'physical_state': physical_state,
            'consecutive_negative': emotional_negative
        }

        logger.info(f"Analyzed feedback for user {user_id}: {result}")
        logger.info(f"Physical state distribution: {physical_stats}")
        return result

    def get_workouts_by_date(self, user_id, start_date, end_date):
        """Get workouts within date range"""
        user_progress = self.get_user_progress(user_id)
        return [
            workout for workout in user_progress
            if start_date <= datetime.strptime(workout['date'], '%Y-%m-%d').date() <= end_date
        ]

    def set_reminder(self, user_id, time):
        """Set workout reminder"""
        self.reminders[str(user_id)] = time
        self._save_to_file('reminders.json', self.reminders)

    def get_reminder(self, user_id):
        """Get user's reminder time"""
        return self.reminders.get(str(user_id))

    def _save_to_file(self, filename, data):
        """Save data to JSON file"""
        try:
            # Add prefix for test environment if specified
            prefix = os.environ.get('DB_PREFIX', '')
            prefixed_filename = f"{prefix}{filename}"
            
            # Add project directory prefix
            filepath = f"fitness_coach_bot/{prefixed_filename}"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Successfully saved data to {filepath}")
        except Exception as e:
            logger.error(f"Error saving to {filepath}: {e}")
            # Try saving to root directory as fallback
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Successfully saved data to root {filename}")
            except Exception as e:
                logger.error(f"Error saving to root {filename}: {e}")

    def _load_from_file(self, filename):
        """Load data from JSON file"""
        try:
            # Try project directory first
            filepath = f"fitness_coach_bot/{filename}"
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Successfully loaded data from {filepath}")
                return data
            except FileNotFoundError:
                # Try root directory
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Successfully loaded data from root {filename}")
                return data
        except FileNotFoundError:
            logger.warning(f"No existing file found for {filename}, creating new")
            return {}
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return {}

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
            workout_date = datetime.strptime(workout['date'], '%Y-%m-%d').date()
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
        if user_id not in self.users:
            logger.warning(f"No user profile found for user {user_id} when saving subscription")
            return False

        self.users[user_id]['subscription'] = subscription_data
        self._save_to_file('users.json', self.users)
        return True

    def get_subscription(self, user_id):
        """Get user subscription data"""
        user_id = str(user_id)
        user = self.users.get(user_id, {})
        return user.get('subscription')

    def check_subscription_status(self, user_id):
        """Check if user has active subscription or is within trial period"""
        user_id = str(user_id)
        user = self.users.get(user_id, {})

        if not user:
            return False

        subscription = user.get('subscription', {})
        
        # Check whitelist status (users with premium access)
        if subscription.get('premium', False):
            logger.info(f"User {user_id} has premium access - bypassing subscription check")
            return True
            
        if subscription.get('active', False):
            # Check if subscription is still valid
            expiry_date = datetime.strptime(subscription.get('expiry_date', '2000-01-01'), '%Y-%m-%d')
            return datetime.now() <= expiry_date

        # Check trial period
        profile_created = datetime.strptime(user.get('last_updated', '2000-01-01'), '%Y-%m-%d %H:%M:%S')
        trial_end = profile_created + timedelta(days=10)
        return datetime.now() <= trial_end
        
    def add_premium_status(self, user_id):
        """Add premium access to user subscription"""
        user_id = str(user_id)
        if user_id not in self.users:
            logger.warning(f"No user profile found for user {user_id} when adding premium access")
            return False
            
        if 'subscription' not in self.users[user_id]:
            self.users[user_id]['subscription'] = {}
            
        self.users[user_id]['subscription']['premium'] = True
        self._save_to_file('users.json', self.users)
        logger.info(f"User {user_id} granted premium access")
        return True
        
    def remove_premium_status(self, user_id):
        """Remove premium access from user subscription"""
        user_id = str(user_id)
        if user_id not in self.users or 'subscription' not in self.users[user_id]:
            logger.warning(f"No user profile or subscription found for user {user_id} when removing premium access")
            return False
            
        self.users[user_id]['subscription']['premium'] = False
        self._save_to_file('users.json', self.users)
        logger.info(f"Premium access removed for user {user_id}")
        return True