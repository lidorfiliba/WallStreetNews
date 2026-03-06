"""
MarketAlert — GitHub Actions Check
בודק כל 5 דקות:
- דוחות רבעוניים (Earnings)
- נתוני מאקרו (CPI, PCE, NFP וכו')
- Insider buying מעל $500K
- תנועות חדות בשוק
- טסלה — דגש מיוחד
"""
import requests, json, re, os
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET

TG_BOT_TOKEN = "8055798978:AAGUJZnv1M5ZHAg2cxMmNzTDShNclh2PGig"
TG_CHAT_ID   = -1003609757340

STATE_FILE = "market_state.json"

TESLA_TICKER = "TSLA"

MACRO_KEYWORDS = [
    "CPI", "PCE", "NFP", "nonfarm", "inflation", "Federal Reserve",
    "FOMC", "interest rate", "GDP", "unemployment", "payrolls",
    "consumer price", "personal consumption", "jobs report",
]

MARKET_MOVE_KEYWORDS = [
    "crash", "surge", "plunge", "rally", "circuit breaker",
    "halted", "recession", "bear market", "bull market",
    "all-time high", "52-week low", "market selloff",
]

RSS_FEEDS = [
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US", "🔴 טסלה"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ&region=US&lang=en-US", "📊 שוק"),
    ("https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "📰 Reuters"),
    ("https://feeds.bloomberg.com/markets/news.rss", "💹 Bloomberg"),
]

SEC_EDGAR_TSLA  = "https://data.sec.gov/submissions/CIK0001318605.json"
SEC_INSIDER_URL = "https://efts.sec.gov/LATEST/search-index?q=%224%22&dateRange=custom&startdt={}&enddt={}&forms=4"

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {
            "sent": [],
            "last_tsla_filing": "",
            "last_insider_dt": "",
            "last_macro_title": "",
        }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
        r = requests.post(url, json=data, timeout=10)
        print(f"TG: {text[:80]}")
    except Exception as e:
        print(f"TG error: {e}")

def already_sent(state, key):
    return key in state["sent"]

def mark_sent(state, key):
    state["sent"].append(key)
    state["sent"] = state["sent"][-300:]

def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("utf-8", errors="ignore")
    except:
        return ""

def parse_rss_items(xml_text):
    items = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            pub   = item.findtext("pubDate", "").strip()
            if title:
                items.append({"title": title, "link": link, "pub": pub})
    except:
        pass
    return items

def parse_pub_date(pub_str):
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"]:
        try:
            return datetime.strptime(pub_str, fmt).replace(tzinfo=None)
        except:
            pass
    return None

def check_tesla_earnings(state):
    """בדיקת דוחות טסלה דרך SEC EDGAR"""
    try:
        headers = {"User-Agent": "market-alert-bot contact@example.com"}
        r = requests.get(SEC_EDGAR_TSLA, headers=headers, timeout=10)
        data = r.json()
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accnums = filings.get("accessionNumber", [])

        for i, form in enumerate(forms[:20]):
            if form in ("10-Q", "10-K", "8-K"):
                dt_str  = dates[i]
                acc     = accnums[i]
                key     = f"tsla_filing:{acc}"
                if already_sent(state, key):
                    continue
                # בדוק שזה חדש (24 שעות)
                try:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                    if (datetime.now() - dt).days > 1:
                        continue
                except:
                    continue

                form_name = {
                    "10-Q": "דוח רבעוני",
                    "10-K": "דוח שנתי",
                    "8-K":  "דיווח מיידי"
                }.get(form, form)

                url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type={form}&dateb=&owner=include&count=1"
                tg_send(
                    f"🔴 <b>טסלה — {form_name} ({form})</b>\n"
                    f"📅 תאריך: {dt_str}\n"
                    f"🔗 <a href='{url}'>SEC EDGAR</a>"
                )
                mark_sent(state, key)

    except Exception as e:
        print(f"Tesla EDGAR error: {e}")

def check_insider_buying(state):
    """בדיקת רכישות insider מ-SEC Form 4"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22P%22&forms=4&dateRange=custom&startdt={yesterday}&enddt={today}"
        headers = {"User-Agent": "market-alert-bot contact@example.com"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:10]:
            src = hit.get("_source", {})
            ticker    = src.get("period_of_report", "")
            entity    = src.get("entity_name", "")
            filed     = src.get("file_date", "")
            accnum    = src.get("accession_no", "")
            key       = f"insider:{accnum}"

            if already_sent(state, key):
                continue

            is_tesla = "tesla" in entity.lower()
            emoji    = "🔴" if is_tesla else "🐋"
            label    = " [TSLA]" if is_tesla else ""

            tg_send(
                f"{emoji} <b>Insider Buying{label}</b>\n"
                f"🏢 {entity}\n"
                f"📅 {filed}\n"
                f"🔗 https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=&State=0&SIC=&dateb=&owner=include&count=10&search_text="
            )
            mark_sent(state, key)

    except Exception as e:
        print(f"Insider error: {e}")

def check_rss_feeds(state):
    """בדיקת RSS לחדשות שוק ומאקרו"""
    now = datetime.now()

    for feed_url, label in RSS_FEEDS:
        xml = fetch_rss(feed_url)
        if not xml:
            continue
        items = parse_rss_items(xml)

        for item in items[:10]:
            title = item["title"]
            link  = item["link"]
            pub   = item["pub"]
            key   = f"rss:{title[:60]}"

            if already_sent(state, key):
                continue

            # בדוק שהכתבה חדשה (שעה אחרונה)
            pub_dt = parse_pub_date(pub)
            if pub_dt and (now - pub_dt).total_seconds() > 3600:
                continue

            is_tesla = "tesla" in title.lower() or "tsla" in title.lower()
            is_macro = any(kw.lower() in title.lower() for kw in MACRO_KEYWORDS)
            is_move  = any(kw.lower() in title.lower() for kw in MARKET_MOVE_KEYWORDS)
            is_earnings = any(w in title.lower() for w in ["earnings", "revenue", "profit", "eps", "beat", "miss", "quarterly"])

            if not any([is_tesla, is_macro, is_move, is_earnings]):
                continue

            if is_tesla:
                emoji = "🔴"
                tag   = "טסלה"
            elif is_macro:
                emoji = "📊"
                tag   = "מאקרו"
            elif is_earnings:
                emoji = "💰"
                tag   = "דוח רבעוני"
            elif is_move:
                emoji = "⚡"
                tag   = "תנועת שוק"
            else:
                emoji = "📰"
                tag   = "שוק"

            tg_send(
                f"{emoji} <b>{tag}</b>\n"
                f"{title}\n"
                f"🔗 {link}"
            )
            mark_sent(state, key)

def get_ticker_data(ticker):
    """שליפת מחיר ושינוי של מניה"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
    data = r.json()
    meta = data["chart"]["result"][0]["meta"]
    price  = meta.get("regularMarketPrice", 0)
    prev   = meta.get("chartPreviousClose", 0)
    change = ((price - prev) / prev * 100) if prev else 0
    return price, change

def check_opening_bell(state):
    """הודעת פתיחת מסחר ב-16:30 שעון ישראל = 13:30 UTC"""
    now = datetime.utcnow()
    key = f"opening:{now.strftime('%Y-%m-%d')}"

    # שלח בין 13:30 ל-13:34 UTC
    if not (now.hour == 13 and 30 <= now.minute <= 34):
        return
    if now.weekday() >= 5:  # לא בסוף שבוע
        return
    if already_sent(state, key):
        return

    try:
        tickers = ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"]
        lines = ["🔔 <b>פתיחת מסחר — וול סטריט (16:30 🇮🇱)</b>"]

        for ticker in tickers:
            price, change = get_ticker_data(ticker)
            arrow     = "🟢" if change >= 0 else "🔴"
            tsla_mark = " ⭐" if ticker == "TSLA" else ""
            lines.append(f"{arrow} {ticker}{tsla_mark}: ${price:.2f} ({change:+.2f}%)")

        tg_send("\n".join(lines))
        mark_sent(state, key)

    except Exception as e:
        print(f"Opening bell error: {e}")

def check_market_summary(state):
    """סיכום יומי ב-23:00 שעון ישראל = 20:00 UTC"""
    now = datetime.utcnow()
    key = f"summary:{now.strftime('%Y-%m-%d')}"

    if now.hour != 20 or already_sent(state, key):
        return
    if now.weekday() >= 5:  # לא בסוף שבוע
        return

    try:
        tickers = ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"]
        lines = ["📈 <b>סיכום יומי — סגירת שוק (23:00 🇮🇱)</b>"]

        for ticker in tickers:
            price, change = get_ticker_data(ticker)
            arrow     = "🟢" if change >= 0 else "🔴"
            tsla_mark = " ⭐" if ticker == "TSLA" else ""
            lines.append(f"{arrow} {ticker}{tsla_mark}: ${price:.2f} ({change:+.2f}%)")

        tg_send("\n".join(lines))
        mark_sent(state, key)

    except Exception as e:
        print(f"Summary error: {e}")

def main():
    state = load_state()

    check_tesla_earnings(state)
    check_insider_buying(state)
    check_rss_feeds(state)
    check_opening_bell(state)
    check_market_summary(state)

    save_state(state)
    print(f"Done. Sent keys: {len(state['sent'])}")

if __name__ == "__main__":
    main()
