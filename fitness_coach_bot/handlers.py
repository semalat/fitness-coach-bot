import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Message
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, TypeHandler, PreCheckoutQueryHandler
)
import logging
from fitness_coach_bot import messages
from datetime import datetime, timedelta
from fitness_coach_bot.config import AGE, HEIGHT, WEIGHT, SEX, GOALS, FITNESS_LEVEL, EQUIPMENT, SUBSCRIPTION_MESSAGE
from fitness_coach_bot.keyboards import (
    get_sex_keyboard, get_goals_keyboard, get_fitness_level_keyboard,
    get_equipment_keyboard, get_calendar_keyboard, get_reminder_keyboard,
    get_subscription_keyboard, get_subscription_plans_keyboard,
    get_payment_keyboard, get_check_payment_keyboard, get_back_to_main_keyboard
)
from fitness_coach_bot.payment_manager import PaymentManager
import re
import random
import traceback

logger = logging.getLogger(__name__)

# Email validation regex
EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")

class BotHandlers:
    def __init__(self, database, workout_manager, reminder_manager):
        self.db = database
        self.workout_manager = workout_manager
        self.reminder_manager = reminder_manager
        
        # Initialize payment manager
        self.payment_manager = PaymentManager(database)
        
        # States for conversation handlers
        self.PROFILE = range(1, 10)
        self.WORKOUT = range(10, 20)
        self.TIMER = range(20, 30)
        self.PAYMENT = range(30, 40)  # Add states for payment process
        
        # Email collection state
        self.WAITING_FOR_EMAIL = 31
        
        # The database parameter is used as 'database' in PaymentManager,
        # so we pass the database object directly
        self.payment_manager = PaymentManager(database)  # Keep using 'database' to match PaymentManager's expectation

    async def show_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /progress command - show fitness dashboard"""
        try:
            # Determine if this is a direct command or callback
            if update.callback_query:
                user_id = update.callback_query.from_user.id
                message_obj = update.callback_query.message
            else:
                user_id = update.effective_user.id
                message_obj = update.message

            # Get detailed statistics
            stats = self.db.get_detailed_progress_stats(user_id)
            logger.info(f"Retrieved initial stats for dashboard: {stats}")

            streaks = stats.get('streaks', {})
            current_streak = streaks.get('current_streak', 0)
            longest_streak = streaks.get('longest_streak', 0)

            # Format main dashboard message
            message = "🏋️‍♂️ *Фитнес Дашборд*\n\n"

            # Overall Statistics
            message += "*📊 Общая статистика*\n"
            message += f"• Всего тренировок: {stats.get('total_workouts', 0)}\n"
            message += f"• Завершено полностью: {stats.get('completed_workouts', 0)}\n"
            message += f"• Процент завершения: {stats.get('completion_rate', 0)}%\n\n"

            # Streaks
            message += "*🔥 Серии тренировок*\n"
            message += f"• Текущая серия: {current_streak} дней\n"
            message += f"• Лучшая серия: {longest_streak} дней\n\n"

            # Navigation buttons
            keyboard = [
                [
                    InlineKeyboardButton("📈 Прогресс по неделям", callback_data="progress_weekly"),
                    InlineKeyboardButton("📅 Месячный отчет", callback_data="progress_monthly")
                ],
                [
                    InlineKeyboardButton("🏆 Достижения", callback_data="achievements"),
                    InlineKeyboardButton("📋 История", callback_data="workout_history")
                ],
                [
                    InlineKeyboardButton("💪 Анализ интенсивности", callback_data="intensity_analysis")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            logger.info("Sending main dashboard view")
            try:
                if isinstance(message_obj, Message):
                    await message_obj.reply_text(
                        message,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await message_obj.edit_text(
                        message,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error sending message: {str(e)}", exc_info=True)
                # Try to send as a new message if edit fails
                await update.effective_chat.send_message(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Error showing progress dashboard: {str(e)}", exc_info=True)
            error_message = "Произошла ошибка при загрузке статистики. Попробуйте позже."
            try:
                if isinstance(message_obj, Message):
                    await message_obj.reply_text(error_message)
                else:
                    await update.callback_query.message.reply_text(error_message)
            except Exception as send_error:
                logger.error(f"Error sending error message: {str(send_error)}", exc_info=True)
                await update.effective_chat.send_message(error_message)

    async def start_gym_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a gym-specific workout session"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        equipment = profile.get('equipment', '').lower()
        if 'зал' not in equipment:
            await update.message.reply_text(
                "Ваш профиль настроен для тренировок без оборудования. "
                "Используйте /start_workout для начала тренировки с собственным весом."
            )
            return

        # Show muscle group selection
        keyboard = [
            [
                InlineKeyboardButton("Грудь + Бицепс", callback_data="muscle_грудь_бицепс"),
                InlineKeyboardButton("Спина + Трицепс", callback_data="muscle_спина_трицепс")
            ],
            [InlineKeyboardButton("Ноги", callback_data="muscle_ноги")],
            [InlineKeyboardButton("Тренировка на все группы мышц", callback_data="muscle_все_группы")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Выберите группу мышц для тренировки:",
            reply_markup=reply_markup
        )

    async def _show_gym_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display current exercise with controls"""
        user_id = update.effective_user.id if update.callback_query else update.effective_user.id
        workout = self.db.get_active_workout(user_id)

        if not workout:
            message = "Тренировка не найдена. Используйте /workout для получения программы."
            if update.callback_query:
                await update.callback_query.message.reply_text(message)
            else:
                await update.message.reply_text(message)
            return

        # Convert Decimal to int for list indexing
        current_exercise_idx = int(workout['current_exercise'])
        exercise = workout['exercises'][current_exercise_idx]
        current = current_exercise_idx + 1
        total = int(workout['total_exercises'])

        # Build the message based on workout type
        if workout['workout_type'] == 'bodyweight':
            current_circuit = int(workout.get('current_circuit', 1))  # Convert to int
            total_circuits = int(exercise.get('circuits', 3))  # Convert to int

            message = f"💪 Круг {current_circuit}/{total_circuits}\n"
            message += f"Упражнение {current}/{total}\n\n"
            message += f"📍 {exercise['name']}\n"
            message += f"🎯 Целевые мышцы: {exercise['target_muscle']}\n"
            message += f"⭐ Сложность: {exercise.get('difficulty', 'средний')}\n\n"

            # Convert exercise time to int for both display and comparison
            exercise_time = int(exercise.get('time', 0))
            exercise_reps = int(exercise.get('reps', 0))
            
            # Check for timed exercise
            if exercise_time > 0:
                message += f"⏱ Время: {exercise_time} сек\n"
            else:
                message += f"🔄 Повторения: {exercise_reps}\n"

            # Format rest times using workout-level circuits rest
            circuits_rest = int(workout['circuits_rest'])  # Convert to int
            if circuits_rest >= 60:
                circuits_rest_str = f"{circuits_rest // 60} мин {circuits_rest % 60} сек"
            else:
                circuits_rest_str = f"{circuits_rest} сек"

            exercises_rest = int(exercise['exercises_rest'])  # Convert to int
            exercises_rest_str = f"{exercises_rest} сек"

            message += f"\n⏰ Отдых между кругами: {circuits_rest_str}"
            message += f"\n⏰ Отдых между упражнениями: {exercises_rest_str}"

            # Add instructions
            message += "\n\n📋 Как выполнять:"
            if exercise_time > 0:
                message += "\n1️⃣ Нажмите кнопку '⏱ Старт упражнения' чтобы начать таймер"
                message += "\n2️⃣ Выполняйте упражнение пока идет таймер"
                message += "\n3️⃣ После сигнала таймера нажмите '✅ Упражнение выполнено'"
            else:
                message += "\n1️⃣ Выполните упражнение указанное количество раз"
                message += "\n2️⃣ Нажмите '✅ Упражнение выполнено'"
            message += "\n3️⃣ Отдохните, нажав кнопку таймера"
            message += "\n4️⃣ После последнего упражнения - отдохните перед следующим кругом"

            # Create keyboard
            keyboard = []

            # Add exercise timer button if it's a timed exercise
            if exercise_time > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        "⏱ Старт упражнения",
                        callback_data=f"exercise_timer_{exercise_time}"
                    )
                ])

            # Add completion button
            keyboard.append([InlineKeyboardButton("✅ Упражнение выполнено", callback_data="exercise_done")])

            # Add appropriate rest timer
            if current_exercise_idx == total - 1:
                # Show circuit rest only after last exercise
                keyboard.append([
                    InlineKeyboardButton(
                        f"⏰ Отдых между кругами {circuits_rest_str}",
                        callback_data=f"circuit_rest_{circuits_rest}"
                    )
                ])
            else:
                # Show exercise rest between exercises
                keyboard.append([
                    InlineKeyboardButton(
                        f"⏰ Отдых между упражнениями {exercises_rest_str}",
                        callback_data=f"exercise_rest_{exercises_rest}"
                    )
                ])

        else:
            current_set = int(exercise.get('current_set', 1))  # Convert to int
            total_sets = int(exercise.get('sets', 3))  # Convert to int

            message = f"💪 Упражнение {current}/{total}\n\n"
            message += f"📍 {exercise['name']}\n"
            message += f"🎯 Целевые мышцы: {exercise['target_muscle']}\n"
            message += f"⭐ Сложность: {exercise.get('difficulty', 'средний')}\n\n"
            message += f"Сет {current_set}/{total_sets}\n"

            # Check if exercise has time or reps data
            has_time = 'time' in exercise and int(exercise.get('time', 0)) > 0
            has_reps = 'reps' in exercise and int(exercise.get('reps', 0)) > 0
            
            if has_time:
                # For time-based exercises (like running on treadmill)
                exercise_time = int(exercise.get('time', 0))
                time_minutes = exercise_time // 60
                time_seconds = exercise_time % 60
                
                if time_minutes > 0:
                    message += f"⏱ Время: {time_minutes} мин {time_seconds} сек\n"
                else:
                    message += f"⏱ Время: {time_seconds} сек\n"
            elif has_reps:
                # For rep-based exercises
                message += f"🔄 Повторения: {int(exercise['reps'])}\n"  # Convert to int
            else:
                # Fallback if neither is present
                message += f"🔄 Подходов: {total_sets}\n"

            # Fix the type error by converting weight to float first
            weight = self._safe_float_convert(exercise.get('weight', 0))
            if weight > 0:
                message += f"🏋️ Вес: {int(weight)} кг\n"

            sets_rest = int(exercise['sets_rest'])  # Convert to int
            message += f"\n⏰ Отдых между сетами: {sets_rest} сек"

            # Add instructions
            message += "\n\n📋 Как выполнять:"
            if has_time:
                message += "\n1️⃣ Нажмите кнопку '⏱ Старт упражнения' чтобы начать таймер"
                message += "\n2️⃣ Выполняйте упражнение пока идет таймер"
                message += "\n3️⃣ После сигнала таймера нажмите '✅ Сет выполнен'"
            else:
                message += "\n1️⃣ Выполните указанное количество повторений с заданным весом"
                message += "\n2️⃣ Нажмите '✅ Сет выполнен'"
            message += "\n3️⃣ Отдохните, нажав кнопку таймера"

            # Create keyboard
            keyboard = []
            
            # Add exercise timer button only if it's a timed exercise
            if has_time:
                exercise_time = int(exercise.get('time', 0))
                keyboard.append([
                    InlineKeyboardButton(
                        "⏱ Старт упражнения",
                        callback_data=f"exercise_timer_{exercise_time}"
                    )
                ])

            # Add completion button
            keyboard.append([InlineKeyboardButton("✅ Сет выполнен", callback_data="set_done")])
            keyboard.append([
                InlineKeyboardButton(
                    f"⏰ Отдых {sets_rest} сек",
                    callback_data=f"rest_{sets_rest}"
                )
            ])

        # Add navigation buttons
        nav_buttons = []
        if current_exercise_idx > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущее", callback_data="prev_exercise"))
        if current_exercise_idx < total - 1:
            nav_buttons.append(InlineKeyboardButton("➡️ Следующее", callback_data="next_exercise"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Add finish workout button
        keyboard.append([InlineKeyboardButton("🏁 Закончить тренировку", callback_data="finish_workout")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if 'gif_url' in exercise:
                try:
                    if update.callback_query:
                        await update.callback_query.message.reply_animation(
                            animation=exercise['gif_url'],
                            caption=message,
                            reply_markup=reply_markup
                        )
                        try:
                            await update.callback_query.message.delete()
                        except Exception:
                            pass
                    else:
                        await update.message.reply_animation(
                            animation=exercise['gif_url'],
                            caption=message,
                            reply_markup=reply_markup
                        )
                except Exception as e:
                    logger.error(f"Failed to send GIF: {str(e)}")
                    if update.callback_query:
                        await update.callback_query.message.reply_text(
                            text=message,
                            reply_markup=reply_markup
                        )
                    else:
                        await update.message.reply_text(
                            text=message,
                            reply_markup=reply_markup
                        )
            else:
                if update.callback_query:
                    await update.callback_query.message.reply_text(
                        text=message,
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(
                        text=message,
                        reply_markup=reply_markup
                    )

        except Exception as e:
            logger.error(f"Error in _show_gym_exercise: {str(e)}")
            error_message = "Произошла ошибка. Пожалуйста, начните тренировку заново."
            if update.callback_query:
                await update.callback_query.message.reply_text(error_message)
            else:
                await update.message.reply_text(error_message)

    async def _finish_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete workout and save user's progress"""
        user_id = update.effective_user.id
        workout = self.db.get_active_workout(user_id)

        if not workout:
            # Use effective_chat which works in both message and callback contexts
            await update.effective_chat.send_message("У вас нет активной тренировки.")
            return

        try:
            current_exercise = int(workout.get('current_exercise', 0))
            total_exercises = int(workout.get('total_exercises', 0))
        except (ValueError, TypeError) as e:
            logger.warning(f"Error converting exercise numbers: {e}")
            current_exercise = 0
            total_exercises = 0

        # Create completion data
        completion_data = {
            'workout_id': workout.get('workout_id', f"workout_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
            'workout_type': workout.get('workout_type', 'unknown'),
            'exercises_completed': current_exercise,
            'total_exercises': total_exercises,
            'workout_completed': True,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Save the workout_id in context for feedback
        context.user_data['last_workout_id'] = completion_data['workout_id']

        success = True
        error_message = None
        try:
            self.db.save_workout_progress(user_id, completion_data)
            logger.info(f"Saved workout progress for user {user_id}: {completion_data}")
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Error saving workout progress: {e}")

        # Remove active workout
        self.db.finish_active_workout(user_id)

        # Prepare feedback buttons
        keyboard = [
            [
                InlineKeyboardButton("👍 Понравилось", callback_data="feedback_fun"),
                InlineKeyboardButton("👎 Не понравилось", callback_data="feedback_not_fun")
            ],
            [
                InlineKeyboardButton("😅 Было легко", callback_data="feedback_too_easy"),
                InlineKeyboardButton("😊 Нормально", callback_data="feedback_ok"),
                InlineKeyboardButton("😓 Устал(а)", callback_data="feedback_tired")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Handle both direct message and callback query cases
        if success:
            await update.effective_chat.send_message(
                "🎉 Тренировка завершена! Как вам тренировка?",
                reply_markup=reply_markup
            )
        else:
            await update.effective_chat.send_message(
                f"⚠️ Тренировка завершена, но возникла ошибка при сохранении прогресса: {error_message}\n"
                "Как вам тренировка?",
                reply_markup=reply_markup
            )

    async def handle_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, timer_type: str, rest_time: int):
        """Handle rest timer between sets/circuits"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        # Create and store timer job in context
        timer_message = await query.message.reply_text(f"⏱ {timer_type}: {rest_time} сек")
        
        # Store message ID and other info in context for later use
        if 'timer_messages' not in context.chat_data:
            context.chat_data['timer_messages'] = []
        context.chat_data['timer_messages'].append(timer_message.message_id)
        
        # Store the chat_id and original message for automatic progress
        timer_data = {
            'user_id': user_id,
            'original_message_id': query.message.message_id,
            'chat_id': query.message.chat_id,
            'is_active': True
        }
        context.chat_data['current_timer'] = timer_data
        
        async def update_timer():
            for remaining in range(rest_time - 1, -1, -1):
                # Check if timer was cancelled
                if not context.chat_data.get('current_timer', {}).get('is_active', False):
                    logger.info("Timer was cancelled, exiting timer loop")
                    break
                    
                await asyncio.sleep(1)
                try:
                    if remaining > 0:
                        await timer_message.edit_text(f"⏱ {timer_type}: {remaining} сек")
                    else:
                        # Just delete the message when timer is done
                        await timer_message.delete()
                        if 'timer_messages' in context.chat_data:
                            try:
                                context.chat_data['timer_messages'].remove(timer_message.message_id)
                            except ValueError:
                                pass
                        
                        # Auto-progress only if timer wasn't cancelled
                        if context.chat_data.get('current_timer', {}).get('is_active', False):
                            # Clear timer flag
                            context.chat_data['current_timer']['is_active'] = False
                            
                            # Get workout and auto-progress
                            workout = self.db.get_active_workout(user_id)
                            if workout:
                                # Update the workout state
                                if workout['workout_type'] == 'bodyweight':
                                    # Simulate exercise_done callback
                                    new_update = Update.de_json(
                                        {
                                            'callback_query': {
                                                'id': query.id,
                                                'from': query.from_user.to_dict(),
                                                'message': query.message.to_dict(),
                                                'chat_instance': query.chat_instance,
                                                'data': 'exercise_done'
                                            }
                                        },
                                        context.bot
                                    )
                                    # Process as if user clicked "exercise done"
                                    await self.handle_gym_workout_callback(new_update, context)
                                else:
                                    # Simulate set_done callback for gym workouts
                                    new_update = Update.de_json(
                                        {
                                            'callback_query': {
                                                'id': query.id,
                                                'from': query.from_user.to_dict(),
                                                'message': query.message.to_dict(),
                                                'chat_instance': query.chat_instance,
                                                'data': 'set_done'
                                            }
                                        },
                                        context.bot
                                    )
                                    # Process as if user clicked "set done"
                                    await self.handle_gym_workout_callback(new_update, context)
                except Exception as e:
                    logger.error(f"Error in timer update: {e}")
                    break
        
        # Start timer in background
        asyncio.create_task(update_timer())

    async def handle_gym_workout_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle workout callbacks"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        workout = self.db.get_active_workout(user_id)

        if not workout:
            await query.message.reply_text(
                "Тренировка не найдена. Используйте /workout для получения программы."
            )
            return

        # Handle exercise timer
        if query.data.startswith("exercise_timer_"):
            time = int(query.data.split('_')[2])
            await self.handle_exercise_timer(update, context, time)
            return

        # Mark any running timer as cancelled so it doesn't auto-progress
        if 'current_timer' in context.chat_data:
            context.chat_data['current_timer']['is_active'] = False

        # Clean up any active timer messages when proceeding with workout
        if 'timer_messages' in context.chat_data:
            for msg_id in context.chat_data['timer_messages'][:]:  # Create a copy of the list to iterate
                try:
                    # Try to delete the message
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
                except Exception:
                    pass  # Message might be already deleted
                try:
                    context.chat_data['timer_messages'].remove(msg_id)
                except ValueError:
                    pass
            
        # Convert Decimal values to int
        current_exercise_idx = int(workout['current_exercise'])
        total_exercises = int(workout['total_exercises'])

        if workout['workout_type'] == 'bodyweight':
            current_circuit = int(workout.get('current_circuit', 1))
            exercise = workout['exercises'][current_exercise_idx]
            total_circuits = int(exercise.get('circuits', 3))

            if query.data == "exercise_done":
                if current_exercise_idx < total_exercises - 1:
                    # Move to next exercise in current circuit
                    workout['current_exercise'] = current_exercise_idx + 1
                    self.db.save_active_workout(user_id, workout)
                    # Delete previous exercise message
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await self._show_gym_exercise(update, context)
                else:
                    # Last exercise in circuit completed
                    if current_circuit < total_circuits:
                        # Start next circuit from first exercise
                        workout['current_exercise'] = 0
                        workout['current_circuit'] = current_circuit + 1
                        self.db.save_active_workout(user_id, workout)
                        # Delete previous exercise message
                        try:
                            await query.message.delete()
                        except Exception:
                            pass
                        await self._show_gym_exercise(update, context)
                    else:
                        # All circuits completed
                        await self._finish_workout(update, context)

            elif query.data.startswith("circuit_rest_"):
                rest_time = int(query.data.split('_')[2])
                await self.handle_timer(update, context, "Отдых между кругами", rest_time)

            elif query.data.startswith("exercise_rest_"):
                rest_time = int(query.data.split('_')[2])
                await self.handle_timer(update, context, "Отдых между упражнениями", rest_time)

        else:
            # Gym workout callback handling
            if query.data == "set_done":
                exercise = workout['exercises'][current_exercise_idx]
                current_set = int(exercise.get('current_set', 1))
                total_sets = int(exercise.get('sets', 3))

                if current_set < total_sets:
                    exercise['current_set'] = current_set + 1
                    self.db.save_active_workout(user_id, workout)
                    # Delete previous exercise message
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await self._show_gym_exercise(update, context)
                else:
                    if current_exercise_idx < total_exercises - 1:
                        workout['current_exercise'] = current_exercise_idx + 1
                        workout['exercises'][current_exercise_idx + 1]['current_set'] = 1
                        self.db.save_active_workout(user_id, workout)
                        # Delete previous exercise message
                        try:
                            await query.message.delete()
                        except Exception:
                            pass
                        await self._show_gym_exercise(update, context)
                    else:
                        await self._finish_workout(update, context)

            elif query.data.startswith("rest_"):
                rest_time = int(query.data.split('_')[1])
                await self.handle_timer(update, context, "Отдых", rest_time)

        if query.data == "prev_exercise" and current_exercise_idx > 0:
            workout['current_exercise'] = current_exercise_idx - 1
            self.db.save_active_workout(user_id, workout)
            # Delete previous exercise message
            try:
                await query.message.delete()
            except Exception:
                pass
            await self._show_gym_exercise(update, context)

        elif query.data == "next_exercise" and current_exercise_idx < total_exercises - 1:
            workout['current_exercise'] = current_exercise_idx + 1
            self.db.save_active_workout(user_id, workout)
            # Delete previous exercise message
            try:
                await query.message.delete()
            except Exception:
                pass
            await self._show_gym_exercise(update, context)

        elif query.data == "finish_workout":
            await self._finish_workout(update, context)

    async def handle_exercise_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exercise_time: int):
        """Handle exercise duration timer"""
        query = update.callback_query
        user_id = update.effective_user.id
        logger.info(f"Starting exercise timer for {exercise_time} seconds")

        # Send initial timer message
        timer_message = await query.message.reply_text(
            "🏃‍♂️ Начинаем упражнение!\n"
            f"⏱ Осталось: {exercise_time} сек"
        )
        logger.info("Timer message sent")

        # Store message ID in context for later deletion
        if 'timer_messages' not in context.chat_data:
            context.chat_data['timer_messages'] = []
        context.chat_data['timer_messages'].append(timer_message.message_id)
        
        # Store timer data for auto-progress
        timer_data = {
            'user_id': user_id,
            'original_message_id': query.message.message_id,
            'chat_id': query.message.chat_id,
            'is_active': True
        }
        context.chat_data['current_timer'] = timer_data
        
        async def update_exercise_timer():
            for remaining in range(exercise_time - 1, -1, -1):
                # Check if timer was cancelled
                if not context.chat_data.get('current_timer', {}).get('is_active', False):
                    logger.info("Exercise timer was cancelled, exiting timer loop")
                    break
                
                await asyncio.sleep(1)
                try:
                    if remaining > 0:
                        await timer_message.edit_text(
                            "🏃‍♂️ Продолжайте упражнение!\n"
                            f"⏱ Осталось: {remaining} сек"
                        )
                        logger.debug(f"Timer updated: {remaining} seconds remaining")
                    else:
                        # Just delete the timer message when done
                        await timer_message.delete()
                        if 'timer_messages' in context.chat_data:
                            try:
                                context.chat_data['timer_messages'].remove(timer_message.message_id)
                            except ValueError:
                                pass
                        logger.info("Exercise timer completed")
                        
                        # Auto-progress only if timer wasn't cancelled
                        if context.chat_data.get('current_timer', {}).get('is_active', False):
                            # Clear timer flag
                            context.chat_data['current_timer']['is_active'] = False
                            
                            # Simulate exercise_done callback
                            new_update = Update.de_json(
                                {
                                    'callback_query': {
                                        'id': query.id,
                                        'from': query.from_user.to_dict(),
                                        'message': query.message.to_dict(),
                                        'chat_instance': query.chat_instance,
                                        'data': 'exercise_done'
                                    }
                                },
                                context.bot
                            )
                            # Process as if user clicked "exercise done"
                            await self.handle_gym_workout_callback(new_update, context)
                except Exception as e:
                    logger.error(f"Error updating timer at {remaining} seconds: {str(e)}", exc_info=True)
                    break
        
        # Start timer in background
        asyncio.create_task(update_exercise_timer())
        logger.info("Exercise timer task created")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command and deep linking"""
        try:
            user_id = update.effective_user.id
            message_text = messages.WELCOME_MESSAGE
            
            # Проверяем, есть ли параметры глубоких ссылок (deep linking)
            if context.args and len(context.args) > 0:
                deep_link_payload = context.args[0]
                logger.info(f"Получена глубокая ссылка: {deep_link_payload}")
                
                # Обработка возврата с платежа
                if deep_link_payload.startswith('payment_'):
                    # Проверяем статус платежа через payment_manager
                    payment_result = self.payment_manager.handle_payment_callback(deep_link_payload)
                    
                    if payment_result:
                        if payment_result.get('success'):
                            await update.message.reply_text(
                                f"🎉 {payment_result['message']}\n\n"
                                f"Теперь у вас есть доступ ко всем функциям бота!",
                                reply_markup=get_back_to_main_keyboard()
                            )
                        else:
                            # Если платеж не успешен, даем возможность проверить еще раз
                            payment_id = payment_result.get('payment_id')
                            if payment_id:
                                await update.message.reply_text(
                                    f"⚠️ {payment_result['message']}",
                                    reply_markup=get_check_payment_keyboard(payment_id)
                                )
                            else:
                                await update.message.reply_text(
                                    f"⚠️ {payment_result['message']}",
                                    reply_markup=get_subscription_keyboard()
                                )
                        # Не показываем приветственное сообщение после обработки платежа
                        return
            
            await update.message.reply_text(message_text)
            logger.info(f"User {update.effective_user.id} started the bot")
        except Exception as e:
            logger.error(f"Error in start handler: {e}")
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте еще раз.")

    async def view_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View existing profile"""
        user_id = update.effective_user.id
        logger.info(f"Viewing profile for user {user_id}")
        profile = self.db.get_user_profile(user_id)
        logger.info(f"Retrieved profile data: {profile}")

        if not profile:
            logger.warning(f"No profile found for user {user_id}")
            await update.message.reply_text(
                "У вас еще нет профиля. Используйте /profile чтобы создать его."
            )
            return

        # Format profile data
        profile_text = "🏋️‍♂️ Ваш профиль:\n\n"
        profile_text += f"📊 Возраст: {profile['age']} лет\n"
        profile_text += f"📏 Рост: {profile['height']} см\n"
        profile_text += f"⚖️ Вес: {profile['weight']} кг\n"
        profile_text += f"👤 Пол: {profile['sex']}\n"
        profile_text += f"🎯 Цели: {profile['goals']}\n"
        profile_text += f"💪 Уровень подготовки: {profile['fitness_level']}\n"
        profile_text += f"🏋️ Оборудование: {profile['equipment']}\n"

        # Add update option
        keyboard = [[InlineKeyboardButton("🔄 Обновить профиль", callback_data="update_profile_full")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(profile_text, reply_markup=reply_markup)
        logger.info(f"Successfully displayed profile for user {user_id}")

    async def start_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the profile creation process"""
        user_id = update.effective_user.id
        logger.info(f"Starting profile process for user {user_id}")
        profile = self.db.get_user_profile(user_id)

        logger.info(f"Retrieved user profile - ID: {user_id}, Profile: {profile}")

        if profile:
            # If profile exists, ask if user wants to update
            keyboard = [
                [InlineKeyboardButton("✅ Да, обновить все поля", callback_data="update_profile_full")],
                [InlineKeyboardButton("❌ Нет, оставить текущий", callback_data="keep_profile")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info(f"Existing profile check result: {bool(profile)}")
            await update.message.reply_text(
                "У вас уже есть профиль. Хотите обновить его?",
                reply_markup=reply_markup
            )
            logger.info(f"Displayed existing profile with update options for user {user_id}")
            return ConversationHandler.END

        # Clear any existing user data
        context.user_data.clear()
        await update.message.reply_text(messages.PROFILE_PROMPTS['age'])
        return AGE

    async def age(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle age input"""
        try:
            age = int(update.message.text)
            if 12 <= age <= 100:
                context.user_data['age'] = age
                await update.message.reply_text(messages.PROFILE_PROMPTS['height'])
                return HEIGHT
            else:
                await update.message.reply_text(messages.INVALID_AGE)
                return AGE
        except ValueError:
            await update.message.reply_text(messages.INVALID_AGE)
            return AGE

    async def height(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle height input"""
        try:
            height = int(update.message.text)
            if 100 <= height <= 250:
                context.user_data['height'] = height
                await update.message.reply_text(messages.PROFILE_PROMPTS['weight'])
                return WEIGHT
            else:
                await update.message.reply_text(messages.INVALID_HEIGHT)
                return HEIGHT
        except ValueError:
            await update.message.reply_text(messages.INVALID_HEIGHT)
            return HEIGHT

    async def weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle weight input"""
        try:
            weight = float(update.message.text)
            if 30 <= weight <= 250:
                context.user_data['weight'] = weight
                await update.message.reply_text(
                    messages.PROFILE_PROMPTS['sex'],
                    reply_markup=get_sex_keyboard()
                )
                return SEX
            else:
                await update.message.reply_text(messages.INVALID_WEIGHT)
                return WEIGHT
        except ValueError:
            await update.message.reply_text(messages.INVALID_WEIGHT)
            return WEIGHT

    async def sex(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sex selection"""
        sex = update.message.text
        if sex in ['Мужской', 'Женский']:
            context.user_data['sex'] = sex
            await update.message.reply_text(
                messages.PROFILE_PROMPTS['goals'],
                reply_markup=get_goals_keyboard()
            )
            return GOALS
        else:
            await update.message.reply_text(messages.INVALID_INPUT)
            return SEX

    async def goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle fitness goals selection"""
        goals = update.message.text
        context.user_data['goals'] = goals
        await update.message.reply_text(
            messages.PROFILE_PROMPTS['fitness_level'],
            reply_markup=get_fitness_level_keyboard()
        )
        return FITNESS_LEVEL

    async def fitness_level(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle fitness level selection"""
        level = update.message.text
        context.user_data['fitness_level'] = level
        await update.message.reply_text(
            messages.PROFILE_PROMPTS['equipment'],
            reply_markup=get_equipment_keyboard()
        )
        return EQUIPMENT

    async def equipment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle equipment selection and complete profile"""
        equipment = update.message.text
        context.user_data['equipment'] = equipment

        # Save profile to database
        await self.save_profile(update.effective_user.id, context.user_data, update.effective_user.username)

        await update.message.reply_text(messages.PROFILE_COMPLETE)

        # If user has gym access, show muscle group options
        if 'зал' in equipment.lower():
            keyboard = [
                [
                    InlineKeyboardButton("Грудь + Бицепс", callback_data="muscle_грудь_бицепс"),
                    InlineKeyboardButton("Спина + Трицепс", callback_data="muscle_спина_трицепс")
                ],
                [InlineKeyboardButton("Ноги", callback_data="muscle_ноги")],
                [InlineKeyboardButton("Тренировка на все группы мышц", callback_data="muscle_все_группы")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Поскольку у вас есть доступ в спортзал, вы можете выбрать группу мышц для тренировки:",
                reply_markup=reply_markup
            )

        return ConversationHandler.END

    async def workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate and show workout preview"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text(
                "Пожалуйста, сначала создайте профиль с помощью команды /profile"
            )
            return

        equipment = profile.get('equipment', '').lower()
        if 'зал' in equipment:
            # Show muscle group selection for gym users
            keyboard = [
                [
                    InlineKeyboardButton("Грудь + Бицепс", callback_data="preview_грудь_бицепс"),
                    InlineKeyboardButton("Спина + Трицепс", callback_data="preview_спина_трицепс")
                ],
                [InlineKeyboardButton("Ноги", callback_data="preview_ноги")],
                [InlineKeyboardButton("Тренировка на все группы мышц", callback_data="preview_все_группы")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Выберите тип тренировки для предпросмотра:",
                reply_markup=reply_markup
            )
            return

        # For non-gym users, generate and show bodyweight workout preview
        workout = self.workout_manager.generate_bodyweight_workout(profile)
        self.db.save_preview_workout(user_id, workout)
        overview = self.workout_manager._generate_bodyweight_overview(workout, profile.get('goals', 'Общая физическая подготовка'))
        overview += "\n📱 Используйте /start_workout для начала тренировки"
        await update.message.reply_text(overview)

    async def start_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a workout session"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        # Get the previewed workout for any user type
        workout = self.db.get_preview_workout(user_id)
        
        # If no preview exists, check equipment and handle accordingly
        if not workout:
            equipment = profile.get('equipment', '').lower()
            if 'зал' in equipment:
                # For gym users, they need to preview a workout first
                keyboard = [
                    [
                        InlineKeyboardButton("Грудь + Бицепс", callback_data="preview_грудь_бицепс"),
                        InlineKeyboardButton("Спина + Трицепс", callback_data="preview_спина_трицепс")
                    ],
                    [InlineKeyboardButton("Ноги", callback_data="preview_ноги")],
                    [InlineKeyboardButton("Тренировка на все группы мышц", callback_data="preview_все_группы")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "Сначала выберите тип тренировки с помощью команды /workout:",
                    reply_markup=reply_markup
                )
                return
            else:
                # For bodyweight users, generate a new workout
                workout = self.workout_manager.generate_bodyweight_workout(profile)
        
        # Ensure workout starts from the first exercise
        workout['current_exercise'] = 0
        
        # For both gym and bodyweight users, start the workout
        self.db.start_active_workout(user_id, workout)
        await self._show_gym_exercise(update, context)

    async def check_subscription_middleware(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user has active subscription or is in trial period"""
        user_id = update.effective_user.id

        # Commands that don't require subscription check
        free_commands = ['/start', '/help', '/subscription', '/profile', '/premium']
        if update.message and update.message.text:
            command = update.message.text.split()[0]
            if command in free_commands:
                return True

        has_access = self.db.check_subscription_status(user_id)
        if not has_access:
            await update.message.reply_text(
                "⚠️ Ваш пробный период закончился или подписка истекла.\n"
                "Используйте команду /subscription для получения информации о подписке."
            )
            return False
        return True

    async def subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show subscription options"""
        user_id = update.effective_user.id
        
        # Check if payment system is enabled
        if not self.payment_manager.is_enabled():
            await update.message.reply_text(
                "Извините, платежная система временно недоступна. Пожалуйста, попробуйте позже."
            )
            return

        # Get current subscription status
        subscription = self.db.get_subscription(user_id)
        
        if subscription and subscription.get('active'):
            expiry_date = subscription.get('expiry_date', 'неизвестно')
            await update.message.reply_text(
                f"🎖 У вас активная подписка до {expiry_date}.\n\n"
                "Вы можете продлить подписку или отменить текущую.",
                reply_markup=get_subscription_keyboard()
            )
        else:
            await update.message.reply_text(
                "🔒 Подписка открывает доступ ко всем функциям бота:\n\n"
                "✅ Расширенные тренировки\n"
                "✅ Персональные программы\n"
                "✅ Статистика и аналитика\n\n"
                "Выберите действие:",
                reply_markup=get_subscription_keyboard()
            )

    async def handle_subscription_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from subscription buttons"""
        query = update.callback_query
        await query.answer()
        
        # Get the callback data
        callback_data = query.data
        
        # Process different subscription actions
        if callback_data == "subscription_plans":
            # Show subscription plans
            plans_keyboard = get_subscription_plans_keyboard()
            await query.message.edit_text(
                "Выберите план подписки:",
                reply_markup=plans_keyboard
            )
            
        elif callback_data == "subscription_cancel":
            # Cancel current subscription
            await query.message.edit_text(
                "Оформление подписки отменено. Вы можете вернуться к этому позже.",
                reply_markup=get_back_to_main_keyboard()
            )
            
        elif callback_data.startswith("plan_"):
            # Handle plan selection
            plan_type = callback_data.split("_")[1]  # monthly or yearly
            
            # Check if payment system is enabled
            if not self.payment_manager.is_enabled():
                await query.message.edit_text(
                    "Извините, платежная система временно недоступна. Пожалуйста, попробуйте позже.",
                    reply_markup=get_back_to_main_keyboard()
                )
                return
            
            # Save the selected plan in user data
            context.user_data['selected_plan'] = plan_type
            
            # Check if Telegram native payments are available
            if self.payment_manager.is_telegram_payment_enabled():
                # Use Telegram native payments
                user_id = query.from_user.id
                
                plans = self.payment_manager.get_subscription_plans()
                selected_plan = plans.get(plan_type, {"name": "Подписка", "price": 0})
                
                await query.message.edit_text(
                    f"💳 *Оплата {selected_plan['name']}*\n\n"
                    f"Стоимость: {selected_plan['price']} ₽\n\n"
                    "Сейчас вам будет выставлен счет для оплаты через Telegram. "
                    "Вы сможете оплатить подписку, не покидая приложение.",
                    parse_mode='Markdown'
                )
                
                # Create invoice parameters
                invoice_params = self.payment_manager.create_telegram_invoice(user_id, plan_type)
                
                if invoice_params:
                    # Send invoice to user
                    try:
                        await context.bot.send_invoice(
                            chat_id=user_id,
                            title=invoice_params["title"],
                            description=invoice_params["description"],
                            payload=invoice_params["payload"],
                            provider_token=invoice_params["provider_token"],
                            currency=invoice_params["currency"],
                            prices=invoice_params["prices"],
                            need_email=invoice_params.get("need_email", True),
                            send_email_to_provider=invoice_params.get("send_email_to_provider", True),
                            provider_data=invoice_params.get("provider_data")
                        )
                        logger.info(f"Sent Telegram invoice to user {user_id} for plan {plan_type}")
                    except Exception as e:
                        logger.error(f"Error sending Telegram invoice: {str(e)}")
                        # Fall back to regular payment method
                        await query.message.edit_text(
                            "Не удалось создать счет через Telegram. Пожалуйста, введите email для альтернативного способа оплаты:",
                        )
                        # Set conversation state to waiting for email
                        context.user_data['payment_state'] = self.WAITING_FOR_EMAIL
                else:
                    # Fall back to regular payment method if invoice creation failed
                    await query.message.edit_text(
                        "Для оформления платежа нам необходим ваш email адрес. "
                        "Он будет использован только для формирования чека.\n\n"
                        "Пожалуйста, введите ваш email:"
                    )
                    # Set conversation state to waiting for email
                    context.user_data['payment_state'] = self.WAITING_FOR_EMAIL
            else:
                # Use regular payment method with email collection
                await query.message.edit_text(
                    "Для оформления платежа нам необходим ваш email адрес. "
                    "Он будет использован только для формирования чека.\n\n"
                    "Пожалуйста, введите ваш email:"
                )
                # Set conversation state to waiting for email
                context.user_data['payment_state'] = self.WAITING_FOR_EMAIL
            
        elif callback_data.startswith("payment_"):
            parts = callback_data.split("_")
            action = parts[1]
            payment_id = parts[2] if len(parts) > 2 else None
            
            if action == "pay" and payment_id:
                # User clicked on the payment link, nothing to do here as the URL opens in browser
                pass
                
            elif action == "check" and payment_id:
                # Check payment status
                await self.check_payment_status(update, context)
                
            elif action == "cancel" and payment_id:
                # Cancel payment
                await query.message.edit_text(
                    "Платеж был отменен. Вы можете попробовать снова позже.",
                    reply_markup=get_subscription_keyboard()
                )

    async def pre_checkout_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pre-checkout queries from Telegram Payment"""
        query = update.pre_checkout_query
        
        # Extract payment info from payload
        payload = query.invoice_payload
        logger.info(f"Received pre-checkout query with payload: {payload}")
        
        # You can perform additional validation here if needed
        try:
            # Always approve the pre-checkout query for now
            await context.bot.answer_pre_checkout_query(
                pre_checkout_query_id=query.id,
                ok=True
            )
            logger.info(f"Pre-checkout query {query.id} approved")
        except Exception as e:
            logger.error(f"Error answering pre-checkout query: {str(e)}")
            # Try to reject the query with an error message
            try:
                await context.bot.answer_pre_checkout_query(
                    pre_checkout_query_id=query.id,
                    ok=False,
                    error_message="Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже."
                )
            except Exception as inner_e:
                logger.error(f"Error rejecting pre-checkout query: {str(inner_e)}")
    
    async def successful_payment_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle successful payments from Telegram Payment"""
        message = update.message
        payment_info = message.successful_payment
        user_id = update.effective_user.id
        
        logger.info(f"Received successful payment from user {user_id}")
        logger.info(f"Payment info: {payment_info.to_dict()}")
        
        # Process the payment and activate subscription
        success = self.payment_manager.process_successful_telegram_payment(user_id, payment_info.to_dict())
        
        if success:
            # Get subscription details
            subscription = self.db.get_subscription(user_id)
            expiry_date = subscription.get('expiry_date', 'неизвестно')
            
            await message.reply_text(
                f"🎉 Поздравляем! Ваш платеж успешно обработан!\n\n"
                f"Ваша подписка активна до {expiry_date}.\n"
                f"Теперь у вас есть доступ ко всем функциям бота.",
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await message.reply_text(
                "Платеж прошел успешно, но возникла ошибка при активации подписки. "
                "Пожалуйста, обратитесь в поддержку.",
                reply_markup=get_back_to_main_keyboard()
            )

    async def collect_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Collect email address for payment processing"""
        # First check if we're actually in the email collection state
        if not context.user_data.get('payment_state') == self.WAITING_FOR_EMAIL:
            # We're not in email collection state, so this message is for some other handler
            return
        
        email = update.message.text.strip()
        # Better email validation using regex
        if not EMAIL_REGEX.match(email):
            await update.message.reply_text(
                "Пожалуйста, введите корректный email адрес (например, user@example.com)."
            )
            return
            
        # Save email to user data
        context.user_data['email'] = email
        plan_type = context.user_data.get('selected_plan')
        
        if not plan_type:
            await update.message.reply_text(
                "Произошла ошибка. Пожалуйста, начните процесс подписки заново.",
                reply_markup=get_subscription_keyboard()
            )
            return
            
        # Create payment with the collected email
        try:
            payment_info = self.payment_manager.create_payment(
                update.effective_user.id, 
                plan_type,
                email=email
            )
            
            if payment_info:
                # Create keyboard with payment options
                payment_keyboard = get_payment_keyboard(
                    payment_info["payment_url"], 
                    payment_info["payment_id"]
                )
                
                plans = self.payment_manager.get_subscription_plans()
                selected_plan = plans.get(plan_type, {"name": "Подписка", "price": 0})
                
                await update.message.reply_text(
                    f"💳 *Оплата {selected_plan['name']}*\n\n"
                    f"Стоимость: {selected_plan['price']} ₽\n"
                    f"Email для чека: {email}\n\n"
                    "Нажмите на кнопку \"Оплатить\" для перехода на страницу оплаты.",
                    reply_markup=payment_keyboard,
                    parse_mode='Markdown'
                )
                
                # Reset payment state
                context.user_data.pop('payment_state', None)
            else:
                await update.message.reply_text(
                    "Извините, произошла ошибка при обработке вашего платежа. Пожалуйста, попробуйте позже.",
                    reply_markup=get_subscription_keyboard()
                )
        except Exception as e:
            logger.error(f"Payment creation error: {str(e)}")
            await update.message.reply_text(
                "Извините, произошла ошибка при обработке вашего платежа. Пожалуйста, попробуйте позже.",
                reply_markup=get_subscription_keyboard()
            )

    async def check_payment_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check payment status and activate subscription if paid"""
        # Handle both direct command and callback query
        if update.callback_query:
            query = update.callback_query
            callback_data = query.data
            parts = callback_data.split('_')
            
            if len(parts) >= 3 and parts[0] == 'payment' and parts[1] == 'check':
                payment_id = parts[2]
                logger.info(f"Checking payment status from callback for ID: {payment_id}")
                
                # Check payment status
                payment_data = self.payment_manager.check_payment_status(payment_id)
                
                if not payment_data:
                    await query.message.reply_text(
                        "Не удалось получить информацию об оплате. Пожалуйста, попробуйте позже.",
                        reply_markup=get_check_payment_keyboard(payment_id)
                    )
                    return
                
                if payment_data["status"] == "succeeded" or payment_data.get("paid", False):
                    # Process successful payment
                    success = self.payment_manager.process_successful_payment(payment_id)
                    
                    if success:
                        # Get subscription details
                        subscription = self.db.get_subscription(query.from_user.id)
                        expiry_date = subscription.get('expiry_date', 'неизвестно')
                        
                        await query.message.reply_text(
                            f"🎉 Поздравляем! Ваш платеж успешно обработан!\n\n"
                            f"Ваша подписка активна до {expiry_date}.\n"
                            f"Теперь у вас есть доступ ко всем функциям бота.",
                            reply_markup=get_back_to_main_keyboard()
                        )
                    else:
                        await query.message.reply_text(
                            "Платеж прошел успешно, но возникла ошибка при активации подписки. "
                            "Пожалуйста, обратитесь в поддержку.",
                            reply_markup=get_back_to_main_keyboard()
                        )
                else:
                    # Payment not yet successful, show status and check button
                    status_msg = f"Статус платежа: {payment_data['status']}.\n\n"
                    
                    if payment_data["status"] == "pending":
                        status_msg += "Платеж ожидает оплаты. Пожалуйста, завершите оплату или проверьте статус позже."
                    elif payment_data["status"] == "canceled":
                        status_msg += "Платеж был отменен. Вы можете попробовать снова."
                    elif payment_data["status"] == "waiting_for_capture":
                        status_msg += "Платеж ожидает подтверждения. Пожалуйста, проверьте статус позже."
                    else:
                        status_msg += "Пожалуйста, завершите оплату или проверьте статус позже."
                        
                    await query.message.reply_text(
                        status_msg,
                        reply_markup=get_check_payment_keyboard(payment_id)
                    )
            return

    async def handle_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle profile-related callbacks"""
        query = update.callback_query
        await query.answer()
        
        logger.info(f"Processing profile callback for user {update.effective_user.id}: {query.data}")

        if query.data == "update_profile" or query.data == "update_profile_full":
            # Clear existing data and start profile update
            context.user_data.clear()
            await query.message.reply_text(messages.PROFILE_PROMPTS['age'])
            return AGE
        elif query.data == "keep_profile":
            await query.message.reply_text("Хорошо, ваш профиль останется без изменений.")
            return ConversationHandler.END
        else:
            logger.warning(f"Unexpected callback data received: {query.data}")
            return ConversationHandler.END

    async def handle_progress_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle progress dashboard callbacks"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        try:
            if query.data == "back_to_dashboard":
                logger.info(f"User {user_id} returning to main dashboard")
                await self.show_progress(update, context)
                return

            # Get stats once at the beginning
            logger.info(f"Retrieving statistics for user {user_id}")
            stats = self.db.get_detailed_progress_stats(user_id)
            logger.info(f"Retrieved stats: {stats}")
            message = ""

            if query.data == "progress_weekly":
                logger.info("Processing weekly progress view")
                weekly_stats = stats['weekly_stats']
                message = "*📈 Прогресс по неделям*\n\n"
                for week, data in weekly_stats.items():
                    message += f"*{week}*\n"
                    message += f"• Тренировок: {data['workouts']}\n"
                    message += f"• Завершено: {data['completed']}\n"
                    message += f"• Эффективность: {data['completion_rate']}%\n\n"
                logger.info("Weekly progress view processed")

            elif query.data == "progress_monthly":
                logger.info("Processing monthly progress view")
                monthly_stats = stats['monthly_stats']
                message = "*📅 Месячный отчет*\n\n"
                for month, data in monthly_stats.items():
                    message += f"*{month}*\n"
                    message += f"• Тренировок: {data['workouts']}\n"
                    message += f"• Завершено: {data['completed']}\n"
                    message += f"• Эффективность: {data['completion_rate']}%\n\n"
                logger.info("Monthly progress view processed")

            elif query.data == "achievements":
                logger.info("Processing achievements view")
                message = "*🏆 Ваши достижения*\n\n"

                # Achievement criteria
                achievements = []
                if stats.get('total_workouts', 0) > 0:
                    achievements.append("🎯 Первая тренировка")
                if stats.get('total_workouts', 0) >= 10:
                    achievements.append("💪 Постоянство (10 тренировок)")
                if stats.get('streaks', {}).get('longest_streak', 0) >= 7:
                    achievements.append("🔥 Недельная серия")
                if stats.get('completion_rate', 0) >= 80:
                    achievements.append("⭐ Высокая эффективность (>80%)")

                if achievements:
                    message += "\n".join(achievements)
                else:
                    message += "Продолжайте тренироваться, чтобы получить достижения!"
                logger.info(f"Achievements processed: {achievements}")

            elif query.data == "workout_history":
                logger.info("Processing workout history view")
                workouts = self.db.get_user_progress(user_id)
                message = "*📋 История тренировок*\n\n"

                # Show last 5 workouts
                recent_workouts = workouts[-5:] if workouts else []
                logger.info(f"Found {len(recent_workouts)} recent workouts")

                for workout in recent_workouts:
                    date = workout['date']
                    completed = workout['exercises_completed']
                    total = workout['total_exercises']
                    message += f"📅 {date}\n"
                    message += f"• Выполнено: {completed}/{total} упражнений\n"
                    message += f"• Процент: {int((completed/total)*100)}%\n\n"

            elif query.data == "intensity_analysis":
                logger.info("Processing intensity analysis view")
                intensity_stats = self.db.get_workout_intensity_stats(user_id)
                message = "*💪 Анализ интенсивности*\n\n"

                if intensity_stats:
                    # Show last 7 days
                    recent_stats = intensity_stats[-7:]
                    logger.info(f"Processing {len(recent_stats)} days of intensity data")

                    for stat in recent_stats:
                        date = stat['date']
                        completion = stat['completion_rate']
                        intensity_bar = "▓" * (int(completion/10)) + "░" * (10 - int(completion/10))
                        message += f"📅 {date}\n"
                        message += f"{intensity_bar} {int(completion)}%\n\n"
                else:
                    message += "Пока нет данных для анализа интенсивности."

            # Add back button for all views
            keyboard = [[InlineKeyboardButton("🔙 Назад к дашборду", callback_data="back_to_dashboard")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            logger.info("Sending updated progress view")
            await query.message.edit_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Error handling progress callback: {str(e)}", exc_info=True)
            await query.message.reply_text(
                "Произошла ошибка при загрузке данных. Попробуйте позже."
            )

    async def handle_back_to_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back to main menu button presses"""
        query = update.callback_query
        await query.answer()
        
        # Edit the message to show a dashboard menu
        await query.message.edit_text(
            "🏠 Главное меню\n\n"
            "Выберите доступное действие из меню команд или воспользуйтесь кнопкой /help, "
            "чтобы увидеть список всех команд."
        )
        logger.info(f"User {query.from_user.id} returned to dashboard")
    
    async def error_handler(self, update, context):
        """Log Errors caused by Updates."""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Send a message to the user if this is a message or callback update
        if update and (update.message or update.callback_query):
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            error_message = (
                "😓 Произошла ошибка при обработке вашего запроса.\n"
                "Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
            )
            
            try:
                if update.callback_query:
                    await update.callback_query.message.reply_text(error_message)
                else:
                    await update.message.reply_text(error_message)
                    
                logger.info(f"Sent error notification to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
                
        # Log the error with traceback for debugging
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = ''.join(tb_list)
        logger.error(f"Traceback: {tb_string}")

    async def show_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /calendar command"""
        try:
            user_id = update.effective_user.id
            logger.info(f"Received /calendar command from user {user_id}")

            now = datetime.now()
            logger.info(f"Generating calendar for {now.year}-{now.month}")

            # Get workouts for current month
            start_date = now.replace(day=1).date()
            end_date = now.date()

            workouts = self.db.get_workouts_by_date(user_id, start_date, end_date)
            logger.info(f"Retrieved {len(workouts) if workouts else 0} workouts for calendar")

            # Generate calendar keyboard
            keyboard = get_calendar_keyboard(now.year, now.month, workouts)
            logger.info("Calendar keyboard generated successfully")

            # Send calendar message
            await update.message.reply_text(
                messages.CALENDAR_HELP,
                reply_markup=keyboard
            )
            logger.info("Calendar displayed successfully")
        except Exception as e:
            logger.error(f"Error showing calendar: {str(e)}", exc_info=True)
            await update.message.reply_text("Произошла ошибка при отображении календаря. Попробуйте позже.")

    async def handle_calendar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle calendar navigation and date selection"""
        query = update.callback_query
        await query.answer()
        logger.info(f"Received calendar callback: {query.data}")

        try:
            # Extract data from callback
            data = query.data.split('_')
            logger.info(f"Calendar callback data: {data}")

            if data[0] == 'calendar':
                # Handle month navigation
                year = int(data[1])
                month = int(data[2])
                logger.info(f"Navigating to calendar {year}-{month}")

                # Get workouts for the selected month
                start_date = datetime(year, month, 1).date()
                end_date = (datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)).date() - timedelta(days=1)

                workouts = self.db.get_workouts_by_date(query.from_user.id, start_date, end_date)
                logger.info(f"Retrieved {len(workouts) if workouts else 0} workouts for {year}-{month}")

                # Update calendar view
                calendar_keyboard = get_calendar_keyboard(year, month, workouts)
                await query.message.edit_reply_markup(reply_markup=calendar_keyboard)
                logger.info("Calendar view updated successfully")

            elif data[0] == 'date':
                # Handle date selection
                selected_date = datetime.strptime(data[1], '%Y-%m-%d').date()
                logger.info(f"Selected date: {selected_date}")

                workouts = self.db.get_workouts_by_date(query.from_user.id, selected_date, selected_date)
                logger.info(f"Found {len(workouts) if workouts else 0} workouts for selected date")

                if workouts:
                    # Show workouts for selected date
                    workout_details = f"📅 Тренировки {selected_date.strftime('%d.%m.%Y')}:\n\n"
                    for workout in workouts:
                        status = "✅" if workout.get('workout_completed') else "⭕"
                        completion = (workout['exercises_completed'] / workout['total_exercises'] * 100)
                        workout_details += (
                            f"{status} Упражнений: {workout['exercises_completed']}/{workout['total_exercises']}\n"
                            f"Завершенность: {completion:.1f}%\n\n"
                        )
                    await query.message.reply_text(workout_details)
                else:
                    await query.message.reply_text(f"На {selected_date.strftime('%d.%m.%Y')} тренировок не найдено.")

        except Exception as e:
            logger.error(f"Error handling calendar callback: {str(e)}", exc_info=True)
            await query.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

    async def set_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /reminder command"""
        user_id = update.effective_user.id
        logger.info(f"Setting reminder for user {user_id}")

        # Check if user already has a reminder
        current_reminder = self.db.get_reminder(user_id)

        if current_reminder:
            message = f"⏰ Текущее напоминание установлено на {current_reminder}\n"
            message += "Хотите изменить время?"
        else:
            message = "⏰ Выберите время для напоминаний о тренировке:"

        # Get reminder keyboard from keyboards.py
        keyboard = get_reminder_keyboard()
        await update.message.reply_text(message, reply_markup=keyboard)

    async def handle_reminder_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle reminder time selection"""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("reminder_"):
            time = query.data.split("_")[1]
            user_id = update.effective_user.id

            # Save reminder in database
            self.db.set_reminder(user_id, time)

            # Set up reminder in reminder manager
            self.reminder_manager.set_reminder(user_id, time)

            await query.message.edit_text(
                f"✅ Напоминание установлено на {time}\n"
                "Бот будет напоминать вам о тренировке каждый день в это время."
            )
            logger.info(f"Reminder set to {time} for user {user_id}")

    async def muscle_group_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle muscle group specific workout commands"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        equipment = profile.get('equipment', '').lower()
        if 'зал' not in equipment:
            await update.message.reply_text(
                "Эта функция доступна только для тренировок в зале. "
                "Убедитесь, что в вашем профиле указано наличие тренажерного зала."
            )
            return

        # Determine which muscle group workout was requested
        command = update.message.text[1:] # Remove the '/' from command
        muscle_group_map = {
            'chest_biceps': 'грудь_бицепс',
            'back_triceps': 'спина_трицепс',
            'legs': 'ноги'
        }

        muscle_group = muscle_group_map.get(command)
        if not muscle_group:
            await update.message.reply_text(
                "Неверная команда. Используйте:\n"
                "/chest_biceps - для тренировки груди и бицепса\n"
                "/back_triceps - для тренировки спины и трицепса\n"
                "/legs - для тренировки ног"
            )
            return

        # Generate and cache the workout
        workout = self.workout_manager.generate_muscle_group_workout(profile, muscle_group)
        self.db.save_preview_workout(user_id, workout)

        # Generate overview
        overview = self.workout_manager._generate_gym_overview(workout)
        await update.message.reply_text(overview)

    async def create_muscle_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /create_muscle_workout command"""
        logger.info(f"User {update.effective_user.id} requested muscle workout creation")
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            logger.warning(f"No profile found for user {user_id}")
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        equipment = profile.get('equipment', '').lower()
        if 'зал' not in equipment:
            logger.warning(f"User {user_id} attempted muscle workout without gym equipment")
            await update.message.reply_text(
                "Эта функция доступна только для тренировок в зале. "
                "Убедитесь, что в вашем профиле указано наличие тренажерного зала."
            )
            return

        # Create keyboard with muscle group options
        keyboard = [
            [
                InlineKeyboardButton("Грудь + Бицепс", callback_data="muscle_грудь_бицепс"),
                InlineKeyboardButton("Спина + Трицепс", callback_data="muscle_спина_трицепс")
            ],
            [InlineKeyboardButton("Ноги", callback_data="muscle_ноги")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        logger.info(f"Showing muscle group selection buttons to user {user_id}")
        await update.message.reply_text(
            "Выберите группу мышц для тренировки:",
            reply_markup=reply_markup
        )

    async def handle_muscle_group_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle muscle group selection callback"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        logger.info(f"User {user_id} selected muscle group: {query.data}")

        profile = self.db.get_user_profile(user_id)
        if not profile:
            logger.warning(f"No profile found for user {user_id} during muscle group selection")
            await query.message.reply_text("Сначала создайте профиль командой /profile")
            return

        # Extract muscle group from callback data
        callback_type, muscle_group = query.data.split('_', 1)  # Split into type and muscle group
        logger.info(f"Callback type: {callback_type}, muscle group: {muscle_group}")

        try:
            # Generate workout based on selection
            if muscle_group == 'все_группы':
                workout = self.workout_manager.generate_gym_workout(profile, user_id)
            else:
                workout = self.workout_manager.generate_muscle_group_workout(profile, muscle_group, user_id)

            if not workout:
                logger.error(f"Failed to generate workout for muscle group: {muscle_group}")
                await query.message.reply_text("Не удалось создать тренировку. Попробуйте еще раз.")
                return

            # Ensure workout starts from the first exercise
            workout['current_exercise'] = 0
            
            if callback_type == 'preview':
                # Save as preview and show overview
                self.db.save_preview_workout(user_id, workout)
                overview = self.workout_manager._generate_gym_overview(workout)
                overview += "\n📱 Используйте /start_workout для начала тренировки"
                await query.message.edit_text(overview)
            else:
                # Start workout immediately
                self.db.start_active_workout(user_id, workout)
                await query.message.delete()
                await self._show_gym_exercise(update, context)

        except Exception as e:
            logger.error(f"Error generating muscle group workout: {str(e)}", exc_info=True)
            await query.message.reply_text(
                "Произошла ошибка при создании тренировки. Пожалуйста, попробуйте позже."
            )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel and end the conversation."""
        await update.message.reply_text(
            "Операция отменена. Используйте /help чтобы увидеть доступные команды."
        )
        return ConversationHandler.END

    async def save_profile(self, user_id, profile_data, telegram_handle=None):
        """Save user profile with trial period initialization"""
        self.db.save_user_profile(user_id, profile_data, telegram_handle)

        # Initialize trial subscription
        trial_start = datetime.now()
        trial_end = trial_start + timedelta(days=10)
        subscription_data = {
            'active': False,
            'trial_start': trial_start.strftime('%Y-%m-%d'),
            'trial_end': trial_end.strftime('%Y-%m-%d'),
        }
        self.db.save_subscription(user_id, subscription_data)

    def get_handlers(self):
        """Return all handlers for the bot"""
        return [
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("view_profile", self.view_profile),
            CommandHandler("workout", self.workout),
            CommandHandler("start_workout", self.start_workout),
            CommandHandler("progress", self.show_progress),
            CommandHandler("calendar", self.show_calendar),
            CommandHandler("reminder", self.set_reminder),
            CommandHandler("subscription", self.subscription),
            # Add handler for email collection - just intercept ALL text messages and filter in the handler
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_email),
            # Add workout feedback handler
            CallbackQueryHandler(
                self.handle_workout_feedback,
                pattern="^feedback_"
            ),
            CommandHandler('premium', self.premium_access)
        ]
    
    # We'll keep this method for reference but not use it directly in filters
    def in_payment_email_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user is in email collection state"""
        return context.user_data.get('payment_state') == self.WAITING_FOR_EMAIL

    def register_handlers(self, application):
        """Register all handlers with the application"""
        # Register command handlers
        for handler in self.get_handlers():
            application.add_handler(handler)
            
        # Add custom error handler
        application.add_error_handler(self.error_handler)
        
        # Create profile conversation handler
        profile_handler = ConversationHandler(
            entry_points=[
                CommandHandler('profile', self.start_profile)
            ],
            states={
                # States are defined as class variables
                self.PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_profile_input)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_profile)]
        )
        application.add_handler(profile_handler)
        
        # Add various callback query handlers
        application.add_handler(CallbackQueryHandler(self.handle_muscle_group_selection, pattern='^muscle_'))
        application.add_handler(CallbackQueryHandler(self.handle_calendar_callback, pattern='^(calendar|date)_'))
        application.add_handler(CallbackQueryHandler(self.handle_reminder_callback, pattern='^reminder_'))
        application.add_handler(CallbackQueryHandler(self.handle_workout_feedback, pattern='^feedback_'))
        application.add_handler(CallbackQueryHandler(self.handle_gym_workout_callback, pattern='^workout_'))
        application.add_handler(CallbackQueryHandler(self.handle_progress_callback, pattern='^progress_'))
        application.add_handler(CallbackQueryHandler(self.handle_profile_callback, pattern='^(update_profile|update_profile_full|keep_profile)$'))
        
        # Add payment and subscription handlers
        application.add_handler(CallbackQueryHandler(self.handle_subscription_callback, pattern='^subscription_'))
        application.add_handler(CallbackQueryHandler(self.handle_subscription_callback, pattern='^plan_'))
        application.add_handler(CallbackQueryHandler(self.check_payment_status, pattern='^payment_check_'))
        application.add_handler(CallbackQueryHandler(self.handle_subscription_callback, pattern='^payment_cancel_'))
        
        # Add Telegram payment handlers
        application.add_handler(PreCheckoutQueryHandler(self.pre_checkout_query_handler))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, self.successful_payment_handler))
        
        # Default back to main menu handler
        application.add_handler(CallbackQueryHandler(self.handle_back_to_dashboard, pattern='^back_to_main$'))
        
        logger.info("All handlers registered successfully")

    async def cancel_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel profile creation/editing"""
        await update.message.reply_text("Создание профиля отменено. Используйте /help чтобы увидеть доступные команды.")
        return ConversationHandler.END

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        await update.message.reply_text(messages.HELP_MESSAGE)

    async def handle_workout_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle workout feedback"""
        query = update.callback_query
        await query.answer()

        feedback_type = query.data.split('_')[1]
        user_id = update.effective_user.id

        # Initialize response variables with default values
        emotional_response = 'neutral'  # Default emotional state
        physical_response = 'ok'        # Default physical state

        # Map feedback to responses - only override the relevant state
        if feedback_type == 'fun':
            emotional_response = 'fun'
        elif feedback_type == 'not_fun':
            emotional_response = 'not_fun'
        elif feedback_type == 'too_easy':
            physical_response = 'too_easy'
        elif feedback_type == 'ok':
            physical_response = 'ok'
        elif feedback_type == 'tired':
            physical_response = 'tired'

        # Get workout ID from context
        workout_id = context.user_data.get('last_workout_id')
        if not workout_id:
            logger.warning(f"No workout_id found in context for user {user_id} when giving feedback")
            await update.effective_chat.send_message("Не удалось сохранить отзыв. Пожалуйста, попробуйте снова.")
            return

        # Save feedback with both emotional and physical states always filled
        feedback_data = {
            'user_id': user_id,
            'workout_id': workout_id,
            'emotional_state': emotional_response,
            'physical_state': physical_response,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'feedback_id': f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }

        logger.info(f"Attempting to save feedback for user {user_id}, workout {workout_id}")
        logger.info(f"Feedback data: {feedback_data}")
        
        success = self.db.save_workout_feedback(
            user_id,
            workout_id,
            feedback_data
        )

        if success:
            await update.effective_chat.send_message(
                "Спасибо за отзыв! Это поможет нам подобрать более подходящие тренировки."
            )
        else:
            logger.error(f"Failed to save feedback for user {user_id}, workout {workout_id}")
            await update.effective_chat.send_message(
                "Не удалось сохранить отзыв. Пожалуйста, попробуйте снова."
            )

    async def premium_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to manage premium access (add or remove users)"""
        user_id = update.effective_user.id
        
        # Debug logging for admin command
        logger.info(f"Premium command called by user {user_id}")
        
        # List of admin user IDs - should be moved to config in a real application
        admin_ids = ["5311473961", "413662602"]  # Convert to string for consistency
        
        if str(user_id) not in admin_ids:
            # Log unauthorized attempt
            logger.warning(f"Unauthorized premium command attempt by user {user_id}")
            await update.message.reply_text(
                "⛔ Извините, у вас нет доступа к этой команде."
            )
            return
            
        # Check if command has arguments
        if not context.args or len(context.args) < 2:
            logger.info(f"Admin {user_id} used premium command without proper arguments")
            await update.message.reply_text(
                "⚠️ Формат команды: /premium add|remove USER_ID"
            )
            return
            
        action = context.args[0].lower()
        target_user_id = context.args[1]
        
        logger.info(f"Admin {user_id} using premium command: {action} for user {target_user_id}")
        
        if action == "add":
            result = self.db.add_premium_status(target_user_id)
            if result:
                logger.info(f"Successfully added premium status to user {target_user_id}")
                await update.message.reply_text(f"✅ Премиум статус добавлен для пользователя {target_user_id}.")
            else:
                logger.error(f"Failed to add premium status to user {target_user_id}")
                await update.message.reply_text(f"❌ Не удалось добавить премиум статус. Возможно, профиль не существует.")
        elif action == "remove":
            result = self.db.remove_premium_status(target_user_id)
            if result:
                logger.info(f"Successfully removed premium status from user {target_user_id}")
                await update.message.reply_text(f"✅ Премиум статус удален для пользователя {target_user_id}.")
            else:
                logger.error(f"Failed to remove premium status from user {target_user_id}")
                await update.message.reply_text(f"❌ Не удалось удалить премиум статус.")
        else:
            logger.warning(f"Admin {user_id} used invalid action: {action}")
            await update.message.reply_text("⚠️ Неверная команда. Используйте 'add' или 'remove'.")

    def _safe_float_convert(self, value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0

    async def handle_profile_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user input during profile creation/update"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Determine what field we're collecting based on the state
        current_state = context.user_data.get('profile_state', None)
        profile_data = context.user_data.get('profile_data', {})
        
        if not current_state:
            await update.message.reply_text(
                "Извините, произошла ошибка. Пожалуйста, начните заново командой /profile"
            )
            return ConversationHandler.END
            
        if current_state == 'age':
            try:
                age = int(text)
                if age < 13 or age > 100:
                    await update.message.reply_text(
                        "Пожалуйста, введите корректный возраст (от 13 до 100 лет)."
                    )
                    return self.PROFILE
                profile_data['age'] = age
                
                # Next, ask for height
                await update.message.reply_text("Укажите ваш рост (в см):")
                context.user_data['profile_state'] = 'height'
                return self.PROFILE
                
            except ValueError:
                await update.message.reply_text(
                    "Пожалуйста, введите возраст числом."
                )
                return self.PROFILE
                
        elif current_state == 'height':
            try:
                height = self._safe_float_convert(text)
                if height < 100 or height > 250:
                    await update.message.reply_text(
                        "Пожалуйста, введите корректный рост (от 100 до 250 см)."
                    )
                    return self.PROFILE
                profile_data['height'] = height
                
                # Next, ask for weight
                await update.message.reply_text("Укажите ваш вес (в кг):")
                context.user_data['profile_state'] = 'weight'
                return self.PROFILE
                
            except ValueError:
                await update.message.reply_text(
                    "Пожалуйста, введите рост числом."
                )
                return self.PROFILE
                
        elif current_state == 'weight':
            try:
                weight = self._safe_float_convert(text)
                if weight < 30 or weight > 300:
                    await update.message.reply_text(
                        "Пожалуйста, введите корректный вес (от 30 до 300 кг)."
                    )
                    return self.PROFILE
                profile_data['weight'] = weight
                
                # Next, ask for sex
                await update.message.reply_text(
                    "Укажите ваш пол:",
                    reply_markup=get_sex_keyboard()
                )
                context.user_data['profile_state'] = 'sex'
                return self.PROFILE
                
            except ValueError:
                await update.message.reply_text(
                    "Пожалуйста, введите вес числом."
                )
                return self.PROFILE
                
        # ... other states like sex, goals, fitness_level, equipment would go here
                
        # Save the updated profile data
        context.user_data['profile_data'] = profile_data
        
        # If we've collected all fields, save the profile
        if current_state == 'equipment':
            # Save the complete profile
            await self.save_profile(user_id, profile_data, update.message.from_user.username)
            
            await update.message.reply_text(
                "Ваш профиль успешно сохранен! Теперь вы можете начать тренировки с помощью команды /workout.",
                reply_markup=get_back_to_main_keyboard()
            )
            return ConversationHandler.END
            
        return self.PROFILE
