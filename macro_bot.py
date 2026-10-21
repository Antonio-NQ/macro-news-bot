import os, re, json, html, time
from calendar import timegm
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import feedparser, requests
from deep_translator import GoogleTranslator

TOKEN = os.environ["TELEGRAM_TOKEN"].strip()
CHANNEL = os.environ["TELEGRAM_CHANNEL"].strip()
if CHANNEL.startswith("https://t.me/"):
    CHANNEL = "@" + CHANNEL.split("/")[-1]
elif not CHANNEL.startswith(("@", "-")):
    CHANNEL = "@" + CHANNEL

SEEN_FILE = "seen.json"
MAX_PER_RUN = 10        # messaggi massimi per giro
MAX_AGE_HOURS = 6       # ignora notizie più vecchie
CAL_WINDOW_MIN = 30     # avviso calendario: minuti prima
TRANSLATE = True
ROME = ZoneInfo("Europe/Rome")

# (etichetta, url, filtra per parole chiave?)
FEEDS = [
    ("🏦 FED", "https://www.federalreserve.gov/feeds/press_all.xml", False),
    ("🇪🇺 BCE", "https://www.ecb.europa.eu/rss/press.xml", False),
    ("🇬🇧 BoE", "https://www.bankofengland.co.uk/rss/news", False),
    ("📊 BLS", "https://www.bls.gov/feed/bls_latest.rss", False),
    ("📰 CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", True),
]

CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAL_COUNTRIES = {"USD", "EUR", "GBP"}

KEYWORDS = [
    "inflation", "cpi", "pce", "ppi", "interest rate", "rate cut", "rate hike",
    "fed", "fomc", "powell", "lagarde", "ecb", "bank of england", "bailey",
    "payrolls", "nonfarm", "jobs report", "unemployment", "jobless", "gdp",
    "recession", "tariff", "tariffs", "treasury", "yields", "retail sales",
    "pmi", "ism", "consumer confidence", "oil", "opec", "dollar",
    "debt ceiling", "shutdown",
]
HIGH = [
    "rate decision", "interest rate", "rate cut", "rate hike", "fomc", "cpi",
    "inflation", "payrolls", "nonfarm", "jobs report", "powell", "lagarde",
    "gdp", "tariff", "tariffs", "emergency",
]
MEDIUM = [
    "ppi", "pce", "retail sales", "pmi", "ism", "jobless", "unemployment",
    "consumer confidence", "yields", "bailey", "minutes", "speech", "testimony",
]

def rx(words):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)

RE_KW, RE_HIGH, RE_MED = rx(KEYWORDS), rx(HIGH), rx(MEDIUM)

def impact(title):
    if RE_HIGH.search(title):
        return "🔴 Impatto alto"
    if RE_MED.search(title):
        return "🟠 Impatto medio"
    return "⚪ Impatto basso"

def tr(text):
    if not TRANSLATE or not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="it").translate(text) or text
    except Exception as e:
        print("Traduzione fallita:", e)
        return text

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
        json={"chat_id": CHANNEL, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=15,
    )
    if not r.ok:
        print(f"ERRORE TELEGRAM {r.status_code}: {r.text}")
    return r.ok

def fmt_news(label, title, link):
    t = html.escape(tr(title))
    return f"{label}  ·  {impact(title)}\n<b>{t}</b>\n{link}"

def fmt_cal(country, title, when, mins, forecast, previous):
    t = html.escape(tr(title))
    ora = when.astimezone(ROME).strftime("%H:%M")
    extra = f"\nPrevisione: {forecast or '-'}  |  Precedente: {previous or '-'}"
    return (f"⏰ <b>Tra circa {mins} min</b>\n"
            f"🔴 {country} · {t}\n🕒 {ora} (ora italiana){extra}")

def collect_news(seen_set):
    items = []
    now = time.time()
    for label, url, filtered in FEEDS:
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0")
        except Exception as e:
            print("Errore feed", label, e)
            continue
        print(f"{label}: {len(feed.entries)} voci")
        for e in reversed(feed.entries):
            uid = e.get("id") or e.get("link")
            if not uid or uid in seen_set:
                continue
            title = e.get("title", "").strip()
            ts = e.get("published_parsed") or e.get("updated_parsed")
            age_h = (now - timegm(ts)) / 3600 if ts else 0
            ok = age_h <= MAX_AGE_HOURS
            if filtered and not RE_KW.search(title):
                ok = False
            items.append((uid, ok, fmt_news, (label, title, e.get("link", ""))))
    return items

def collect_calendar(seen_set):
    items = []
    try:
        r = requests.get(CAL_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        events = r.json()
    except Exception as e:
        print("Calendario non disponibile:", e)
        return items
    now = datetime.now(timezone.utc)
    print(f"Calendario: {len(events)} eventi nella settimana")
    for ev in events:
        if ev.get("impact") != "High" or ev.get("country") not in CAL_COUNTRIES:
            continue
        try:
            when = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        uid = f"cal:{ev['date']}:{ev.get('country')}:{ev.get('title')}"
        if uid in seen_set:
            continue
        mins = int((when - now).total_seconds() // 60)
        if mins < 0:
            items.append((uid, False, fmt_cal, ()))
        elif mins <= CAL_WINDOW_MIN:
            items.append((uid, True, fmt_cal, (
                ev.get("country"), ev.get("title", ""), when, mins,
                ev.get("forecast"), ev.get("previous"))))
    return items

def main():
    seen = load_seen()
    first_run = seen is None
    seen = seen or []
    seen_set = set(seen)

    items = collect_news(seen_set) + collect_calendar(seen_set)

    sent = fails = 0
    for uid, ok, fmt, args in items:
        if first_run or not ok:
            seen.append(uid)
            continue
        if sent >= MAX_PER_RUN or fails >= 3:
            continue
        if send(fmt(*args)):
            seen.append(uid)
            sent += 1
            time.sleep(1)
        else:
            fails += 1
    print(f"Inviati: {sent}, errori: {fails}")
    save_seen(seen)

if __name__ == "__main__":
    main()
