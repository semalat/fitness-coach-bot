import os
import logging
import uuid
from datetime import datetime, timedelta
import dotenv
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из .env файла
# Поиск .env файла в нескольких местах
env_paths = [
    '.env',                                # Текущая директория
    'fitness_coach_bot/.env',              # Поддиректория
    '../.env',                             # Родительская директория
    str(Path(__file__).parent.parent / '.env'),  # Относительно текущего файла
    # Keep test paths as fallback
    '.env.test',                                # Текущая директория
    'fitness_coach_bot/.env.test',              # Поддиректория
    '../.env.test',                             # Родительская директория
    str(Path(__file__).parent.parent / '.env.test')  # Относительно текущего файла
]

for env_path in env_paths:
    if os.path.exists(env_path):
        dotenv.load_dotenv(env_path)
        logger.info(f"Loaded environment variables from {env_path}")
        break
else:
    logger.warning("Could not find .env or .env.test file, using default credentials")

# Пытаемся импортировать YooKassa, но не останавливаем выполнение, если модуль не найден
try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
    logger.info("YooKassa module imported successfully")
except ImportError as e:
    logger.error(f"Error importing YooKassa: {str(e)}")
    YOOKASSA_AVAILABLE = False
    # Создаем пустые классы для избежания ошибок при инициализации
    class Configuration:
        account_id = None
        secret_key = None
    class Payment:
        @staticmethod
        def create(*args, **kwargs):
            return None
        @staticmethod
        def find_one(*args, **kwargs):
            return None

class PaymentManager:
    def __init__(self, database, bot_username=None):
        self.database = database
        self.bot_username = bot_username or os.getenv('TELEGRAM_BOT_USERNAME', 'your_bot_username')
        self.payment_enabled = False
        self.telegram_payment_enabled = False
        
        # Define subscription plans early (always define regardless of payment system status)
        self.plans = {
            "monthly": {"name": "Месячная подписка", "price": 299, "days": 30},
            "yearly": {"name": "Годовая подписка", "price": 999, "days": 365},
        }
        
        # Log environment variables for debugging
        logger.info(f"Available environment variables: {list(os.environ.keys())}")
        
        # Try multiple approaches to get the provider token
        self.provider_token = os.getenv('TELEGRAM_PROVIDER_TOKEN')
        logger.info(f"Provider token from os.getenv: {self.provider_token}")
        
        # If provider token is not in environment, try to read directly from .env.test
        if not self.provider_token:
            logger.info("Trying to read TELEGRAM_PROVIDER_TOKEN directly from .env.test")
            try:
                env_file_path = None
                for path in env_paths:
                    if os.path.exists(path):
                        env_file_path = path
                        logger.info(f"Found .env.test file at: {env_file_path}")
                        break
                
                if env_file_path:
                    # Print the content of the .env file for debugging
                    with open(env_file_path, 'r') as f:
                        env_contents = f.read()
                        logger.info(f"Contents of {env_file_path}:\n{env_contents}")
                    
                    # Try to extract the provider token using a more flexible approach
                    with open(env_file_path, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('TELEGRAM_PROVIDER_TOKEN'):
                                # Handle various formats like TOKEN=value, TOKEN = value, etc.
                                parts = line.split('=', 1)
                                if len(parts) == 2:
                                    value = parts[1].strip()
                                    # Remove quotes if present
                                    if (value.startswith('"') and value.endswith('"')) or \
                                       (value.startswith("'") and value.endswith("'")):
                                        value = value[1:-1]
                                    self.provider_token = value
                                    logger.info(f"Found TELEGRAM_PROVIDER_TOKEN in {env_file_path}: {self.provider_token}")
                                    break
            except Exception as e:
                logger.error(f"Error reading TELEGRAM_PROVIDER_TOKEN from file: {str(e)}")
        
        # If still not found, set it to Telegram's TEST provider token
        if not self.provider_token:
            logger.info("Provider token not found in environment or .env.test, using default TEST provider token")
            # This is Telegram's official test provider token
            self.provider_token = "381764678:TEST:54143"
            
        logger.info(f"Final TELEGRAM_PROVIDER_TOKEN: {self.provider_token}")
        
        # Если есть токен провайдера, включаем оплату через Telegram
        if self.provider_token:
            self.telegram_payment_enabled = True
            logger.info("Платежи через Telegram включены")
            # Test if this is a test provider token
            if "TEST:" in self.provider_token:
                logger.info("Using TEST provider token - test mode payments are enabled")
        else:
            logger.warning("Токен провайдера Telegram не найден, платежи через Telegram отключены")
        
        # Если модуль YooKassa недоступен, прекращаем инициализацию
        if not YOOKASSA_AVAILABLE:
            logger.error("YooKassa module is not available. Payment functions are disabled.")
            return
        
        # Инициализация конфигурации YooMoney
        shop_id = os.getenv('YOOMONEY_SHOP_ID')
        api_key = os.getenv('YOOMONEY_API_KEY')
        
        # Для тестирования: использовать тестовые значения, если переменные окружения не заданы
        if not shop_id:
            shop_id = "1051520"  # Тестовый ID магазина YooKassa из .env.test
            logger.info("Using test shop ID for development")
            
        if not api_key:
            api_key = "test_sc0b5Tc99pvpyb3F1_jxaFmT7ERC8GEvbv30bWB1Yfs"  # Тестовый ключ API YooKassa из .env.test
            logger.info("Using test API key for development")
        
        logger.info(f"PaymentManager initialization - Bot username: {self.bot_username}")
        logger.info(f"YooKassa credentials - Shop ID: {shop_id}, API Key exists: {bool(api_key)}")
        
        try:
            if shop_id and api_key:
                logger.info("Attempting to initialize YooKassa configuration...")
                Configuration.account_id = shop_id
                Configuration.secret_key = api_key
                self.payment_enabled = True
                logger.info("Платежная система YooMoney инициализирована успешно")
            else:
                logger.warning("YooKassa credentials missing: " + 
                              (f"Shop ID: {'Missing' if not shop_id else 'Present'}, " +
                               f"API Key: {'Missing' if not api_key else 'Present'}"))
                self.payment_enabled = False
                logger.warning("Учетные данные YooMoney не найдены, платежные функции отключены")
        except Exception as e:
            logger.error(f"Error initializing YooKassa: {str(e)}", exc_info=True)
            self.payment_enabled = False
            logger.warning("Платежные функции отключены из-за ошибки инициализации")
    
    def is_enabled(self):
        """Проверить, включена ли платежная система"""
        logger.info(f"Payment system enabled status: {self.payment_enabled}")
        return self.payment_enabled or self.telegram_payment_enabled
    
    def is_telegram_payment_enabled(self):
        """Проверить, включены ли платежи через Telegram"""
        return self.telegram_payment_enabled
    
    def get_subscription_plans(self):
        """Получить доступные тарифные планы"""
        return self.plans
    
    def create_telegram_invoice(self, user_id, plan_type, email=None):
        """Создать счет для оплаты через Telegram"""
        if not self.telegram_payment_enabled:
            logger.error("Платежи через Telegram не включены")
            return None
            
        if plan_type not in self.plans:
            logger.error(f"Неверный тип плана: {plan_type}")
            return None
            
        selected_plan = self.plans[plan_type]
        
        # Determine if we're in test mode by checking the provider token
        is_test_mode = "TEST:" in self.provider_token
        
        # Create a simplified payload for identification
        payment_payload = f"subscription_{plan_type}_{user_id}_{int(datetime.now().timestamp())}"
        logger.info(f"Created payment payload: {payment_payload}")
        
        if is_test_mode:
            logger.info("Using simplified payment data for test mode")
            # IMPORTANT: Use minimum valid amount for Telegram test payments - 100 RUB (10000 kopecks)
            # The minimum amount depends on the currency, for RUB it should be at least 100
            return {
                "provider_token": self.provider_token,
                "title": "Test Payment",
                "description": "Test Payment for Subscription",
                "payload": payment_payload,
                "currency": "RUB",
                "prices": [{"label": "Test", "amount": 10000}],  # 100 RUB in kopecks
                "start_parameter": "test_payment"
            }
            
        # Regular production mode - provide complete payment details
        # Сохраняем email в данных пользователя, если он предоставлен
        # Этот email будет использован при обработке успешного платежа
        if email:
            user_profile = self.database.get_user_profile(user_id)
            if not user_profile:
                user_profile = {}
            user_profile['email'] = email
            self.database.save_user_profile(user_id, user_profile)
            logger.info(f"Email {email} сохранен для пользователя {user_id}")
            
        # Store the selected plan in user data for reference during payment processing
        user_data = self.database.get_user_data(user_id) or {}
        user_data['selected_plan'] = plan_type
        self.database.save_user_data(user_id, user_data)
        logger.info(f"Selected plan '{plan_type}' saved for user {user_id}")
        
        # Возвращаем данные для создания счета через Telegram Bot API
        return {
            "provider_token": self.provider_token,
            "title": f"Фитнес-тренер бот - {selected_plan['name']}",
            "description": f"Подписка на {selected_plan['days']} дней",
            "payload": payment_payload,
            "currency": "RUB",
            "prices": [{"label": selected_plan['name'], "amount": selected_plan['price'] * 100}],  # Сумма в копейках
            "start_parameter": f"pay_{plan_type}",
            "need_email": True,  # Запрашиваем email для чека
            "send_email_to_provider": True,  # Отправляем email провайдеру
            "provider_data": {
                "receipt": {
                    "items": [
                        {
                            "description": selected_plan["name"],
                            "quantity": "1",
                            "amount": {
                                "value": selected_plan["price"],
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_subject": "service",
                            "payment_mode": "full_payment"
                        }
                    ],
                    "tax_system_code": 1  # Общая система налогообложения
                }
            }
        }

    def process_successful_telegram_payment(self, user_id, payment_info):
        """Обработать успешный платеж через Telegram"""
        try:
            logger.info(f"Обработка успешного платежа через Telegram для пользователя {user_id}")
            logger.info(f"Информация о платеже: {payment_info}")
            
            # Разбираем payload для получения информации о плане
            payload = payment_info.get('invoice_payload', '')
            parts = payload.split('_')
            
            if len(parts) < 3 or parts[0] != 'subscription':
                logger.error(f"Неверный формат payload: {payload}")
                # Even with invalid payload, try to activate a default subscription
                plan_type = "monthly"  # Default plan if payload is invalid
                logger.info(f"Using default plan '{plan_type}' due to invalid payload")
            else:
                plan_type = parts[1]
                
            if plan_type not in self.plans:
                logger.error(f"Неизвестный тип плана: {plan_type}")
                plan_type = "monthly"  # Fallback to monthly if plan type is unknown
                logger.info(f"Using fallback plan '{plan_type}' due to unknown plan type")
                
            selected_plan = self.plans[plan_type]
            days = selected_plan['days']
            
            # Получение ID платежа от провайдера
            provider_payment_charge_id = payment_info.get('provider_payment_charge_id', 'telegram_payment')
            
            # Расчет даты истечения срока
            expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Get email from payment_info if available
            email = payment_info.get('email')
            
            # Создание данных подписки
            subscription_data = {
                "active": True,
                "expiry_date": expiry_date,
                "plan": plan_type,
                "payment_id": provider_payment_charge_id,
                "purchase_date": datetime.now().strftime('%Y-%m-%d'),
                "telegram_payment": True
            }
            
            # Add email to subscription data if available
            if email:
                subscription_data["email"] = email
                logger.info(f"Adding email {email} to subscription data")
            
            # Сохранение в базу данных
            success = self.database.save_subscription(user_id, subscription_data)
            
            if success:
                logger.info(f"Активирована подписка для пользователя {user_id} до {expiry_date}")
            else:
                logger.error(f"Не удалось сохранить подписку для пользователя {user_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Ошибка обработки успешного платежа через Telegram: {str(e)}", exc_info=True)
            return False
    
    def create_payment(self, user_id, plan_type, return_url=None, email=None):
        """Создать новый платеж для подписки через YooKassa API"""
        # Если включены платежи через Telegram, рекомендуем использовать их
        if self.telegram_payment_enabled:
            logger.info("Доступны платежи через Telegram, но используется YooKassa API")
            
        if not self.payment_enabled:
            logger.error("Платежная система не включена")
            return None
        
        if plan_type not in self.plans:
            logger.error(f"Неверный тип плана: {plan_type}")
            return None
        
        selected_plan = self.plans[plan_type]
        
        try:
            # Создание уникального ключа идемпотентности для этого платежа
            idempotence_key = str(uuid.uuid4())
            
            # Формируем глубокую ссылку для возврата в бот
            # Формат: https://t.me/{bot_username}?start=payment_{payment_id}_{user_id}
            payment_id_placeholder = "{payment_id}"  # Будет заменено на реальный ID после создания платежа
            deep_link_return_url = f"https://t.me/{self.bot_username}?start=payment_{payment_id_placeholder}_{user_id}"
            
            # Проверяем наличие email
            if not email:
                email = "customer@example.com"  # Запасной вариант, если email не предоставлен
                logger.warning(f"Email не предоставлен для пользователя {user_id}, используется запасной вариант")
            
            logger.info(f"Создание платежа для пользователя {user_id}, email: {email}")
            
            # Создание платежа через YooMoney
            payment_data = {
                "amount": {
                    "value": selected_plan["price"],
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url or deep_link_return_url.replace(payment_id_placeholder, "placeholder")
                },
                "capture": True,
                "description": f"Фитнес-тренер бот - {selected_plan['name']}",
                "metadata": {
                    "user_id": str(user_id),
                    "plan_type": plan_type,
                    "days": str(selected_plan["days"]),
                    "bot_username": self.bot_username,
                    "email": email  # Сохраняем email в метаданных
                },
                # Добавляем поддержку различных платежных методов
                "payment_method_data": {
                    "type": "bank_card"
                },
                # Сохраняем информацию о покупателе если есть
                "receipt": {
                    "customer": {
                        "email": email  # Используем предоставленный email
                    },
                    "items": [
                        {
                            "description": selected_plan["name"],
                            "quantity": "1",
                            "amount": {
                                "value": selected_plan["price"],
                                "currency": "RUB"
                            },
                            "vat_code": "1",
                            "payment_subject": "service",
                            "payment_mode": "full_payment"
                        }
                    ]
                }
            }
            
            # Добавляем логирование для отладки
            logger.info(f"Payment data: {payment_data}")
            
            # Создаем платеж
            payment = Payment.create(payment_data, idempotence_key)
            
            # Обновляем URL возврата с реальным ID платежа
            real_return_url = deep_link_return_url.replace(payment_id_placeholder, payment.id)
            
            logger.info(f"Создан платеж {payment.id} для пользователя {user_id}, план {plan_type}")
            logger.info(f"URL возврата: {real_return_url}")
            
            return {
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "return_url": real_return_url,
                "plan": selected_plan,
                "status": payment.status
            }
            
        except Exception as e:
            logger.error(f"Не удалось создать платеж: {str(e)}")
            return None
    
    def check_payment_status(self, payment_id):
        """Проверить статус платежа"""
        if not self.payment_enabled:
            logger.error("Платежная система не включена")
            return None
        
        try:
            # Получение платежа из YooMoney
            payment = Payment.find_one(payment_id)
            
            status_data = {
                "status": payment.status,
                "payment_id": payment.id,
                "metadata": payment.metadata,
                "paid": payment.paid
            }
            
            logger.info(f"Проверен платеж {payment_id}, статус: {payment.status}, оплачен: {payment.paid}")
            return status_data
            
        except Exception as e:
            logger.error(f"Не удалось проверить статус платежа: {str(e)}")
            return None
    
    def process_successful_payment(self, user_id, payment_id, email=None, idempotence_key=None):
        """Обработать успешный платеж и активировать подписку"""
        if not self.payment_enabled and not self.telegram_payment_enabled:
            logger.error("Платежная система не включена")
            return {"success": False}
        
        # For Telegram payments, we might not need to check with YooKassa
        if self.telegram_payment_enabled and user_id:
            # Get the selected plan from the database or use a default
            plan_type = "monthly"  # Default to monthly
            days = 30  # Default to 30 days
            
            # Retrieve the user's last selected plan if available
            user_data = self.database.get_user_data(user_id)
            if user_data and 'selected_plan' in user_data:
                plan_type = user_data['selected_plan']
                days = 365 if plan_type == 'yearly' else 30
            
            # Calculate expiry date
            expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Create subscription data
            subscription_data = {
                "active": True,
                "expiry_date": expiry_date,
                "plan": plan_type,
                "payment_id": payment_id,
                "purchase_date": datetime.now().strftime('%Y-%m-%d'),
                "email": email
            }
            
            # Save to database
            success = self.database.save_subscription(user_id, subscription_data)
            
            if success:
                logger.info(f"Activated subscription for user {user_id} until {expiry_date}")
                return {
                    "success": True,
                    "expiry_date": expiry_date,
                    "plan": plan_type
                }
            else:
                logger.error(f"Failed to save subscription for user {user_id}")
                return {"success": False}
        
        # For YooKassa payments, check payment status
        payment_data = self.check_payment_status(payment_id)
        if not payment_data:
            logger.error(f"Не удалось получить данные платежа {payment_id}")
            return {"success": False}
            
        if payment_data["status"] != "succeeded" and not payment_data.get("paid", False):
            logger.error(f"Платеж {payment_id} не успешен, статус: {payment_data['status']}")
            return {"success": False}
        
        try:
            metadata = payment_data["metadata"]
            payment_user_id = metadata.get("user_id")
            days = int(metadata.get("days", 30))
            plan_type = metadata.get("plan_type", "monthly")
            
            # If user_id was passed, use it; otherwise use from metadata
            user_id = user_id or payment_user_id
            
            if not user_id:
                logger.error(f"Нет user_id в метаданных платежа {payment_id}")
                return {"success": False}
            
            # Проверяем, не активирована ли уже подписка по этому платежу
            existing_subscription = self.database.get_subscription(user_id)
            if existing_subscription and existing_subscription.get('payment_id') == payment_id:
                logger.info(f"Подписка для платежа {payment_id} уже была активирована")
                expiry_date = existing_subscription.get('expiry_date', 'unknown')
                return {
                    "success": True,
                    "expiry_date": expiry_date,
                    "plan": existing_subscription.get('plan', 'monthly')
                }
            
            # Расчет даты истечения срока
            expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Добавляем email к данным подписки, если он предоставлен
            subscription_data = {
                "active": True,
                "expiry_date": expiry_date,
                "plan": plan_type,
                "payment_id": payment_id,
                "purchase_date": datetime.now().strftime('%Y-%m-%d')
            }
            
            if email:
                subscription_data["email"] = email
            
            # Сохранение в базу данных
            success = self.database.save_subscription(user_id, subscription_data)
            
            if success:
                logger.info(f"Активирована подписка для пользователя {user_id} до {expiry_date}")
                return {
                    "success": True,
                    "expiry_date": expiry_date,
                    "plan": plan_type
                }
            else:
                logger.error(f"Не удалось сохранить подписку для пользователя {user_id}")
                return {"success": False}
            
        except Exception as e:
            logger.error(f"Ошибка обработки успешного платежа: {str(e)}")
            return {"success": False}
            
    def handle_payment_callback(self, start_payload):
        """
        Обработать callback при возврате пользователя в бот через deep link
        Формат: payment_{payment_id}_{user_id}
        """
        try:
            if not start_payload.startswith('payment_'):
                logger.warning(f"Неверный формат payload: {start_payload}")
                return None
                
            # Разбираем payload
            parts = start_payload.split('_')
            if len(parts) < 3:
                logger.warning(f"Неверное количество параметров в payload: {start_payload}")
                return None
                
            payment_id = parts[1]
            user_id = parts[2]
            
            # Проверяем статус платежа
            payment_status = self.check_payment_status(payment_id)
            
            if not payment_status:
                return {
                    "success": False,
                    "message": "Платеж не найден"
                }
                
            # Если платеж успешен, активируем подписку
            if payment_status["status"] == "succeeded" or payment_status.get("paid", False):
                success = self.process_successful_payment(user_id, payment_id)
                
                if success:
                    # Получаем данные подписки
                    subscription = self.database.get_subscription(user_id)
                    expiry_date = subscription.get('expiry_date', 'неизвестно')
                    
                    return {
                        "success": True,
                        "message": f"Платеж успешно завершен! Ваша подписка активна до {expiry_date}.",
                        "subscription": subscription
                    }
                else:
                    return {
                        "success": False,
                        "message": "Платеж прошел успешно, но возникла ошибка при активации подписки."
                    }
            else:
                return {
                    "success": False,
                    "message": f"Статус платежа: {payment_status['status']}. Пожалуйста, завершите оплату или повторите попытку.",
                    "payment_id": payment_id
                }
                
        except Exception as e:
            logger.error(f"Ошибка обработки платежного callback: {str(e)}")
            return {
                "success": False,
                "message": "Произошла ошибка при проверке платежа"
            } 