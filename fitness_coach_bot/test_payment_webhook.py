#!/usr/bin/env python3
import requests
import json
import os
import uuid
import sys
from pathlib import Path
import argparse

def send_test_notification(webhook_url, notification_type="payment.succeeded"):
    """
    Send a test webhook notification to a YooMoney webhook endpoint
    
    Args:
        webhook_url (str): URL of the webhook endpoint
        notification_type (str): Type of notification to send (payment.succeeded, payment.waiting_for_capture, etc.)
        
    Returns:
        bool: True if the request was successful, False otherwise
    """
    # Complete webhook URL
    if not webhook_url.endswith('/webhook/payment'):
        webhook_url = f"{webhook_url.rstrip('/')}/webhook/payment"
    
    # Create a test payment ID
    payment_id = f"test_{uuid.uuid4()}"
    
    # Test user ID - this should match a user in your test database
    user_id = 12345
    
    # Create a test notification based on the type
    notification = {
        "event": notification_type,
        "object": {
            "id": payment_id,
            "status": "succeeded" if notification_type == "payment.succeeded" else "pending",
            "paid": notification_type == "payment.succeeded",
            "amount": {
                "value": "299.00",
                "currency": "RUB"
            },
            "description": "Подписка на фитнес-тренера бота",
            "metadata": {
                "user_id": user_id,
                "plan_type": "monthly",
                "test_notification": True
            }
        }
    }
    
    # Headers to simulate a YooMoney webhook
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4())
    }
    
    try:
        print(f"Sending {notification_type} test notification to {webhook_url}")
        print(f"Payload: {json.dumps(notification, indent=2)}")
        
        # Send the webhook notification
        response = requests.post(webhook_url, json=notification, headers=headers)
        
        # Print the response details
        print(f"Response status code: {response.status_code}")
        print(f"Response body: {response.text}")
        
        # Return True if the request was successful
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error sending webhook notification: {e}")
        return False

def main():
    """Main function to send test webhook notifications"""
    parser = argparse.ArgumentParser(description='Test YooMoney webhook notifications')
    parser.add_argument('--url', '-u', type=str, default='http://localhost:5000', 
                        help='Webhook server URL (default: http://localhost:5000)')
    parser.add_argument('--type', '-t', type=str, default='payment.succeeded',
                        choices=['payment.succeeded', 'payment.waiting_for_capture', 'payment.canceled'],
                        help='Notification type (default: payment.succeeded)')
    
    args = parser.parse_args()
    
    # Send the test notification
    success = send_test_notification(args.url, args.type)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 