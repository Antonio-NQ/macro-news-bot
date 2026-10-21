import os, sys, json, html
import feedparser, requests

TOKEN = os.environ["TELEGRAM_TOKEN"].strip()
CHANNEL = os.environ["TELEGRAM_CHANNEL"].strip()
if CHANNEL.startswith("https://t.me/"):
    CHANNEL = "@" + CHANNEL.split("/")[-1]
elif not CHANNEL.startswith(("@", "-")):
    CHANNEL = "@" + CHANNEL

SEEN_FILE = "seen.json"
MAX_PER_RUN = 10
SEND_TEST = False

FEEDS = {
    "🏦 FED": "https://www.federalreserve.gov/feeds/press_all.xml",
    "🇪🇺 BCE": "https://www.ecb.europa.eu/rss/press.html",
}

def load_seen():
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except Exception:
        return None

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen[-3000:], f)

def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHANNEL, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if not r.ok:
        sys.exit(f"ERRORE TELEGRAM {r.status_code}: {r.text}")

def main():
    if SEND_TEST:
        send("✅ Test: il bot funziona!")
        return

    seen = load_seen()
    first_run = seen is None
    seen = seen or []
    seen_set = set(seen)
    new_items = []

    for label, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print("Errore feed", label, e)
            continue
        for e in reversed(feed.entries):
            uid = e.get("id") or e.get("link")
            if not uid or uid in seen_set:
                continue
            seen_set.add(uid)
            seen.append(uid)
            title = html.escape(e.get("title", "").strip())
            new_items.append(f"{label}\n<b>{title}</b>\n{e.get('link', '')}")

    if not first_run:
        for msg in new_items[-MAX_PER_RUN:]:
            send(msg)

    save_seen(seen)

if __name__ == "__main__":
    main()
