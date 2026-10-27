import telebot
from flask import Flask, request
import html
import os
import time
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

CHAT_ID = -1002599963619
# Signals (Don't Chat) is the forum's General topic - Telegram requires
# omitting message_thread_id (not passing 1) to post there.
SIGNALS_TOPIC = None

IST = pytz.timezone('Asia/Kolkata')

# Optional secret: when WEBHOOK_KEY is set in Railway Variables, /webhook/<key> works. Once every TradingView alert
# uses that URL, set REQUIRE_KEY=1 and the old open /webhook stops accepting posts.
WEBHOOK_KEY = os.environ.get('WEBHOOK_KEY', '')
REQUIRE_KEY = os.environ.get('REQUIRE_KEY', '') == '1'


def post_to_signals(text_html, text_plain):
    """Posts to Signals with up to 3 tries; falls back to plain text if Telegram rejects the formatting."""
    last = None
    for attempt in range(3):
        try:
            kwargs = {'parse_mode': 'HTML'} if text_html else {}
            if SIGNALS_TOPIC is not None:
                kwargs['message_thread_id'] = SIGNALS_TOPIC
            return bot.send_message(CHAT_ID, text_html or text_plain, **kwargs)
        except Exception as e:
            last = e
            if "parse" in str(e).lower() or "entities" in str(e).lower():
                text_html = None  # e.g. a symbol like BAJAJ_AUTO broke the formatting: send it plain
                continue
            time.sleep(2 * (attempt + 1))
    raise last

app = Flask(__name__)


@app.route('/webhook', methods=['GET', 'POST'])
@app.route('/webhook/<key>', methods=['GET', 'POST'])
def receive_alert(key=None):
    if key is not None and (not WEBHOOK_KEY or key != WEBHOOK_KEY):
        return {'status': 'error', 'message': 'not found'}, 404
    if key is None and REQUIRE_KEY and request.method == 'POST':
        print("⛔ Post to the open /webhook refused (REQUIRE_KEY is on)")
        return {'status': 'error', 'message': 'not found'}, 404
    try:
        # Full diagnostics, regardless of method
        print("=" * 60)
        print(f"📥 Method: {request.method}")
        print(f"📥 Content-Type: {request.content_type}")
        print(f"📥 Content-Length: {request.content_length}")
        print(f"📥 From: {request.headers.get('X-Forwarded-For', request.remote_addr)}  UA: {request.headers.get('User-Agent', '')[:60]}")

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

        # Format the alert for Telegram. The alert text is escaped: TradingView symbols like BAJAJ_AUTO or M_M
        # used to break the old Markdown formatting, and Telegram then dropped the whole alert.
        formatted_html = (f"🔔 <b>TRADINGVIEW ALERT</b>\n\n{html.escape(alert_message)}\n\n"
                          f"<i>Time: {current_time} IST</i>")
        formatted_plain = f"🔔 TRADINGVIEW ALERT\n\n{alert_message}\n\nTime: {current_time} IST"

        # Send to Signals topic
        try:
            sent = post_to_signals(formatted_html, formatted_plain)
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
