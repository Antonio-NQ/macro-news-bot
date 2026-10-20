import os, json, html
import feedparser, requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL = os.environ["TELEGRAM_CHANNEL"]
SEEN_FILE = "seen.json"
MAX_PER_RUN = 10

FEEDS = {
    "🏦 FED": "https://www.federalreserve.gov/feeds/press_all.xml",
    "🇪🇺 BCE": "https://www.ecb.europa.eu/rss/press.html",
}

def load_seen():
    if os.path.exists(SEEN_FILE):
        return json.load(open(SEEN_FILE))
    return None

def save_seen(seen):
    json.dump(seen[-3000:], open(SEEN_FILE, "w"))

def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHANNEL, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if not r.ok:
        print("Errore Telegram:", r.text)

def main():
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
