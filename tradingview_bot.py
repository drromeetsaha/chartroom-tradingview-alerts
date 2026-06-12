import telebot
from flask import Flask, request
import json
import os
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

CHAT_ID = -1002599963619
SIGNALS_TOPIC = 1

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_alert():
    try:
        # Get raw body first
        raw_body = request.get_data(as_text=True)
        print(f"📥 Raw webhook body: {raw_body}")
        
        # Try JSON
        data = request.get_json(silent=True)
        if data:
            print(f"📥 JSON data: {data}")
        
        # Try form data
        if not data:
            data = request.form.to_dict()
            if data:
                print(f"📥 Form data: {data}")
        
        # Extract message from any available source
        alert_message = None
        
        if data:
            # Try common field names
            alert_message = (data.get('message', '') or 
                            data.get('msg', '') or 
                            data.get('text', '') or 
                            data.get('alert', '') or
                            list(data.values())[0] if data else '')
        
        # If no message from structured data, use raw body
        if not alert_message and raw_body:
            alert_message = raw_body
        
        # Final fallback
        if not alert_message:
            alert_message = "TradingView Alert Triggered"
        
        print(f"✅ Alert message: {alert_message[:100]}")
        
        # Get current time in IST
        current_time = datetime.now(IST).strftime("%H:%M:%S")
        
        # Format the alert for Telegram
        formatted_alert = (
            f"🔔 **TRADINGVIEW ALERT**\n\n"
            f"{alert_message}\n\n"
            f"_Time: {current_time} IST_"
        )
        
        # Send to Signals topic
        try:
            bot.send_message(
                CHAT_ID,
                formatted_alert,
                message_thread_id=SIGNALS_TOPIC,
                parse_mode="Markdown"
            )
            print(f"✅ Alert posted to Signals: {alert_message[:50]}...")
            return {'status': 'success', 'message': 'Alert posted'}, 200
            
        except Exception as e:
            print(f"❌ Error posting to Telegram: {e}")
            return {'status': 'error', 'message': str(e)}, 500
    
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {'status': 'error', 'message': str(e)}, 400

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'Bot is running'}, 200

if __name__ == '__main__':
    print("🚀 TradingView Webhook Bot is running...")
    print(f"Chat ID: {CHAT_ID}")
    print(f"Signals Topic: {SIGNALS_TOPIC}")
    print("Webhook endpoint: /webhook")
    print("="*60)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
