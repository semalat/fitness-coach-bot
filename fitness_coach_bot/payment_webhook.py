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

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных и менеджера платежей
database = Database()
payment_manager = PaymentManager(database)

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
    
    # Проверяем подпись
    if not verify_signature(notification_body, signature_header, secret_key):
        logger.error("Недействительная подпись уведомления")
        return jsonify({"status": "error", "message": "Invalid signature"}), 400
    
    # Продолжаем обработку только если подпись действительна
    try:
        notification = json.loads(notification_body)
        
        event = notification.get('event')
        payment_id = notification.get('object', {}).get('id')
        status = notification.get('object', {}).get('status')
        paid = notification.get('object', {}).get('paid', False)
        
        logger.info(f"Обработка события {event}, платеж {payment_id}, статус {status}, оплачен: {paid}")
        
        # Обрабатываем различные события
        if event == 'payment.succeeded':
            # Платеж успешно завершен
            idempotence_key = str(uuid.uuid4())
            success = payment_manager.process_successful_payment(payment_id, idempotence_key)
            
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
        logger.error(f"Ошибка обработки вебхука: {str(e)}")
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

if __name__ == '__main__':
    # Запуск сервера вебхуков
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
    logger.info(f"Сервер вебхуков запущен на порту {port}") 