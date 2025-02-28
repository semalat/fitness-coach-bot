import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Message
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, Application
)
import logging
import messages
from datetime import datetime, timedelta
from config import AGE, HEIGHT, WEIGHT, SEX, GOALS, FITNESS_LEVEL, EQUIPMENT
from keyboards import (
    get_sex_keyboard, get_goals_keyboard, get_fitness_level_keyboard,
    get_equipment_keyboard, get_calendar_keyboard, get_reminder_keyboard
)

logger = logging.getLogger(__name__)

class BotHandlers:
    def __init__(self, database, workout_manager, reminder_manager):
        self.db = database
        self.workout_manager = workout_manager
        self.reminder_manager = reminder_manager

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

        # Get the previewed workout or generate new if none exists
        workout = self.db.get_preview_workout(user_id)
        if not workout:
            logger.info(f"No preview workout found for user {user_id}, generating new workout")
            workout = self.workout_manager.generate_gym_workout(profile)
        else:
            logger.info(f"Using previewed workout for user {user_id}")

        self.db.start_active_workout(user_id, workout)
        self.db.clear_preview_workout(user_id)  # Clear the preview after starting
        await self._show_gym_exercise(update, context)

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

        exercise = workout['exercises'][workout['current_exercise']]
        current = workout['current_exercise'] + 1
        total = workout['total_exercises']

        # Build the message based on workout type
        if workout['workout_type'] == 'bodyweight':
            current_circuit = workout.get('current_circuit', 1)  # Track circuit globally
            total_circuits = exercise.get('circuits', 3)

            message = f"💪 Круг {current_circuit}/{total_circuits}\n"
            message += f"Упражнение {current}/{total}\n\n"
            message += f"📍 {exercise['name']}\n"
            message += f"🎯 Целевые мышцы: {exercise['target_muscle']}\n"
            message += f"⭐ Сложность: {exercise.get('difficulty', 'средний')}\n\n"

            if exercise.get('time', 0) > 0:
                message += f"⏱ Время: {exercise['time']} сек\n"
            else:
                message += f"🔄 Повторения: {exercise['reps']}\n"

            # Format rest times using workout-level circuits rest
            circuits_rest = workout['circuits_rest']  # Use workout-level circuits rest
            if circuits_rest >= 60:
                circuits_rest_str = f"{circuits_rest // 60} мин {circuits_rest % 60} сек"
            else:
                circuits_rest_str = f"{circuits_rest} сек"

            exercises_rest = exercise['exercises_rest']
            exercises_rest_str = f"{exercises_rest} сек"

            message += f"\n⏰ Отдых между кругами: {circuits_rest_str}"
            message += f"\n⏰ Отдых между упражнениями: {exercises_rest_str}"

            # Add instructions
            message += "\n\n📋 Как выполнять:"
            if exercise.get('time', 0) > 0:
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
            if exercise.get('time', 0) > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        "⏱ Старт упражнения",
                        callback_data=f"exercise_timer_{exercise['time']}"
                    )
                ])

            # Add completion button
            keyboard.append([InlineKeyboardButton("✅ Упражнение выполнено", callback_data="exercise_done")])

            # Add appropriate rest timer
            if workout['current_exercise'] == workout['total_exercises'] - 1:
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
            current_set = exercise.get('current_set', 1)
            total_sets = int(exercise.get('sets', 3))

            message = f"💪 Упражнение {current}/{total}\n\n"
            message += f"📍 {exercise['name']}\n"
            message += f"🎯 Целевые мышцы: {exercise['target_muscle']}\n"
            message += f"⭐ Сложность: {exercise.get('difficulty', 'средний')}\n\n"
            message += f"Сет {current_set}/{total_sets}\n"
            message += f"🔄 Повторения: {exercise['reps']}\n"

            if exercise.get('weight', 0) > 0:
                message += f"🏋️ Вес: {exercise['weight']} кг\n"

            message += f"\n⏰ Отдых между сетами: {exercise['sets_rest']} сек"

            # Add instructions
            message += "\n\n📋 Как выполнять:"
            message += "\n1️⃣ Выполните указанное количество повторений с заданным весом"
            message += "\n2️⃣ Нажмите '✅ Сет выполнен'"
            message += "\n3️⃣ Отдохните, нажав кнопку таймера"

            # Create keyboard
            keyboard = []

            # Add completion button
            keyboard.append([InlineKeyboardButton("✅ Сет выполнен", callback_data="set_done")])
            keyboard.append([
                InlineKeyboardButton(
                    f"⏰ Отдых {exercise['sets_rest']} сек",
                    callback_data=f"rest_{exercise['sets_rest']}"
                )
            ])


        # Add navigation buttons
        nav_buttons = []
        if workout['current_exercise'] > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущее", callback_data="prev_exercise"))
        if workout['current_exercise'] < workout['total_exercises'] - 1:
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
        """Complete the workout and save progress"""
        user_id = update.effective_user.id
        workout = self.db.get_active_workout(user_id)

        if workout:
            # Save workout completion in database
            completion_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'exercises_completed': workout['current_exercise'] + 1,
                'total_exercises': workout['total_exercises'],
                'workout_completed': True,
                'workout_id': f"workout_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            }

            self.db.save_workout_progress(user_id, completion_data)
            self.db.finish_active_workout(user_id)

            # Ask for feedback about the workout
            keyboard = [
                [
                    InlineKeyboardButton("😊 Было весело!", callback_data="feedback_fun"),
                    InlineKeyboardButton("😐 Не очень", callback_data="feedback_not_fun")
                ],
                [
                    InlineKeyboardButton("💪 Слишком легко", callback_data="feedback_too_easy"),
                    InlineKeyboardButton("👍 В самый раз", callback_data="feedback_ok"),
                    InlineKeyboardButton("😓 Устал(а)", callback_data="feedback_tired")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Delete the last exercise message
            if update.callback_query:
                try:
                    await update.callback_query.message.delete()
                except Exception:
                    pass

            message = (
                "🎉 Тренировка завершена!\n\n"
                f"✅ Выполнено упражнений: {completion_data['exercises_completed']}/{completion_data['total_exercises']}\n\n"
                "Как вам тренировка? Ваш отзыв поможет нам подобрать лучшую программу в следующий раз!"
            )

            # Store workout_id in context for feedback handling
            context.user_data['last_workout_id'] = completion_data['workout_id']

            if update.callback_query:
                await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message, reply_markup=reply_markup)

    async def handle_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, timer_type: str, rest_time: int):
        """Handle rest timer between sets/circuits"""
        query = update.callback_query
        # Delete only the timer message when done

        timer_message = await query.message.reply_text(f"⏱ {timer_type}: {rest_time} сек")

        for remaining in range(rest_time - 1, -1, -1):
            await asyncio.sleep(1)
            try:
                await timer_message.edit_text(f"⏱ {timer_type}: {remaining} сек")
            except Exception as e:
                logger.error(f"Error updating timer: {str(e)}")
                break

        # Delete only the timer message when done
        try:
            await timer_message.delete()
        except Exception:
            pass

        await query.message.reply_text(
            "✅ Отдых завершен!\n"
            "Готовы продолжить? Нажмите кнопку выполнения."
        )

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

        if workout['workout_type'] == 'bodyweight':
            current_circuit = workout.get('current_circuit', 1)
            exercise = workout['exercises'][workout['current_exercise']]
            total_circuits = exercise.get('circuits', 3)

            if query.data == "exercise_done":
                if workout['current_exercise'] < workout['total_exercises'] - 1:
                    # Move to next exercise in current circuit
                    workout['current_exercise'] += 1
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
                current_exercise = workout['exercises'][workout['current_exercise']]
                current_set = current_exercise.get('current_set', 1)
                total_sets = int(current_exercise.get('sets', 3))

                if current_set < total_sets:
                    current_exercise['current_set'] = current_set + 1
                    self.db.save_active_workout(user_id, workout)
                    # Delete previous exercise message
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await self._show_gym_exercise(update, context)
                else:
                    if workout['current_exercise'] < workout['total_exercises'] - 1:
                        workout['current_exercise'] += 1
                        workout['exercises'][workout['current_exercise']]['current_set'] = 1
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

        if query.data == "prev_exercise" and workout['current_exercise'] > 0:
            workout['current_exercise'] -= 1
            self.db.save_active_workout(user_id, workout)
            # Delete previous exercise message
            try:
                await query.message.delete()
            except Exception:
                pass
            await self._show_gym_exercise(update, context)

        elif query.data == "next_exercise" and workout['current_exercise'] < workout['total_exercises'] - 1:
            workout['current_exercise'] += 1
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
        logger.info(f"Starting exercise timer for {exercise_time} seconds")

        # Send initial timer message
        timer_message = await query.message.reply_text(
            "🏃‍♂️ Начинаем упражнение!\n"
            f"⏱ Осталось: {exercise_time} сек"
        )
        logger.info("Timer message sent")

        for remaining in range(exercise_time - 1, -1, -1):
            await asyncio.sleep(1)
            try:
                if remaining > 0:
                    await timer_message.edit_text(
                        "🏃‍♂️ Продолжайте упражнение!\n"
                        f"⏱ Осталось: {remaining} сек"
                    )
                    logger.debug(f"Timer updated: {remaining} seconds remaining")
                else:
                    await timer_message.edit_text("✅ Время упражнения истекло!")
                    logger.info("Exercise timer completed")
            except Exception as e:
                logger.error(f"Error updating timer at {remaining} seconds: {str(e)}", exc_info=True)
                break

        # Delete timer message after completion
        try:
            await timer_message.delete()
            logger.info("Timer message deleted")
        except Exception as e:
            logger.error(f"Error deleting timer message: {str(e)}", exc_info=True)

        completion_message = await query.message.reply_text(
            "Упражнение завершено!\n"
            "Нажмите '✅ Упражнение выполнено' для продолжения."
        )
        logger.info("Completion message sent")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        try:
            await update.message.reply_text(messages.WELCOME_MESSAGE)
            logger.info(f"User {update.effective_user.id} started the bot")
        except Exception as e:
            logger.error(f"Error in start handler: {e}")
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте еще раз.")

    async def view_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View existing profile"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
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
        keyboard = [[InlineKeyboardButton("🔄 Обновить профиль", callback_data="update_profile")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(profile_text, reply_markup=reply_markup)

    async def start_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the profile creation process or offer to update existing profile"""
        user_id = update.effective_user.id
        logger.info(f"Starting profile process for user {user_id}")
        profile = self.db.get_user_profile(user_id)

        if profile:
            logger.info(f"Existing profile found for user {user_id}, showing update options")
            # Format current profile data for preview
            profile_text = "🏋️‍♂️ Ваш текущий профиль:\n\n"
            profile_text += f"📊 Возраст: {profile['age']} лет\n"
            profile_text += f"📏 Рост: {profile['height']} см\n"
            profile_text += f"⚖️ Вес: {profile['weight']} кг\n"
            profile_text += f"👤 Пол: {profile['sex']}\n"
            profile_text += f"🎯 Цели: {profile['goals']}\n"
            profile_text += f"💪 Уровень подготовки: {profile['fitness_level']}\n"
            profile_text += f"🏋️ Оборудование: {profile['equipment']}\n\n"

            profile_text += "Хотите обновить свой профиль?"

            keyboard = [
                [InlineKeyboardButton("✅ Да, обновить", callback_data="update_profile")],
                [InlineKeyboardButton("❌ Нет, оставить текущий", callback_data="keep_profile")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                profile_text,
                reply_markup=reply_markup
            )
            logger.info(f"Sent profile update options to user {user_id}")
            return ConversationHandler.END

        logger.info(f"No existing profile found for user {user_id}, starting creation process")
        # No existing profile - start creation process
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
        self.db.save_user_profile(
            update.effective_user.id,
            context.user_data,
            update.effective_user.username
        )

        await update.message.reply_text(messages.PROFILE_COMPLETE)
        return ConversationHandler.END

    async def preview_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /workout command - show workout overview"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        # Generate and cache the workout
        equipment = profile.get('equipment', '').lower()
        goal = profile.get('goals', 'общая физическая подготовка').lower()

        if 'зал' in equipment:
            workout = self.workout_manager.generate_gym_workout(profile)
        else:
            workout = self.workout_manager.generate_bodyweight_workout(profile)

        # Save the preview workout
        self.db.save_preview_workout(user_id, workout)

        # Generate overview from the cached workout
        if 'зал' in equipment:
            overview = self.workout_manager._generate_gym_overview(workout)
        else:
            overview = self.workout_manager._generate_bodyweight_overview(workout, goal)

        await update.message.reply_text(overview)

    async def start_bodyweight_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a bodyweight workout session"""
        user_id = update.effective_user.id
        profile = self.db.get_user_profile(user_id)

        if not profile:
            await update.message.reply_text("Сначала создайте профиль командой /profile")
            return

        equipment = profile.get('equipment', '').lower()
        if 'зал' in equipment:
            await update.message.reply_text(
                "Ваш профильнастроен для тренировок в зале. "
                "Используйте /start_gym_workout для начала тренировки в зале."
            )
            return

        # Get the previewed workout or generate new if none exists
        workout = self.db.db.get_preview_workout(user_id)
        if not workout:
            logger.info(f"No preview workout found foruser {user_id}, generating new workout")
            workout = self.workout_manager.generate_bodyweight_workout(profile)
        else:
            logger.info(f"Using previewed workout for user {user_id}")

        self.db.start_active_workout(user_id, workout)
        self.db.clear_preview_workout(user_id)  # Clear the preview after starting
        await self._show_gym_exercise(update, context)


    async def handle_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle profile-related callback queries"""
        query = update.callback_query
        user_id = query.from_user.id
        logger.info(f"Received profile callback from user {user_id}: {query.data}")

        await query.answer()

        if query.data == "update_profile":
            logger.info(f"User {user_id} chose to update profile")
            # Start profile update process
            context.user_data.clear()
            await query.message.reply_text(messages.PROFILE_PROMPTS['age'])
            return AGE
        elif query.data == "keep_profile":
            logger.info(f"User {user_id} chose to keep current profile")
            await query.message.reply_text("👍 Хорошо, ваш профиль останется без изменений.")
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
        """Handle back to dashboard button"""
        query = update.callback_query
        await query.answer()

        if query.data == "back_to_dashboard":
            await self.show_progress(update, context)

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

    async def handle_calendar_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        command = update.message.text[1:]  # Remove the '/' from command
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

        # Add specific start command based on muscle group
        overview += "\n📱 Используйте /start_gym_workout для начала тренировки"

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
        muscle_group = query.data.split('_', 1)[1]  # Remove 'muscle_' prefix
        logger.info(f"Generating workout for muscle group: {muscle_group}")

        try:
            # Generate and cache the workout
            workout = self.workout_manager.generate_muscle_group_workout(profile, muscle_group)
            if not workout:
                logger.error(f"Failed to generate workout for muscle group: {muscle_group}")
                await query.message.reply_text("Не удалось создать тренировку. Попробуйте еще раз.")
                return

            self.db.save_preview_workout(user_id, workout)
            logger.info(f"Successfully generated and saved preview workout for user {user_id}")

            # Generate overview
            overview = self.workout_manager._generate_gym_overview(workout)
            overview += "\n📱 Используйте /start_gym_workout для начала тренировки"

            # Delete the selection message and send the workout overview
            await query.message.delete()
            await query.message.reply_text(overview)
            logger.info(f"Sent workout overview to user {user_id}")

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

    def get_handlers(self):
        """Return list of handlers to be registered"""
        logger.info("Configuring conversation handlers")
        # Create profile handler
        profile_handler = ConversationHandler(
            entry_points=[CommandHandler('profile', self.start_profile)],
            states={
                AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.age)],
                HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.height)],
                WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.weight)],
                SEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.sex)],
                GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.goals)],
                FITNESS_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.fitness_level)],
                EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.equipment)]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel),
                CallbackQueryHandler(self.handle_profile_callback, pattern='^(update_profile|keep_profile)$')
            ],
            name="profile_conversation",
            persistent=False
        )
        logger.info("Profile conversation handler configured")

        return [
            CommandHandler('start', self.start),
            profile_handler,  # Add profile handler here
            CommandHandler('view_profile', self.view_profile),
            CommandHandler('workout', self.preview_workout),
            CommandHandler('start_workout', self.start_bodyweight_workout),
            CommandHandler('start_gym_workout', self.start_gym_workout),
            CommandHandler('create_muscle_workout', self.create_muscle_workout),
            CommandHandler('progress', self.show_progress),
            CommandHandler('help', self.help_command),
            CommandHandler('calendar', self.show_calendar),
            CommandHandler('reminder', self.set_reminder),
            CallbackQueryHandler(self.handle_feedback, pattern='^feedback_'),
            CallbackQueryHandler(self.handle_muscle_group_selection, pattern='^muscle_')
        ]

    def register_handlers(self, application: Application):
        """Register all command handlers"""
        logger.info("Registering handlers with application")

        # Register all handlers from get_handlers
        for handler in self.get_handlers():
            application.add_handler(handler)
            logger.info(f"Registered handler: {handler.__class__.__name__}")

        # Add callback query handlers
        application.add_handler(CallbackQueryHandler(
            self.handle_calendar_selection,
            pattern=r"^calendar_"
        ))

        application.add_handler(CallbackQueryHandler(
            self.handle_gym_workout_callback,
            pattern=r"^(exercise_timer_|circuit_rest_|exercise_rest_|rest_|exercise_done|set_done|prev_exercise|next_exercise|finish_workout)"
        ))

        application.add_handler(CallbackQueryHandler(
            self.handle_reminder_callback,
            pattern=r"^reminder_"
        ))

        application.add_handler(CallbackQueryHandler(
            self.handle_progress_callback,
            pattern=r"^(progress_weekly|progress_monthly|achievements|workout_history|intensity_analysis|back_to_dashboard)$"
        ))

        logger.info("All handlers registered successfully")


    async def cancel_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel profile creation"""
        await update.message.reply_text(
            "Создание профиля отменено. Используйте /profile чтобы начать заново."
        )
        return ConversationHandler.END

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        await update.message.reply_text(messages.HELP_MESSAGE)

    async def handle_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle workout feedback"""
        query = update.callback_query
        await query.answer()

        feedback_type = query.data.split('_')[1]

        # Initialize response variables
        emotional_response = None
        physical_response = None

        # Map feedback to responses
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
            await query.message.reply_text("Не удалось сохранить отзыв. Пожалуйста, попробуйте снова.")
            return

        # Save feedback
        feedback_data = {
            'workout_id': workout_id,
            'emotional_state': emotional_response,
            'physical_state': physical_response,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        self.db.save_workout_feedback(
            update.effective_user.id,
            workout_id,
            feedback_data
        )

        await query.message.reply_text(
            "Спасибо за отзыв! Это поможет нам подобрать более подходящие тренировки."
        )