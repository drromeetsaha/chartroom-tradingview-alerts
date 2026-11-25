"""Daily clean-up of the Nifty scalping posts (Doc, 25 Nov 2026).

Every Nifty scalping post is saved here. At DELETE_AT (IST) the bot first sends Doc a private copy, then deletes the
posts from the group. Only posts passed to record() are ever deleted. Telegram lets a bot delete its own message
for 48 hours only. Nothing here may stop an alert from being posted.
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta

import pytz

IST = pytz.timezone('Asia/Kolkata')
ENABLED = os.environ.get('DAILY_CLEANUP', '1') != '0'  # on unless set to 0
DELETE_AT = os.environ.get('DELETE_AT', '15:40')
OWNER_ID = int(os.environ.get('OWNER_ID', '570458138'))
# A Railway volume mounted at /app/data keeps the list across restarts.
DATA_DIR = os.environ.get('DATA_DIR') or ('/app/data' if os.path.isdir('/app/data') else '.')
STORE = os.path.join(DATA_DIR, 'nifty_posts.json')
MAX_AGE = 48 * 3600
COPY_LIMIT = 3500  # Telegram's limit is 4096; leaves room for the heading

_lock = threading.RLock()
_posts = None  # list of {"id", "ts", "text", "copied"}


def _load():
    global _posts
    if _posts is None:
        try:
            with open(STORE, encoding='utf-8') as f:
                _posts = json.load(f)
        except FileNotFoundError:
            _posts = []
        except Exception as e:
            print(f"⚠️ Clean-up list unreadable ({e}); starting a new one")
            _posts = []
    return _posts


def _save():
    try:
        with open(STORE + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(_posts, f, ensure_ascii=False)
        os.replace(STORE + '.tmp', STORE)
    except Exception as e:
        print(f"⚠️ Clean-up list not saved to disk ({e}); it is still held in memory")


def record(message_id, text, now=None):
    """Remember one Nifty scalping post. Never raises: the alert has already been posted."""
    try:
        with _lock:
            _load().append({'id': int(message_id), 'ts': (now or time.time()), 'text': str(text), 'copied': False})
            _save()
    except Exception as e:
        print(f"⚠️ Clean-up could not record message {message_id}: {e}")


def pending():
    with _lock:
        return len(_load())


def last_cutoff(now):
    """The most recent DELETE_AT that has passed, as a timestamp."""
    hour, minute = (int(x) for x in DELETE_AT.split(':'))
    local = datetime.fromtimestamp(now, IST)
    cut = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cut > local:
        cut -= timedelta(days=1)
    return cut.timestamp()


def _copy_chunks(posts):
    chunks, current, members = [], '', []
    for p in posts:
        entry = p['text'][:COPY_LIMIT]
        if current and len(current) + len(entry) + 2 > COPY_LIMIT:
            chunks.append((current, members))
            current, members = '', []
        current = f"{current}\n\n{entry}" if current else entry
        members.append(p)
    if current:
        chunks.append((current, members))
    return chunks


def run_once(bot, chat_id, now=None):
    """Copies, then deletes, every saved post sent up to the last cutoff. Returns the number deleted.
    A post is deleted only after Doc's copy has gone through; anything that fails is tried again later."""
    now = now or time.time()
    with _lock:
        cutoff = last_cutoff(now)
        due = [p for p in _load() if p['ts'] <= cutoff]
    if not due:
        return 0

    for body, members in _copy_chunks([p for p in due if not p['copied']]):
        day = datetime.fromtimestamp(members[0]['ts'], IST).strftime('%d %b %Y')
        try:
            bot.send_message(OWNER_ID, f"🗂 Private copy: Nifty scalping posts, {day}\n\n{body}")
        except Exception as e:
            print(f"⚠️ Clean-up: private copy not sent ({e}); those posts stay in the group for now")
            continue
        with _lock:
            for p in members:
                p['copied'] = True
            _save()

    deleted, gone, too_old = 0, [], 0
    for p in due:
        if not p['copied']:
            continue
        try:
            bot.delete_message(chat_id, p['id'])
            deleted += 1
            gone.append(p)
        except Exception as e:
            if 'message to delete not found' in str(e).lower():
                gone.append(p)  # already removed by hand
            elif now - p['ts'] >= MAX_AGE:
                too_old += 1
                gone.append(p)
                print(f"⚠️ Clean-up: message {p['id']} is older than 48 hours and cannot be deleted ({e})")
            else:
                print(f"⚠️ Clean-up: could not delete message {p['id']} ({e}); will try again")

    with _lock:
        for p in gone:
            _posts.remove(p)
        _save()
    if deleted or too_old:
        print(f"🧹 Clean-up: deleted {deleted} Nifty scalping post(s), {too_old} too old to delete")
    return deleted


def start(bot, chat_id, every=60, retry_after=600):
    """Checks once a minute in the background. After a failed run it waits 10 minutes, to avoid hammering Telegram."""
    if not ENABLED:
        print("🧹 Daily clean-up is off (DAILY_CLEANUP=0)")
        return None

    def loop():
        while True:
            wait = every
            try:
                run_once(bot, chat_id)
                with _lock:
                    if any(p['ts'] <= last_cutoff(time.time()) for p in _load()):
                        wait = retry_after
            except Exception as e:
                print(f"⚠️ Clean-up error: {e}")
                wait = retry_after
            time.sleep(wait)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    where = 'volume' if DATA_DIR == '/app/data' else 'NOT on a volume: a restart loses the list'
    print(f"🧹 Daily clean-up on: Nifty scalping posts are deleted at {DELETE_AT} IST ({where}); {pending()} waiting")
    return thread
