import telebot
from flask import Flask, request
import os
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

CHAT_ID = -1002599963619
SIGNALS_TOPIC = 1

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)


@app.route('/webhook', methods=['GET', 'POST'])
def receive_alert():
    try:
        # Full diagnostics, regardless of method
        print("=" * 60)
        print(f"📥 Method: {request.method}")
        print(f"📥 Content-Type: {request.content_type}")
        print(f"📥 Content-Length: {request.content_length}")
        print(f"📥 Headers: {dict(request.headers)}")

        raw_body = request.get_data(as_text=True)
        print(f"📥 Raw body ({len(raw_body)} chars): {raw_body!r}")

        if request.method == 'GET':
            return {'status': 'ok', 'message': 'webhook endpoint is up, send a POST'}, 200

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
            alert_message = (data.get('message') or
                              data.get('msg') or
                              data.get('text') or
                              data.get('alert') or
                              next(iter(data.values()), ''))

        # If no message from structured data, use raw body
        if not alert_message and raw_body.strip():
            alert_message = raw_body.strip()

        # Final fallback
        if not alert_message:
            alert_message = "TradingView Alert Triggered (no message body received)"

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
            sent = bot.send_message(
                CHAT_ID,
                formatted_alert,
                message_thread_id=SIGNALS_TOPIC,
                parse_mode="Markdown"
            )
            print(f"✅ Alert posted to Signals (message_id={sent.message_id}): {alert_message[:50]}...")
            return {'status': 'success', 'message': 'Alert posted'}, 200

        except Exception as e:
            print(f"❌ Error posting to Telegram: {e}")
            return {'status': 'error', 'message': str(e)}, 500

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {'status': 'error', 'message': str(e)}, 400


@app.route('/health', methods=['GET'])
def health():
    return {
        'status': 'Bot is running',
        'bot_token_set': bool(BOT_TOKEN),
        'chat_id': CHAT_ID,
        'signals_topic': SIGNALS_TOPIC,
    }, 200


if __name__ == '__main__':
    print("🚀 TradingView Webhook Bot is running...")
    print(f"BOT_TOKEN set: {bool(BOT_TOKEN)}")
    print(f"Chat ID: {CHAT_ID}")
    print(f"Signals Topic: {SIGNALS_TOPIC}")
    print("Webhook endpoint: /webhook")
    print("=" * 60)
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
