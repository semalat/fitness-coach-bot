import schedule
import time
from threading import Thread
from telegram import Bot
from telegram.error import TelegramError
from datetime import datetime

class ReminderManager:
    def __init__(self, bot, database):
        self.bot = bot
        self.database = database
        self.thread = Thread(target=self._run_schedule, daemon=True)
        self.thread.start()

    def set_reminder(self, user_id, time_str):
        """Set a new reminder for a user"""
        self.database.set_reminder(user_id, time_str)
        self._schedule_reminder(user_id, time_str)

    def _schedule_reminder(self, user_id, time_str):
        """Schedule a reminder for specific time"""
        schedule.every().day.at(time_str).do(
            self._send_reminder, user_id=user_id
        )

    def _send_reminder(self, user_id):
        """Send reminder message to user"""
        try:
            self.bot.send_message(
                chat_id=user_id,
                text="🏋️‍♂️ Время тренировки! Готовы начать? Используйте /workout для получения программы."
            )
        except Exception as e:
            print(f"Error sending reminder to {user_id}: {e}")

    def _run_schedule(self):
        """Run the schedule loop in background"""
        while True:
            schedule.run_pending()
            time.sleep(60)