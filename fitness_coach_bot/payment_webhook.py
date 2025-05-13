from flask import Flask, request, jsonify
import os
import logging
import hashlib
import hmac
import base64
from fitness_coach_bot.database import Database
from fitness_coach_bot.payment_manager import PaymentManager
import uuid
import json
import dotenv
from pathlib import Path
import requests
import threading
import time

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add a simple root route for health checks
@app.route('/', methods=['GET'])
def health_check():
    """Simple health check endpoint to verify the server is running"""
    return jsonify({"status": "ok", "service": "payment_webhook"}), 200

# Load environment variables from .env file
env_paths = [
    '.env',                                # Current directory
    'fitness_coach_bot/.env',              # Subdirectory
    '../.env',                             # Parent directory
    str(Path(__file__).parent.parent / '.env'),  # Relative to current file
    # Keep test paths as fallback
    '.env.test',                           # Current directory
    'fitness_coach_bot/.env.test',         # Subdirectory
    '../.env.test',                        # Parent directory
    str(Path(__file__).parent.parent / '.env.test')  # Relative to current file
]

for env_path in env_paths:
    if os.path.exists(env_path):
        dotenv.load_dotenv(env_path)
        logger.info(f"Loaded environment variables from {env_path}")
        break
else:
    logger.warning("Could not find .env or .env.test file, using default credentials")

# Инициализация базы данных и менеджера платежей
database = Database()
payment_manager = PaymentManager(database)

# Флаг, показывающий, запущен ли веб-сервер
webhook_server_running = False

@app.route('/webhook/payment', methods=['POST'])
def payment_webhook():
    """
    Обработчик вебхуков от YooKassa
    
    YooKassa отправляет уведомления о изменении статуса платежа.
    Подробнее: https://yookassa.ru/developers/using-api/webhooks
    """
    # Получаем уведомление
    notification_body = request.data.decode('utf-8')
    signature_header = request.headers.get('X-Signature')
    
    # Получаем секретный ключ из переменных окружения
    secret_key = os.getenv('YOOMONEY_API_KEY')
    
    # Логируем заголовки и тело запроса для диагностики
    logger.info(f"Получен вебхук от YooKassa. Заголовки: {request.headers}")
    logger.info(f"Тело запроса: {notification_body}")
    
    # Проверяем подпись только если она предоставлена
    if signature_header and secret_key:
        if not verify_signature(notification_body, signature_header, secret_key):
            logger.error("Недействительная подпись уведомления")
            return jsonify({"status": "error", "message": "Invalid signature"}), 400
    else:
        logger.warning("Пропуск проверки подписи: отсутствует подпись или секретный ключ")
    
    # Продолжаем обработку
    try:
        notification = json.loads(notification_body)
        
        event = notification.get('event')
        payment_id = notification.get('object', {}).get('id')
        status = notification.get('object', {}).get('status')
        paid = notification.get('object', {}).get('paid', False)
        metadata = notification.get('object', {}).get('metadata', {})
        
        logger.info(f"Обработка события {event}, платеж {payment_id}, статус {status}, оплачен: {paid}")
        logger.info(f"Metadata: {metadata}")
        
        # Extract user_id from metadata if available
        user_id = None
        if metadata and 'user_id' in metadata:
            user_id = metadata.get('user_id')
            logger.info(f"Extracted user_id from metadata: {user_id}")
        
        # Обрабатываем различные события
        if event == 'payment.succeeded':
            # Платеж успешно завершен
            idempotence_key = str(uuid.uuid4())
            success = payment_manager.process_successful_payment(
                user_id=user_id, 
                payment_id=payment_id, 
                idempotence_key=idempotence_key
            )
            
            if success:
                logger.info(f"Вебхук успешно обработал платеж: {payment_id}")
                return jsonify({"status": "success"})
            else:
                logger.error(f"Ошибка при обработке успешного платежа: {payment_id}")
                return jsonify({"status": "error", "message": "Error processing payment"}), 500
                
        elif event == 'payment.waiting_for_capture':
            # Платеж ожидает подтверждения (холдирование средств)
            logger.info(f"Платеж {payment_id} ожидает подтверждения (capture)")
            return jsonify({"status": "success"})
            
        elif event == 'payment.canceled':
            # Платеж отменен
            logger.info(f"Платеж {payment_id} отменен")
            return jsonify({"status": "success"})
            
        elif event == 'refund.succeeded':
            # Успешный возврат средств
            logger.info(f"Выполнен возврат средств для платежа {payment_id}")
            return jsonify({"status": "success"})
            
        else:
            # Неизвестное или необрабатываемое событие
            logger.info(f"Получено необрабатываемое событие: {event}")
            return jsonify({"status": "ignored", "event": event})
            
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON: {str(e)}")
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400
        
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def verify_signature(body, signature, secret_key):
    """
    Проверяет подпись уведомления от YooMoney
    
    Args:
        body (str): Тело запроса (JSON)
        signature (str): Значение заголовка X-Signature
        secret_key (str): Секретный ключ API YooMoney
    
    Returns:
        bool: True если подпись действительна, иначе False
    """
    if not signature or not secret_key:
        return False
    
    try:
        # Создаем HMAC-SHA256 подпись
        hmac_obj = hmac.new(
            secret_key.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        )
        calculated_signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')
        
        # Сравниваем вычисленную подпись с полученной
        return hmac.compare_digest(calculated_signature, signature)
    except Exception as e:
        logger.error(f"Ошибка при проверке подписи: {str(e)}")
        return False

def register_webhook_with_yoomoney(webhook_url):
    """
    Регистрирует URL вебхука в YooMoney API
    
    Args:
        webhook_url (str): Полный URL вебхука для регистрации
        
    Returns:
        bool: True в случае успешной регистрации, иначе False
    """
    shop_id = os.getenv('YOOMONEY_SHOP_ID')
    api_key = os.getenv('YOOMONEY_API_KEY')
    
    if not shop_id or not api_key:
        logger.error("Отсутствуют учетные данные YooMoney для регистрации вебхука")
        return False
    
    # URL API для регистрации вебхуков
    api_url = "https://api.yookassa.ru/v3/webhooks"
    
    # Данные для запроса
    webhook_data = {
        "event": "payment.succeeded",
        "url": webhook_url
    }
    
    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": str(uuid.uuid4())
    }
    
    # Аутентификация Basic Auth (shop_id:API key)
    auth = (shop_id, api_key)
    
    try:
        # Сначала получаем список текущих вебхуков
        response = requests.get(api_url, auth=auth, headers=headers)
        
        if response.status_code == 200:
            current_webhooks = response.json().get('items', [])
            
            # Проверяем, существует ли уже такой вебхук
            for webhook in current_webhooks:
                if webhook.get('url') == webhook_url and webhook.get('event') == "payment.succeeded":
                    logger.info(f"Вебхук уже зарегистрирован: {webhook_url}")
                    return True
        
        # Регистрируем новый вебхук
        response = requests.post(
            api_url,
            json=webhook_data,
            auth=auth,
            headers=headers
        )
        
        if response.status_code in (200, 201):
            logger.info(f"Вебхук успешно зарегистрирован: {webhook_url}")
            return True
        else:
            logger.error(f"Ошибка регистрации вебхука: {response.status_code}, {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при регистрации вебхука: {str(e)}")
        return False

def start_webhook_server(host='0.0.0.0', port=5000, public_url=None):
    """
    Запускает сервер вебхуков в отдельном потоке
    
    Args:
        host (str): Хост для запуска сервера (по умолчанию 0.0.0.0)
        port (int): Порт для запуска сервера (по умолчанию 5000)
        public_url (str): Публичный URL для регистрации вебхука (если None, регистрация не выполняется)
    
    Returns:
        threading.Thread: Объект потока с запущенным сервером
    """
    global webhook_server_running
    
    if webhook_server_running:
        logger.info("Сервер вебхуков уже запущен")
        return None
    
    # Настраиваем порт из переменной окружения, если указана
    port = int(os.getenv('WEBHOOK_PORT', port))
    
    # Если указан публичный URL, регистрируем вебхук в YooMoney
    if public_url:
        webhook_url = f"{public_url.rstrip('/')}/webhook/payment"
        success = register_webhook_with_yoomoney(webhook_url)
        if success:
            logger.info(f"Вебхук успешно зарегистрирован: {webhook_url}")
        else:
            logger.warning(f"Не удалось зарегистрировать вебхук: {webhook_url}")
    
    def run_server():
        global webhook_server_running  # Need to declare global inside the function too
        logger.info(f"Запуск сервера вебхуков на {host}:{port}")
        webhook_server_running = True
        app.run(host=host, port=port, debug=False, use_reloader=False)
    
    # Запуск сервера в отдельном потоке
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait a moment to ensure the server has started
    time.sleep(1)
    
    logger.info(f"Сервер вебхуков запущен в отдельном потоке на порту {port}")
    return server_thread

if __name__ == '__main__':
    # Запуск сервера вебхуков
    port = int(os.getenv('WEBHOOK_PORT', 5000))
    public_url = os.getenv('PUBLIC_WEBHOOK_URL')
    
    if public_url:
        logger.info(f"Регистрация вебхука: {public_url}/webhook/payment")
        register_webhook_with_yoomoney(f"{public_url.rstrip('/')}/webhook/payment")
    
    app.run(host='0.0.0.0', port=port, debug=False)
    logger.info(f"Сервер вебхуков запущен на порту {port}") 