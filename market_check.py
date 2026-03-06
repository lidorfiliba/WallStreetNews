"""
MarketAlert v2 — GitHub Actions
בודק כל 5 דקות — קבוצה אחת לכל הפעולות
"""
import requests, json, re, os
from datetime import datetime, timedelta, timezone
import urllib.request
import xml.etree.ElementTree as ET

TG_BOT_TOKEN = "8055798978:AAGUJZnv1M5ZHAg2cxMmNzTDShNclh2PGig"
TG_CHAT_ID   = -1003609757340
STATE_FILE   = "market_state.json"

WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "SPY", "QQQ"]
MOVE_THRESHOLD = 3.0  # % שינוי חד

MACRO_KEYWORDS = [
    "CPI", "PCE", "NFP", "nonfarm", "inflation", "Federal Reserve",
    "FOMC", "interest rate", "GDP", "unemployment", "payrolls",
    "consumer price", "personal consumption", "jobs report", "rate hike",
    "rate cut", "dovish", "hawkish", "recession",
]

MARKET_MOVE_KEYWORDS = [
    "crash", "surge", "plunge", "rally", "circuit breaker", "halted",
    "bear market", "bull market", "all-time high", "52-week low",
    "market selloff", "black monday", "meltdown",
]

EARNINGS_KEYWORDS = [
    "earnings beat", "earnings miss", "earnings per share",
    "quarterly results", "quarterly earnings", "revenue beat",
    "revenue miss", "eps beat", "eps miss", "raised guidance",
    "lowered guidance", "beats estimates", "misses estimates",
    "reports earnings", "posted earnings",
]

TESLA_KEYWORDS = [
    "tesla", "tsla", "elon musk", "elon", "cybertruck",
    "model 3", "model y", "model s", "gigafactory", "supercharger",
]

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,NVDA&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
]

SEC_TSLA = "https://data.sec.gov/submissions/CIK0001318605.json"
STOCKTWITS_TSLA = "https://api.stocktwits.com/api/2/streams/symbol/TSLA.json"
FEAR_GREED = "https://fear-and-greed-index.p.rapidapi.com/v1/fgi"

# ── helpers ──────────────────────────────────────────────

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"sent": [], "weekly_key": "", "prices": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": True}
        r = requests.post(url, json=data, timeout=10)
        print(f"✅ TG: {text[:80]}")
    except Exception as e:
        print(f"TG error: {e}")

def sent(state, key):
    return key in state["sent"]

def mark(state, key):
    state["sent"].append(key)
    state["sent"] = state["sent"][-500:]

def fetch_url(url, headers=None):
    try:
        h = {"User-Agent": "Mozilla/5.0"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("utf-8", errors="ignore")
    except:
        return ""

def get_ticker(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        data = r.json()
        meta   = data["chart"]["result"][0]["meta"]
        price  = meta.get("regularMarketPrice", 0)
        prev   = meta.get("chartPreviousClose", 0)
        change = ((price - prev) / prev * 100) if prev else 0
        volume = meta.get("regularMarketVolume", 0)
        avg_vol= meta.get("averageDailyVolume10Day", 1)
        return price, change, volume, avg_vol
    except:
        return 0, 0, 0, 1

def parse_rss(url):
    items = []
    xml = fetch_url(url)
    if not xml:
        return items
    try:
        root = ET.fromstring(xml)
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            pub   = item.findtext("pubDate", "").strip()
            if title:
                items.append({"title": title, "link": link, "pub": pub})
    except:
        pass
    return items

def parse_date(s):
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"]:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=None)
        except:
            pass
    return None

# ── checks ───────────────────────────────────────────────

def check_sharp_moves(state):
    """תנועות חדות מעל 3% בזמן מסחר"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # רק בשעות מסחר 13:30-20:00 UTC
    if not (now.weekday() < 5 and (now.hour > 13 or (now.hour == 13 and now.minute >= 30)) and now.hour < 20):
        return

    for ticker in WATCHLIST:
        price, change, volume, avg_vol = get_ticker(ticker)
        if abs(change) < MOVE_THRESHOLD:
            continue

        key = f"move:{ticker}:{now.strftime('%Y-%m-%d')}:{int(abs(change))}"
        if sent(state, key):
            continue

        arrow    = "🚀" if change > 0 else "💥"
        is_tesla = ticker == "TSLA"
        star     = " ⭐" if is_tesla else ""
        vol_note = ""
        if avg_vol and volume > avg_vol * 1.5:
            vol_note = " | 🔥 נפח חריג"

        tg_send(
            f"{arrow} <b>תנועה חדה{star} — {ticker}</b>\n"
            f"💲 ${price:.2f}  ({change:+.2f}%){vol_note}"
        )
        mark(state, key)

def check_tesla_filings(state):
    """דוחות טסלה מ-SEC EDGAR"""
    try:
        headers = {"User-Agent": "market-alert contact@example.com"}
        r = requests.get(SEC_TSLA, headers=headers, timeout=10)
        data    = r.json()
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accs    = filings.get("accessionNumber", [])

        for i, form in enumerate(forms[:15]):
            if form not in ("10-Q", "10-K", "8-K"):
                continue
            key = f"tsla:{accs[i]}"
            if sent(state, key):
                continue
            try:
                dt = datetime.strptime(dates[i], "%Y-%m-%d")
                if (datetime.now() - dt).days > 1:
                    continue
            except:
                continue

            names = {"10-Q": "דוח רבעוני", "10-K": "דוח שנתי", "8-K": "דיווח מיידי"}
            link  = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type={form}&dateb=&owner=include&count=1"
            tg_send(
                f"🔴⭐ <b>טסלה — {names[form]} ({form})</b>\n"
                f"📅 {dates[i]}\n"
                f"🔗 <a href='{link}'>SEC EDGAR</a>"
            )
            mark(state, key)
    except Exception as e:
        print(f"EDGAR error: {e}")

def check_insider(state):
    """Insider buying מ-SEC Form 4"""
    try:
        today     = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22P%22&forms=4&dateRange=custom&startdt={yesterday}&enddt={today}"
        r   = requests.get(url, headers={"User-Agent": "market-alert contact@example.com"}, timeout=10)
        hits = r.json().get("hits", {}).get("hits", [])

        for hit in hits[:15]:
            src    = hit.get("_source", {})
            entity = src.get("entity_name", "")
            filed  = src.get("file_date", "")
            acc    = src.get("accession_no", "")
            key    = f"insider:{acc}"
            if sent(state, key):
                continue

            is_tesla = "tesla" in entity.lower()
            emoji    = "🔴⭐" if is_tesla else "🐋"
            label    = " [TSLA]" if is_tesla else ""
            acc_fmt = acc.replace("-", "")
            link    = f"https://www.sec.gov/Archives/edgar/data/{acc_fmt[:10]}/{acc_fmt}/{acc}-index.htm"
            tg_send(
                f"{emoji} <b>Insider Buying{label}</b>\n"
                f"🏢 {entity}\n"
                f"📅 {filed}\n"
                f"🔗 https://efts.sec.gov/LATEST/search-index?q=%22{acc}%22&forms=4"
            )
            mark(state, key)
    except Exception as e:
        print(f"Insider error: {e}")

def check_news(state):
    """חדשות שוק, מאקרו, טסלה ודוחות"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for feed_url in RSS_FEEDS:
        for item in parse_rss(feed_url)[:8]:
            title = item["title"]
            link  = item["link"]
            key   = f"news:{title[:60]}"
            if sent(state, key):
                continue

            pub_dt = parse_date(item["pub"])
            if pub_dt and (now - pub_dt).total_seconds() > 3600:
                continue

            tl = title.lower()
            is_tesla    = any(k in tl for k in TESLA_KEYWORDS)
            is_macro    = any(k.lower() in tl for k in MACRO_KEYWORDS)
            is_earnings = any(k in tl for k in EARNINGS_KEYWORDS)
            is_move     = any(k in tl for k in MARKET_MOVE_KEYWORDS)

            if not any([is_tesla, is_macro, is_earnings, is_move]):
                continue

            if is_tesla:
                emoji, tag = "🔴⭐", "טסלה"
            elif is_macro:
                emoji, tag = "📊", "מאקרו"
            elif is_earnings:
                emoji, tag = "💰", "דוח רבעוני"
            else:
                emoji, tag = "⚡", "תנועת שוק"

            tg_send(f"{emoji} <b>{tag}</b>\n{title}\n🔗 {link}")
            mark(state, key)

def check_stocktwits_tsla(state):
    """טרנדים חמים על טסלה מ-StockTwits"""
    try:
        r    = requests.get(STOCKTWITS_TSLA, timeout=8)
        msgs = r.json().get("messages", [])
        for msg in msgs[:5]:
            mid  = str(msg.get("id", ""))
            key  = f"st:{mid}"
            if sent(state, key):
                continue

            body      = msg.get("body", "")
            sentiment = msg.get("entities", {}).get("sentiment", {})
            sen_label = sentiment.get("basic", "") if sentiment else ""
            created   = msg.get("created_at", "")

            # רק הודעות עם sentiment ברור
            if sen_label not in ("Bullish", "Bearish"):
                continue

            # בדוק שההודעה מהשעה האחרונה
            try:
                dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
                if (datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds() > 3600:
                    continue
            except:
                continue

            emoji = "🟢" if sen_label == "Bullish" else "🔴"
            tg_send(
                f"{emoji}⭐ <b>StockTwits — TSLA ({sen_label})</b>\n"
                f"{body[:200]}"
            )
            mark(state, key)
    except Exception as e:
        print(f"StockTwits error: {e}")

def check_opening_bell(state):
    """פתיחת מסחר 16:30 ישראל = 13:30 UTC"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"open:{now.strftime('%Y-%m-%d')}"
    if not (now.hour == 13 and 30 <= now.minute <= 34):
        return
    if now.weekday() >= 5 or sent(state, key):
        return

    lines = ["🔔 <b>פתיחת מסחר — וול סטריט 🇺🇸 (16:30 🇮🇱)</b>\n"]
    for ticker in ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"]:
        price, change, volume, avg_vol = get_ticker(ticker)
        arrow = "🟢" if change >= 0 else "🔴"
        star  = "⭐ " if ticker == "TSLA" else ""
        lines.append(f"{arrow} {star}{ticker}: ${price:.2f} ({change:+.2f}%)")

    tg_send("\n".join(lines))
    mark(state, key)

def check_daily_summary(state):
    """סיכום יומי 23:00 ישראל = 20:00 UTC"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"summary:{now.strftime('%Y-%m-%d')}"
    if now.hour != 20 or now.weekday() >= 5 or sent(state, key):
        return

    lines = ["📈 <b>סיכום יומי — סגירת שוק (23:00 🇮🇱)</b>\n"]
    winners, losers = [], []

    for ticker in ["SPY", "QQQ", "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META"]:
        price, change, _, _ = get_ticker(ticker)
        arrow = "🟢" if change >= 0 else "🔴"
        star  = "⭐ " if ticker == "TSLA" else ""
        lines.append(f"{arrow} {star}{ticker}: ${price:.2f} ({change:+.2f}%)")
        if change > 0:
            winners.append(f"{ticker} +{change:.1f}%")
        else:
            losers.append(f"{ticker} {change:.1f}%")

    if winners:
        lines.append(f"\n🏆 <b>מובילי עליות:</b> {', '.join(winners[:3])}")
    if losers:
        lines.append(f"📉 <b>מובילי ירידות:</b> {', '.join(losers[:3])}")

    tg_send("\n".join(lines))
    mark(state, key)

def check_weekly_summary(state):
    """סיכום שבועי כל יום שישי ב-20:00 UTC"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"weekly:{now.strftime('%Y-W%W')}"
    if now.weekday() != 4 or now.hour != 20 or sent(state, key):
        return

    lines = ["📊 <b>סיכום שבועי 🗓️</b>\n"]
    for ticker in ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1wk&range=1wk"
            r   = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            meta = r.json()["chart"]["result"][0]["meta"]
            price  = meta.get("regularMarketPrice", 0)
            prev   = meta.get("chartPreviousClose", 0)
            change = ((price - prev) / prev * 100) if prev else 0
            arrow  = "🟢" if change >= 0 else "🔴"
            star   = "⭐ " if ticker == "TSLA" else ""
            lines.append(f"{arrow} {star}{ticker}: ${price:.2f} ({change:+.2f}% השבוע)")
        except:
            pass

    tg_send("\n".join(lines))
    mark(state, key)

# ── main ─────────────────────────────────────────────────

def main():
    state = load_state()

    check_sharp_moves(state)
    check_tesla_filings(state)
    check_insider(state)
    check_news(state)
    check_stocktwits_tsla(state)
    check_opening_bell(state)
    check_daily_summary(state)
    check_weekly_summary(state)

    save_state(state)
    print(f"Done. Keys: {len(state['sent'])}")

if __name__ == "__main__":
    main()
