import telebot
from flask import Flask, request
import html
import re
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
# Doc (12 Nov): the Nifty scalping indicator's alerts ("ChartRoom Nifty BUY | SL ..", "ChartRoom Nifty TP | ..", etc.)
# go to the Nifty & Indices topic instead of Signals. Everything else stays in Signals.
NIFTY_TOPIC = 10717
NIFTY_PREFIX = "chartroom nifty"

IST = pytz.timezone('Asia/Kolkata')

# Optional secret: when WEBHOOK_KEY is set in Railway Variables, /webhook/<key> works. Once every TradingView alert
# uses that URL, set REQUIRE_KEY=1 and the old open /webhook stops accepting posts.
WEBHOOK_KEY = os.environ.get('WEBHOOK_KEY', '')
REQUIRE_KEY = os.environ.get('REQUIRE_KEY', '') == '1'
NIFTY_HINT = os.environ.get('NIFTY_HINT', '') == '1'
NIFTY_DISCLAIMER = os.environ.get('NIFTY_DISCLAIMER', '1') != '0'  # on unless set to 0


def post_to_signals(text_html, text_plain, topic=SIGNALS_TOPIC):
    """Posts to Signals with up to 3 tries; falls back to plain text if Telegram rejects the formatting."""
    last = None
    for attempt in range(3):
        try:
            kwargs = {'parse_mode': 'HTML'} if text_html else {}
            if topic is not None:
                kwargs['message_thread_id'] = topic
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
        if NIFTY_HINT and alert_message.strip().lower().startswith(NIFTY_PREFIX) and re.search(r"nifty\s+(buy|sell)\b", alert_message, re.I):
            # Doc (19 Nov): members asked what "Fill" means and how long a signal lasts. Added as a LAST line only, so the
            # signal text itself is unchanged for members' own automations. Off unless NIFTY_HINT=1.
            formatted_html += "\n\n<i>Entry = Fill price · valid till 3:10 PM IST</i>"
            formatted_plain += "\n\nEntry = Fill price · valid till 3:10 PM IST"

        if NIFTY_DISCLAIMER and alert_message.strip().lower().startswith(NIFTY_PREFIX):
            # Doc (19 Nov): every Nifty scalping signal carries the disclaimer, as the LAST line so the signal text above is unchanged
            formatted_html += "\n\n<i>Educational purposes only.</i>"
            formatted_plain += "\n\nEducational purposes only."

        # Send to Signals topic
        try:
            is_nifty = alert_message.strip().lower().startswith(NIFTY_PREFIX)
            try:
                sent = post_to_signals(formatted_html, formatted_plain, NIFTY_TOPIC if is_nifty else SIGNALS_TOPIC)
            except Exception as e:
                if not is_nifty:
                    raise
                print(f"⚠️ Nifty topic post failed ({e}); falling back to Signals so the alert is not lost")
                sent = post_to_signals(formatted_html, formatted_plain)
            print(f"✅ Alert posted to {'Nifty & Indices' if is_nifty else 'Signals'} (message_id={sent.message_id}): {alert_message[:50]}...")
            return {'status': 'success', 'message': 'Alert posted'}, 200

        except Exception as e:
            print(f"❌ Error posting to Telegram: {e}")
            return {'status': 'error', 'message': str(e)}, 500

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {'status': 'error', 'message': str(e)}, 400


# ---- Chartink scan alerts (replaces the IFTTT relay; Doc, 16 Nov 2026) ----
# Chartink webhook body (editable "payload columns" in the alert): {"value1": scan name,
# "value2": "SYM - price, SYM - price", "value3": " @ 7:01 pm"}. Native fields (scan_name, stocks, trigger_prices,
# triggered_at) are accepted too. Posted to Signals as a clean one-message alert.
CHARTINK_KEY = os.environ.get('CHARTINK_KEY', '')
# Comma-separated scan names (lower case) that post a given stock at most once a day (e.g. noisy daily scans). Empty = off.
ONCE_PER_DAY = {s.strip().lower() for s in os.environ.get('ONCE_PER_DAY_SCANS', '').split(',') if s.strip()}
_seen_today = {}  # (scan, stock) -> date
MAX_PER_POST = max(1, int(os.environ.get('MAX_PER_POST', '12') or 12))  # stocks listed in one Chartink post


def clean_scan_name(name):
    """Posts show just the setup's name (Doc, 17 Nov): drops a 'Dr. Romeet Saha-' author prefix and writes EMA in capitals."""
    name = re.sub(r'(?i)^dr\.?\s*romeet\s*saha\s*[-\u2013:]+\s*', '', name).strip()
    if re.match(r'(?i)^cr\s', name):
        # Doc (17 Nov): my own scans post under the setup's plain name ("CR Inside Bar Daily" -> "Inside Bar", "CR FnO 75m Breakout" -> "75m Breakout")
        name = re.sub(r'(?i)^cr\s+', '', name)
        name = re.sub(r'(?i)\bfno\s+', '', name)
        name = re.sub(r'(?i)\s+daily$', '', name).strip()
    return re.sub(r'(?i)\bema\b', 'EMA', name)


def parse_chartink(data):
    """Returns (scan_name, [(stock, price_or_None)], time_text) from either payload shape."""
    scan = str(data.get('value1') or data.get('scan_name') or data.get('alert_name') or 'Chartink scan').strip()
    scan = clean_scan_name(scan)
    pairs = []
    if data.get('stocks'):
        stocks = [s.strip() for s in str(data['stocks']).split(',') if s.strip()]
        prices = [p.strip() for p in str(data.get('trigger_prices', '')).split(',')]
        for i, s in enumerate(stocks):
            pairs.append((s, prices[i] if i < len(prices) and prices[i] else None))
    else:
        for part in str(data.get('value2') or '').split(','):
            part = part.strip()
            if not part:
                continue
            if ' - ' in part:
                s, p = part.rsplit(' - ', 1)
                pairs.append((s.strip(), p.strip() or None))
            else:
                pairs.append((part, None))
    when = str(data.get('value3') or data.get('triggered_at') or '').strip().lstrip('@').strip()
    return scan, pairs, when


@app.route('/chartink/<key>', methods=['GET', 'POST'])
def receive_chartink(key):
    if not CHARTINK_KEY or key != CHARTINK_KEY:
        return {'status': 'error', 'message': 'not found'}, 404
    if request.method == 'GET':
        return {'status': 'ok', 'message': 'chartink endpoint is up, send a POST'}, 200
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        print(f"📥 Chartink: {str(data)[:300]}")
        scan, pairs, when = parse_chartink(data)
        today = datetime.now(IST).date()
        if scan.lower() in ONCE_PER_DAY:
            fresh = []
            for s, p in pairs:
                if _seen_today.get((scan.lower(), s)) != today:
                    _seen_today[(scan.lower(), s)] = today
                    fresh.append((s, p))
            pairs = fresh
            if not pairs:
                print(f"↩️ Chartink {scan}: already posted today, skipped")
                return {'status': 'ok', 'message': 'duplicate skipped'}, 200
        if not pairs:
            print(f"↩️ Chartink {scan}: no stocks in payload, nothing to post")
            return {'status': 'ok', 'message': 'no stocks'}, 200
        when = when or datetime.now(IST).strftime("%I:%M %p").lstrip('0').lower()
        more = max(0, len(pairs) - MAX_PER_POST)
        pairs = pairs[:MAX_PER_POST]  # Doc (19 Nov): very long lists (Daily Hammer: 20+) are cut; "+N more" says so
        if request.args.get('dry') == '1':
            # Doc (17 Nov): tests must never land in a public topic. ?dry=1 returns what would be posted, posts nothing.
            return {'status': 'dry', 'would_post': f"🔔 {scan} · {when}\n" + "\n".join(f"{s}" + (f" ₹{p}" if p else "") for s, p in pairs)
                    + (f"\n+{more} more" if more else "")}, 200
        lines_h = [f"{html.escape(s)}" + (f" ₹{html.escape(p)}" if p else "") for s, p in pairs]
        lines_p = [f"{s}" + (f" ₹{p}" if p else "") for s, p in pairs]
        head = f"🔔 {scan} · {when}"
        tail = f"\n+{more} more" if more else ""
        sent = post_to_signals(f"🔔 <b>{html.escape(scan)}</b> · {html.escape(when)}\n" + "\n".join(lines_h) + tail,
                               head + "\n" + "\n".join(lines_p) + tail)
        print(f"✅ Chartink posted (message_id={sent.message_id}): {scan}: {len(pairs)} stock(s)")
        return {'status': 'success', 'message': 'Alert posted'}, 200
    except Exception as e:
        print(f"❌ Chartink webhook error: {e}")
        return {'status': 'error', 'message': str(e)}, 500


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
