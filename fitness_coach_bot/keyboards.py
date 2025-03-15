from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from fitness_coach_bot.config import FITNESS_GOALS, FITNESS_LEVELS, EQUIPMENT_OPTIONS
from datetime import datetime
import calendar

def get_sex_keyboard():
    """Return keyboard with sex options"""
    keyboard = [['Мужской', 'Женский']]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_goals_keyboard():
    """Return keyboard with fitness goals"""
    keyboard = [[goal] for goal in FITNESS_GOALS]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_fitness_level_keyboard():
    """Return keyboard with fitness levels"""
    keyboard = [[level] for level in FITNESS_LEVELS]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_equipment_keyboard():
    """Return keyboard with equipment options"""
    keyboard = [[option] for option in EQUIPMENT_OPTIONS]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_muscle_group_keyboard():
    """Return keyboard with available muscle groups"""
    muscle_groups = [
        ['Ноги', 'Пресс'],
        ['Руки', 'Спина'],
        ['Ягодицы']
    ]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(muscle, callback_data=f"muscle_{muscle.lower()}") 
         for muscle in row] 
        for row in muscle_groups
    ])

def get_workout_feedback_keyboard():
    """Return keyboard with workout feedback options"""
    keyboard = [
        [InlineKeyboardButton("😅 Слишком сложно", callback_data='feedback_too_hard')],
        [InlineKeyboardButton("👍 В самый раз", callback_data='feedback_good')],
        [InlineKeyboardButton("😴 Слишком легко", callback_data='feedback_too_easy')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reminder_keyboard():
    """Return keyboard with time options for reminders"""
    times = [
        ["07:00", "09:00", "11:00"],
        ["13:00", "15:00", "17:00"],
        ["19:00", "21:00"]
    ]
    keyboard = [
        [InlineKeyboardButton(time, callback_data=f"reminder_{time}") 
         for time in row] 
        for row in times
    ]
    return InlineKeyboardMarkup(keyboard)

def get_calendar_keyboard(year, month, workouts):
    """Return keyboard with calendar for specified month"""
    keyboard = []

    # Add month and year header
    month_name = calendar.month_name[month]
    keyboard.append([InlineKeyboardButton(f"{month_name} {year}", callback_data="ignore")])

    # Add day names header
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])

    # Get calendar for month
    cal = calendar.monthcalendar(year, month)
    workout_dates = {w['date'] for w in (workouts or [])}  # Handle None safely

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                # Empty day
                btn = InlineKeyboardButton(" ", callback_data="ignore")
            else:
                date = f"{year}-{month:02d}-{day:02d}"
                # Check if workout exists for this date
                if date in workout_dates:
                    # Find workout for this date to determine status
                    workout = next((w for w in workouts if w.get('date') == date), None)
                    if workout and workout.get('workout_completed', False):
                        btn = InlineKeyboardButton(f"💪{day}", callback_data=f"date_{date}")
                    else:
                        btn = InlineKeyboardButton(f"⭕{day}", callback_data=f"date_{date}")
                else:
                    btn = InlineKeyboardButton(f"{day}", callback_data=f"date_{date}")
            row.append(btn)
        keyboard.append(row)

    # Add navigation buttons
    nav_row = []
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    nav_row.extend([
        InlineKeyboardButton("◀️", callback_data=f"calendar_{prev_year}_{prev_month}"),
        InlineKeyboardButton("▶️", callback_data=f"calendar_{next_year}_{next_month}")
    ])
    keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)

def get_subscription_keyboard():
    """Keyboard for subscription menu"""
    keyboard = [
        [InlineKeyboardButton("Просмотреть тарифы", callback_data="subscription_plans")],
        [InlineKeyboardButton("Вернуться в главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_plans_keyboard():
    """Keyboard for subscription plans"""
    keyboard = [
        [InlineKeyboardButton("Месяц - 299 ₽", callback_data="plan_monthly")],
        [InlineKeyboardButton("Год - 999 ₽", callback_data="plan_yearly")],
        [InlineKeyboardButton("Назад", callback_data="subscription_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_keyboard(payment_url, payment_id):
    """Keyboard for payment options"""
    keyboard = [
        [InlineKeyboardButton("Оплатить", url=payment_url)],
        [InlineKeyboardButton("Проверить статус оплаты", callback_data=f"payment_check_{payment_id}")],
        [InlineKeyboardButton("Отменить", callback_data=f"payment_cancel_{payment_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_check_payment_keyboard(payment_id):
    """Keyboard for checking payment status"""
    keyboard = [
        [InlineKeyboardButton("Проверить еще раз", callback_data=f"payment_check_{payment_id}")],
        [InlineKeyboardButton("Вернуться к тарифам", callback_data="subscription_plans")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_main_keyboard():
    """Keyboard for going back to main menu"""
    keyboard = [
        [InlineKeyboardButton("Вернуться в главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

