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
        # Try multiple ways to get data
        data = request.get_json(silent=True) or request.form.to_dict()
        
        # If still empty, try raw body
        if not data or not any(data.values()):
            raw_body = request.get_data(as_text=True)
            print(f"📥 Raw body: {raw_body}")
            data = {'raw': raw_body} if raw_body else {}
        
        # Debug: log incoming data
        print(f"📥 Webhook received - Data: {data}")
        
        if not data:
            print("❌ No data in webhook")
            return {'status': 'error', 'message': 'No data received'}, 400
        
        # Extract message - try multiple fields
        alert_message = (data.get('message', '') or 
                        data.get('msg', '') or 
                        data.get('raw', '') or 
                        str(data))
        
        if not alert_message:
            print("⚠️ No message field found - using raw data")
            alert_message = str(data)[:200]  # Use first 200 chars of data
        
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
