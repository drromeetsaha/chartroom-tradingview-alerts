import telebot
from flask import Flask, request
import json
from datetime import datetime
import pytz

BOT_TOKEN = "8795864665:AAF3_yW2LIomkjCK9eZBZOvExpit-e838GE"
bot = telebot.TeleBot(BOT_TOKEN)

CHAT_ID = -1002599963619
SIGNALS_TOPIC = 1

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_alert():
    try:
        data = request.get_json()
        
        if not data:
            return {'status': 'error', 'message': 'No data received'}, 400
        
        # Extract message from TradingView alert
        alert_message = data.get('message', '')
        
        if not alert_message:
            return {'status': 'error', 'message': 'No message in alert'}, 400
        
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
    app.run(host='0.0.0.0', port=5000, debug=False)
