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
    "CPI report", "CPI data", "PCE report", "PCE data",
    "nonfarm payrolls", "NFP report", "jobs report",
    "Federal Reserve raises", "Federal Reserve cuts", "Fed raises", "Fed cuts",
    "FOMC decision", "FOMC meeting", "interest rate decision",
    "GDP growth", "GDP report", "unemployment rate",
    "inflation data", "inflation report", "inflation rises", "inflation falls",
    "rate hike", "rate cut", "dovish", "hawkish",
    "consumer price index", "personal consumption expenditures",
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

# Nitter — מראה טוויטר חינמי עם RSS (מנסה כמה שרתים למקרה שאחד נפל)
NITTER_SERVERS = [
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
]

TWITTER_ACCOUNTS = [
    ("elonmusk",        "🔴⭐ אילון מאסק"),
    ("teslarati",       "⭐ Teslarati"),
    ("WholeMarsBlog",   "⭐ Tesla News"),
    ("DeItaone",        "📊 Delta One (חדשות שוק)"),
    ("unusual_whales",  "🐋 Unusual Whales"),
    ("zerohedge",       "📉 ZeroHedge"),
    ("AppEconomy",      "💰 App Economy (דוחות חברות)"),
    ("FinancialJuice",  "⚡ FinancialJuice (חדשות מהירות)"),
    ("CheddarFlow",     "🎯 CheddarFlow (אופציות חריגות)"),
]

TWITTER_FILTER_KEYWORDS = [
    "tesla", "tsla", "stock", "market", "fed", "rate", "inflation",
    "earnings", "spy", "nasdaq", "crash", "rally", "bullish", "bearish",
    "sec", "ipo", "merger", "acquisition", "billion", "million",
    "elon", "cybertruck", "model", "gigafactory",
    "unusual", "call", "put", "options", "sweep", "flow", "unusual activity",
]

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
            raw = r.read()
            for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    return raw.decode(enc, errors="ignore")
                except:
                    continue
            return raw.decode("utf-8", errors="ignore")
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

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def summarize_article(title, link):
    """שולף את תוכן הכתבה ומסכם בעברית עם Groq"""
    if not GROQ_API_KEY:
        return None
    try:
        # שלוף את תוכן הכתבה
        html = fetch_url(link)
        if not html:
            return None
        # נקה HTML — קח רק טקסט
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # קח עד 3000 תווים
        text = text[:3000]
        if len(text) < 200:
            return None

        prompt = f"""אתה עוזר פיננסי. קרא את הכתבה הבאה וסכם אותה בעברית.

כתוב סיכום מפורט של כל הנקודות החשובות:
- מה קרה?
- מה המשמעות לשווקים?
- אילו מספרים/נתונים חשובים מוזכרים?
- מה הצפי להמשך?

כתוב בצורה ברורה, 4-6 משפטים. רק את הסיכום עצמו, ללא כותרת.

כותרת: {title}
תוכן: {text}"""

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json; charset=utf-8"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=15
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq error: {e}")
        return None

def check_sharp_moves(state):
    """תנועות חדות — שולח רק כשיש שינוי חריג חדש"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not (now.weekday() < 5 and (now.hour > 13 or (now.hour == 13 and now.minute >= 30)) and now.hour < 20):
        return

    for ticker in WATCHLIST:
        price, change, volume, avg_vol = get_ticker(ticker)
        if abs(change) < MOVE_THRESHOLD:
            # אם המניה חזרה לנורמלי — נקה את ה-state שלה
            state.setdefault("last_move", {}).pop(ticker, None)
            continue

        # שלח רק אם השינוי גדל ב-1% לפחות מהפעם האחרונה
        last_change = state.setdefault("last_move", {}).get(ticker, 0)
        if abs(change) < abs(last_change) + 1.0 and last_change != 0:
            continue

        state["last_move"][ticker] = change

        arrow    = "🚀" if change > 0 else "💥"
        star     = " ⭐" if ticker == "TSLA" else ""
        vol_note = " | 🔥 נפח חריג" if avg_vol and volume > avg_vol * 1.5 else ""
        key      = f"move:{ticker}:{now.strftime('%Y-%m-%d')}:{int(abs(change))}"

        if sent(state, key):
            continue

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

            # זהה את המקור
            source = ""
            if "reuters" in link: source = "רויטרס"
            elif "yahoo" in link: source = "Yahoo Finance"
            elif "bloomberg" in link: source = "בלומברג"
            elif "cnbc" in link: source = "CNBC"
            elif "wsj" in link: source = "WSJ"
            else: source = link.split("/")[2].replace("www.","")

            summary = summarize_article(title, link)
            if summary:
                tg_send(f"{emoji} <b>{tag}</b>\n📌 <b>{title}</b>\n\n{summary}\n\n📰 מקור: {source}\n🔗 {link}")
            else:
                tg_send(f"{emoji} <b>{tag}</b>\n{title}\n📰 {source}\n🔗 {link}")
            mark(state, key)


def check_twitter_nitter(state):
    """ציוצים חמים מטוויטר דרך Nitter RSS"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for account, label in TWITTER_ACCOUNTS:
        feed_url = None

        # נסה כל שרת nitter עד שאחד עובד
        for server in NITTER_SERVERS:
            try:
                url = f"{server}/{account}/rss"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    xml = r.read().decode("utf-8", errors="ignore")
                if "<item>" in xml:
                    feed_url = url
                    break
            except:
                continue

        if not feed_url:
            continue

        try:
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()

                if not title:
                    continue

                key = f"tw:{account}:{title[:50]}"
                if sent(state, key):
                    continue

                # רק ציוצים מהשעה האחרונה
                pub_dt = parse_date(pub)
                if pub_dt and (now - pub_dt).total_seconds() > 3600:
                    continue

                # סנן לפי מילות מפתח רלוונטיות
                tl = title.lower()
                if not any(kw in tl for kw in TWITTER_FILTER_KEYWORDS):
                    # אם זה אילון מאסק — שלח הכל (כל ציוץ שלו רלוונטי)
                    if account != "elonmusk":
                        continue

                # המר קישור nitter לטוויטר אמיתי
                real_link = link.replace(NITTER_SERVERS[0], "https://twitter.com")
                for s in NITTER_SERVERS:
                    real_link = real_link.replace(s, "https://twitter.com")

                tg_send(
                    f"🐦 <b>{label}</b>\n"
                    f"{title[:280]}\n"
                    f"🔗 {real_link}"
                )
                mark(state, key)
        except Exception as e:
            print(f"Nitter parse error ({account}): {e}")

def check_opening_bell(state):
    """פתיחת מסחר 16:30 ישראל = 13:30 UTC"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"open:{now.strftime('%Y-%m-%d')}"
    if not (now.hour == 13 and 30 <= now.minute <= 34):
        return
    if now.weekday() >= 5 or sent(state, key):
        return

    lines = ["🔔 <b>פתיחת מסחר — וול סטריט 🇺🇸 (16:30 🇮🇱)</b>\n"]

    all_tickers = {}
    for ticker in ["SPY", "QQQ", "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]:
        price, change, volume, avg_vol = get_ticker(ticker)
        all_tickers[ticker] = (price, change)
        arrow = "🟢" if change >= 0 else "🔴"
        star  = "⭐ " if ticker == "TSLA" else ""
        lines.append(f"{arrow} {star}{ticker}: ${price:.2f} ({change:+.2f}%)")

    # מוביל עליות וירידות
    best  = max(all_tickers.items(), key=lambda x: x[1][1])
    worst = min(all_tickers.items(), key=lambda x: x[1][1])
    lines.append(f"\n🏆 מוביל יום: {best[0]} ({best[1][1]:+.2f}%)")
    lines.append(f"💥 מפסיד יום: {worst[0]} ({worst[1][1]:+.2f}%)")

    tg_send("\n".join(lines))
    mark(state, key)

def get_commodity(symbol):
    """שליפת מחיר סחורה/מט"ח מ-Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
        r   = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        meta   = r.json()["chart"]["result"][0]["meta"]
        price  = meta.get("regularMarketPrice", 0)
        prev   = meta.get("chartPreviousClose", 0)
        change = ((price - prev) / prev * 100) if prev else 0
        return price, change
    except:
        return 0, 0

def check_daily_summary(state):
    """סיכום יומי 23:00 ישראל = 20:00 UTC"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"summary:{now.strftime('%Y-%m-%d')}"
    if now.hour != 20 or now.weekday() >= 5 or sent(state, key):
        return

    today = now.strftime("%d.%m.%Y")
    lines = [f"📉📈 <b>יום המסחר הסתיים — {today}</b>\n"]
    winners, losers = [], []

    # מדדים
    lines.append("📊 <b>מדדים</b>")
    for ticker in ["SPY", "QQQ", "DIA"]:
        price, change, _, _ = get_ticker(ticker)
        arrow = "🟢" if change >= 0 else "🔴"
        names = {"SPY": "סאנדפי 500", "QQQ": "נאסדק 100", "DIA": "דאו ג'ונס"}
        lines.append(f"{arrow} {names[ticker]}: ${price:.2f} ({change:+.2f}%)")

    # מניות
    lines.append("\n🏦 <b>מניות</b>")
    all_stocks = {}
    for ticker in ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]:
        price, change, _, _ = get_ticker(ticker)
        all_stocks[ticker] = (price, change)
        arrow = "🟢" if change >= 0 else "🔴"
        star  = "⭐ " if ticker == "TSLA" else ""
        lines.append(f"{arrow} {star}{ticker}: ${price:.2f} ({change:+.2f}%)")
        if change > 0:
            winners.append(f"{ticker} +{change:.1f}%")
        else:
            losers.append(f"{ticker} {change:.1f}%")

    # מוביל עליות וירידות היום
    if all_stocks:
        best  = max(all_stocks.items(), key=lambda x: x[1][1])
        worst = min(all_stocks.items(), key=lambda x: x[1][1])
        lines.append(f"\n🏆 <b>מוביל היום:</b> {best[0]} ({best[1][1]:+.2f}%)")
        lines.append(f"💥 <b>מפסיד היום:</b> {worst[0]} ({worst[1][1]:+.2f}%)")

    # סחורות
    lines.append("\n🛢️ <b>סחורות ומתכות</b>")
    commodities = [
        ("GC=F", "🥇 זהב",  "$", 0),
        ("SI=F", "🥈 כסף",  "$", 2),
        ("CL=F", "🛢️ נפט",  "$", 2),
    ]
    for symbol, label, prefix, decimals in commodities:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: {prefix}{price:.{decimals}f} ({change:+.2f}%)")

    # מט"ח
    lines.append("\n💱 <b>שערי חליפין</b>")
    forex = [
        ("USDILS=X", "💵 דולר-שקל"),
        ("EURILS=X", "💶 יורו-שקל"),
        ("EURUSD=X", "💶 יורו-דולר"),
    ]
    for symbol, label in forex:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: ₪{price:.3f} ({change:+.2f}%)")

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

    # מניות
    lines.append("🏦 <b>מניות</b>")
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

    # סחורות
    lines.append("\n🛢️ <b>סחורות ומתכות</b>")
    for symbol, label, prefix, decimals in [("GC=F","🥇 זהב","$",0),("SI=F","🥈 כסף","$",2),("CL=F","🛢️ נפט","$",2)]:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: {prefix}{price:.{decimals}f} ({change:+.2f}% השבוע)")

    # מט"ח
    lines.append("\n💱 <b>שערי חליפין</b>")
    for symbol, label in [("USDILS=X","💵 דולר-שקל"),("EURILS=X","💶 יורו-שקל")]:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: ₪{price:.3f} ({change:+.2f}% השבוע)")

    tg_send("\n".join(lines))
    mark(state, key)

# ── main ─────────────────────────────────────────────────

def main():
    state = load_state()

    check_sharp_moves(state)
    check_tesla_filings(state)
    check_insider(state)
    check_news(state)
    check_twitter_nitter(state)
    check_opening_bell(state)
    check_daily_summary(state)
    check_weekly_summary(state)

    save_state(state)
    print(f"Done. Keys: {len(state['sent'])}")

if __name__ == "__main__":
    main()
