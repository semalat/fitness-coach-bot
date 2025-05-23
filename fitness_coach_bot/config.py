# Bot configuration and constants
import os

# Telegram Bot Token
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# States for ConversationHandler
PROFILE = range(1, 8)
(
    AGE,
    HEIGHT,
    WEIGHT,
    SEX,
    GOALS,
    FITNESS_LEVEL,
    EQUIPMENT,
) = PROFILE

# Command list
COMMANDS = {
    'start': 'Начать работу с ботом',
    'profile': 'Создать или обновить профиль',
    'view_profile': 'Посмотреть текущий профиль',
    'workout': 'Получить тренировку',
    'start_workout': 'Начать интерактивную тренировку',
    'progress': 'Посмотреть прогресс',
    'calendar': 'Открыть календарь тренировок',
    'reminder': 'Установить напоминание',
    'subscription': 'Информация о подписке',
    'help': 'Получить помощь',
    # Admin commands - Hidden from regular users but available to admins
    'premium': 'Управление премиум-доступом (только для админов)',
}

SUBSCRIPTION_MESSAGE = """
В твою подписку входит:

📝 Персональные тренировочные планы под твой профиль
📊 Детальные отчеты о твоих тренировках
🏋 Адаптация тренировок в зависимости от фидбека
🏆 Отслеживание твоих достижений

🎁 Стоимость подписки составляет:
1 месяц: 300 RUB 
"""

# Fitness goals
FITNESS_GOALS = [
    "Похудение",
    "Набор мышечной массы",
    "Общая физическая подготовка"
]

# Fitness levels
FITNESS_LEVELS = [
    "Начинающий",
    "Средний",
    "Продвинутый"
]

# Equipment options
EQUIPMENT_OPTIONS = [
    "Только вес тела",
    "Доступ в спортзал"
]