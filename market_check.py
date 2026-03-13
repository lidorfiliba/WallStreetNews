"""
MarketAlert v2 — GitHub Actions
בודק כל 5 דקות — קבוצה אחת לכל הפעולות
"""
import requests, json, re, os
from datetime import datetime, timedelta, timezone
import urllib.request
import xml.etree.ElementTree as ET


# לוח שנה רשמי של NYSE 2026
NYSE_HOLIDAYS = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}
NYSE_SHORT_DAYS = {
    "2026-11-27": 18,  # Day after Thanksgiving — סגירה 13:00 ET = 18:00 UTC
    "2026-12-24": 18,  # Christmas Eve — סגירה 13:00 ET = 18:00 UTC
}

def is_trading_day(date_str=None):
    from datetime import datetime, timezone
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:
        return False
    if date_str in NYSE_HOLIDAYS:
        return False
    return True

def get_close_hour_utc(date_str=None):
    from datetime import datetime, timezone
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return NYSE_SHORT_DAYS.get(date_str, 20)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID   = -1003549323911
STATE_FILE   = "market_state.json"

WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "SPY", "QQQ"]
MOVE_THRESHOLD = 3.0  # % שינוי חד

MACRO_KEYWORDS = [
    "cpi", "pce", "nonfarm", "nfp", "jobs report", "payrolls",
    "federal reserve", "fed reserve", "fed governor", "fed chair",
    "fomc", "interest rate", "rate hike", "rate cut", "rate decision",
    "gdp", "unemployment", "inflation", "dovish", "hawkish",
    "powell", "treasury", "yield curve", "recession",
]

MARKET_MOVE_KEYWORDS = [
    "crash", "surge", "plunge", "rally", "soar", "tumble", "sink",
    "circuit breaker", "halted", "bear market", "bull market",
    "all-time high", "52-week", "selloff", "sell-off", "meltdown",
    "market risk", "concentration risk", "war", "geopolitical",
    "tariff", "sanctions", "trade war",
]

EARNINGS_KEYWORDS = [
    "earnings", "revenue", "eps", "quarterly", "guidance",
    "beats", "misses", "results", "profit", "loss", "outlook",
]

ELON_NOISE = [
    "mother", "girlfriend", "wife", "children", "kids", "family",
    "house", "home", "living", "lifestyle", "personal",
    "richest", "billionaire", "net worth", "fashion", "dating",
    "grimes", "baby", "biography", "childhood",
    "iran", "khamenei", "supreme leader", "political", "president", "senator", "congress",
]

TESLA_KEYWORDS = [
    "tesla", "tsla", "elon musk", "elon", "cybertruck",
    "model 3", "model y", "model s", "gigafactory",
    "spacex", "doge", "department of government",
]

MAG7_KEYWORDS = [
    # Apple
    "apple", "aapl", "tim cook", "iphone", "ipad", "mac", "app store",
    # Microsoft
    "microsoft", "msft", "satya nadella", "azure", "copilot", "openai",
    # Google
    "google", "googl", "alphabet", "sundar pichai", "gemini", "youtube",
    # Amazon
    "amazon", "amzn", "andy jassy", "aws", "prime",
    # Meta
    "meta", "facebook", "instagram", "whatsapp", "mark zuckerberg", "zuckerberg",
    # Nvidia
    "nvidia", "nvda", "jensen huang", "blackwell", "cuda", "h100", "h200",
]

BIG_COMPANIES = [
    # MAG7
    "apple", "aapl", "microsoft", "msft", "google", "googl", "alphabet",
    "amazon", "amzn", "meta", "facebook", "nvidia", "nvda", "tesla", "tsla",
    # ענקיות נוספות $450B+
    "berkshire", "eli lilly", "lilly", "jpmorgan", "jp morgan", "visa",
    "mastercard", "walmart", "exxon", "johnson", "unitedhealth", "broadcom",
    "netflix", "nflx", "costco", "salesforce", "oracle", "amd", "intel",
    "taiwan semiconductor", "tsmc", "samsung", "asml", "novo nordisk",
    "lvmh", "hermes", "toyota", "samsung", "tencent", "alibaba",
    # ביג בנקים
    "goldman sachs", "morgan stanley", "bank of america", "wells fargo", "citigroup",
    # מדוברות
    "openai", "anthropic", "spacex", "palantir", "coinbase", "robinhood",
    "rivian", "lucid", "arm holdings", "arm",
]

RSS_FEEDS = [
    # CNBC — תקציר אמיתי בתוך ה-RSS, קישורים אמיתיים
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",  # CNBC Markets
    # Yahoo Finance — כיסוי רחב, בלי סיכום אם חסום
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,NVDA,AAPL&region=US&lang=en-US",
    # Google News — כיסוי רחב
    "https://news.google.com/rss/search?q=tesla+TSLA+elon+musk&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=federal+reserve+fed+inflation+CPI&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=CPI+consumer+price+index+february+2026&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=inflation+data+report+today&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=earnings+beat+miss+quarterly+results&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=unusual+options+insider+buying&hl=en&gl=US&ceid=US:en",
]

SEC_TSLA = "https://data.sec.gov/submissions/CIK0001318605.json"

# Nitter — מראה טוויטר חינמי עם RSS (מנסה כמה שרתים למקרה שאחד נפל)
GOOGLE_NEWS_FEEDS = [
    ("https://news.google.com/rss/search?q=elon+musk&hl=en&gl=US&ceid=US:en",                   "🔴⭐ אילון מאסק"),
    ("https://news.google.com/rss/search?q=tesla+stock+TSLA&hl=en&gl=US&ceid=US:en",             "⭐ טסלה"),
    ("https://news.google.com/rss/search?q=unusual+options+activity+sweep&hl=en&gl=US&ceid=US:en","🎯 אופציות חריגות"),
    ("https://news.google.com/rss/search?q=stock+market+crash+OR+rally&hl=en&gl=US&ceid=US:en",  "📊 שוק ההון"),
    ("https://news.google.com/rss/search?q=federal+reserve+interest+rate&hl=en&gl=US&ceid=US:en","🏦 פד"),
    ("https://news.google.com/rss/search?q=nvidia+NVDA+stock&hl=en&gl=US&ceid=US:en",            "🟢 אנבידיה"),
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

def fetch_url(url, headers=None, timeout=5):
    try:
        h = {"User-Agent": "Mozilla/5.0"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
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
        # range=5d כדי לקבל נתוני close של יום המסחר הקודם
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        data = r.json()
        result = data["chart"]["result"][0]
        meta   = result["meta"]
        price  = meta.get("regularMarketPrice", 0)
        # קח את הסגירה של יום המסחר הקודם מתוך הנרות
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        prev = closes[-2] if len(closes) >= 2 else (closes[-1] if closes else meta.get("regularMarketPreviousClose", 0))
        change = ((price - prev) / prev * 100) if prev else 0
        volume = meta.get("regularMarketVolume", 0)
        avg_vol= meta.get("averageDailyVolume10Day", 1)
        return price, change, volume, avg_vol
    except:
        return 0, 0, 0, 1

def extract_real_link(link, item_xml=None):
    """מוציא קישור אמיתי מ-Google News — רק מה-guid, בלי redirect"""
    if "news.google.com" not in link:
        return link
    if item_xml is not None:
        guid = item_xml.findtext("guid") or ""
        if guid and "news.google.com" not in guid and guid.startswith("http"):
            return guid
    return link  # שמור את הקישור כמו שהוא — אל תנסה redirect

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
            desc  = item.findtext("description", "").strip()
            # נקה HTML מה-description
            desc = re.sub(r'<[^>]+>', ' ', desc)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if title:
                if "news.google.com" in link:
                    link = extract_real_link(link, item)
                items.append({"title": title, "link": link, "pub": pub, "desc": desc})
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

def title_fingerprint(title):
    """מחזיר טביעת אצבע של הכותרת — מילים משמעותיות בלי מקורות/מילות קישור"""
    stop = {"a","an","the","in","on","at","of","to","for","and","or","but",
            "as","is","are","was","were","by","from","with","that","this",
            "it","its","be","has","have","had","will","says","say","amid"}
    words = re.findall(r'\b[a-z]+\b', title.lower())
    key_words = [w for w in words if w not in stop and len(w) > 2]
    return " ".join(sorted(key_words[:6]))  # 6 מילות מפתח ממוינות

COMMODITIES_KEYWORDS = [
    "oil", "crude", "wti", "brent", "opec", "barrel", "petroleum", "gasoline",
    "gold", "silver", "xau", "xag", "bullion", "precious metals",
    "natural gas", "copper", "commodities",
]

BLOCKED_DOMAINS = ["fool.com", "seekingalpha.com", "wsj.com", "barrons.com", "ft.com", "finance.yahoo.com", "uk.finance.yahoo.com", "marketwatch.com", "247wallst.com", "benzinga.com", "investorplace.com", "thestreet.com", "bloomberg.com", "businessinsider.com", "tradingview.com", "tipranks.com"]

def summarize_article(title, link, rss_desc=""):
    """מסכם כתבה — קודם מנסה לשלוף, אחרת משתמש ב-description מה-RSS"""
    if not GROQ_API_KEY:
        return None

    text = None

    # נסה לשלוף את הכתבה (אלא אם חסומה)
    if not any(d in link for d in BLOCKED_DOMAINS) and "news.google.com" not in link:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            html = fetch_url(link, headers=headers, timeout=5)
            if html:
                t = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
                t = re.sub(r'<[^>]+>', ' ', t)
                t = re.sub(r'\s+', ' ', t).strip()
                # קח 4000 תווים מהאמצע — שם נמצא תוכן הכתבה
                mid = len(t) // 3
                t = t[mid:mid + 4000]
                block = ["subscribe to read","sign in","create an account","403 forbidden","access denied"]
                if not any(p in t.lower() for p in block) and len(t) >= 500:
                    text = t
        except:
            pass

    # אם לא הצלחנו — השתמש ב-description מה-RSS
    # בדוק אם הכותרת מכילה מקור חסום (Google News מוסיף "- Source" בסוף)
    BLOCKED_SOURCES = ["Benzinga", "Seeking Alpha", "MarketWatch", "Barron's", "WSJ",
        "The Wall Street Journal", "Bloomberg", "Business Insider", "The Motley Fool",
        "InvestorPlace", "TheStreet", "TipRanks", "TradingView"]
    if any(src.lower() in title.lower() for src in BLOCKED_SOURCES):
        print(f"BLOCKED source in title: {title[:60]}")
        return None
    if not text and len(rss_desc) > 80:
        if not any(d in link for d in BLOCKED_DOMAINS) and not any(d in rss_desc for d in BLOCKED_DOMAINS):
            text = rss_desc

    if not text:
        return None

    try:
        prompt = f"""אתה מסכם חדשות פיננסיות מקצועי. סכם את הכתבה בעברית בפורמט הבא בדיוק:

שורת פתיחה: משפט אחד תמציתי שמסכם את הכותרת הראשית (ללא נקודה בסוף).

ואז 3-4 נקודות bullet בפורמט:
• [נקודה עיקרית ראשונה — עם פרטים ספציפיים, מספרים, שמות]
• [נקודה שנייה]
• [נקודה שלישית]
• [נקודה רביעית אם רלוונטית]

חוקים חשובים:
- השתמש אך ורק במידע שמופיע בטקסט
- כלול מספרים, אחוזים, שמות ספציפיים כשיש
- אם מספר או פרט חסר — אל תכתוב placeholder ריק, פשוט השמט את הפרט הזה
- אם זה לא חדשות פיננסיות, ענה: SKIP
- אל תוסיף כותרת "סיכום:" בהתחלה

כותרת: {title}
טקסט: {text}

סיכום:"""

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 600, "temperature": 0.1},
            timeout=15
        )
        result = r.json()["choices"][0]["message"]["content"].strip()
        if result.upper() == "SKIP" or len(result) < 40:
            return None
        return result[:900]
    except Exception as e:
        print(f"Groq error: {e}")
        return None


def check_sharp_moves(state):
    """תנועות חדות — שולח רק כשיש שינוי חריג חדש"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"sharp_moves check: {now.strftime('%H:%M')} UTC, weekday={now.weekday()}")
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

            if not acc or not entity or len(acc) < 5:
                continue
            key    = f"insider:{acc}"
            if sent(state, key):
                continue

            is_tesla = "tesla" in entity.lower()
            emoji    = "🔴⭐" if is_tesla else "🐋"
            label    = " [TSLA]" if is_tesla else ""
            link    = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={entity[:30]}&type=4&dateb=&owner=include&count=5"
            tg_send(
                f"{emoji} <b>Insider Buying{label}</b>\n"
                f"🏢 {entity}\n"
                f"📅 {filed}\n"
                f"🔗 {link}"
            )
            mark(state, key)
    except Exception as e:
        print(f"Insider error: {e}")

def check_news(state):
    print("=== check_news started ===")
    """חדשות שוק, מאקרו, טסלה ודוחות"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for feed_url in RSS_FEEDS:
        for item in parse_rss(feed_url)[:8]:
            title = item["title"]
            link  = item["link"]
            key   = f"news:{title_fingerprint(title)}"
            if sent(state, key):
                continue

            pub_dt = parse_date(item["pub"])
            if pub_dt and (now - pub_dt).total_seconds() > 10800:
                continue

            tl = title.lower()
            is_tesla    = any(k in tl for k in TESLA_KEYWORDS)
            is_mag7     = any(k in tl for k in MAG7_KEYWORDS)
            is_macro    = any(k.lower() in tl for k in MACRO_KEYWORDS)
            is_earnings = any(k in tl for k in EARNINGS_KEYWORDS) and any(c in tl for c in BIG_COMPANIES)
            is_move     = any(k in tl for k in MARKET_MOVE_KEYWORDS)

            if not any([is_tesla, is_mag7, is_macro, is_earnings, is_move]):
                print(f"SKIP no-keyword: {title[:60]}")
                continue
            print(f"PASS keyword: {title[:60]}")

            # סנן מקורות לא אמינים לסיכום
            if any(d in link for d in BLOCKED_DOMAINS):
                continue

            if is_tesla:
                if getattr(check_news, "_tesla_count", 0) >= 2:
                    continue
                check_news._tesla_count = getattr(check_news, "_tesla_count", 0) + 1
                emoji, tag = "🔴⭐", "טסלה"
            elif is_mag7:
                # זהה איזו חברה ספציפית מוזכרת
                mag7_names = {
                    "apple": ("🍎", "Apple"),
                    "aapl": ("🍎", "Apple"),
                    "iphone": ("🍎", "Apple"),
                    "ipad": ("🍎", "Apple"),
                    "tim cook": ("🍎", "Apple"),
                    "microsoft": ("🪟", "Microsoft"),
                    "msft": ("🪟", "Microsoft"),
                    "google": ("🔍", "Google"),
                    "googl": ("🔍", "Google"),
                    "alphabet": ("🔍", "Google"),
                    "amazon": ("📦", "Amazon"),
                    "amzn": ("📦", "Amazon"),
                    "meta": ("👤", "Meta"),
                    "facebook": ("👤", "Meta"),
                    "nvidia": ("🟢", "Nvidia"),
                    "nvda": ("🟢", "Nvidia"),
                    "netflix": ("🎬", "Netflix"),
                    "nflx": ("🎬", "Netflix"),
                }
                found_companies = []
                for kw, (em, name) in mag7_names.items():
                    if kw in tl and name not in found_companies:
                        found_companies.append((em, name))
                if len(found_companies) == 1:
                    emoji, tag = found_companies[0][0], found_companies[0][1]
                elif len(found_companies) > 1:
                    emoji, tag = "📊", "תנועות שוק"
                else:
                    emoji, tag = "📊", "תנועות שוק"
            elif is_macro:
                emoji, tag = "📊", "מאקרו"
            elif is_earnings:
                emoji, tag = "💰", "דוח רבעוני"
            else:
                emoji, tag = "⚡", "תנועת שוק"

            source = link.split("/")[2].replace("www.","") if "http" in link else ""
            # אם הקישור עדיין של Google News — אל תציג אותו
            if "news.google.com" in link:
                summary = summarize_article(title, link, item.get("desc",""))
                print(f"SENDING: {title[:50]}, summary={bool(summary)}")
                if summary:
                    tg_send(f"{emoji} <b>{tag}</b>\n📌 <b>{title}</b>\n\n{summary}")
                elif not any(src.lower() in title.lower() for src in ["Motley Fool","Seeking Alpha","Benzinga","MarketWatch","Barron","InvestorPlace","TheStreet"]):
                    tg_send(f"{emoji} <b>{tag}</b>\n📌 <b>{title}</b>")
                else:
                    print(f"SKIP blocked-source no-summary: {title[:60]}")
                    continue
            else:
                summary = summarize_article(title, link, item.get("desc",""))
                if summary:
                    tg_send(f"{emoji} <b>{tag}</b>\n📌 <b>{title}</b>\n\n{summary}\n\n📰 {source}\n🔗 {link}")
                else:
                    tg_send(f"{emoji} <b>{tag}</b>\n📌 <b>{title}</b>\n📰 {source}\n🔗 {link}")
            mark(state, key)


def check_twitter_nitter(state):
    """חדשות מ-Google News RSS (החליף את Nitter)"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for feed_url, label in GOOGLE_NEWS_FEEDS:
        try:
            items = parse_rss(feed_url)
            for item in items[:5]:
                title = item["title"]
                link  = item["link"]
                pub   = item["pub"]

                key = f"gnews:{title_fingerprint(title)}"
                if sent(state, key):
                    continue

                pub_dt = parse_date(pub)
                if pub_dt and (now - pub_dt).total_seconds() > 10800:
                    continue

                tl = title.lower()
                if not any(kw in tl for kw in TWITTER_FILTER_KEYWORDS):
                    if "אילון" not in label and "טסלה" not in label:
                        continue

                source = link.split("/")[2].replace("www.","") if "http" in link and "news.google.com" not in link else ""
                summary = summarize_article(title, link, item.get("desc",""))
                if summary:
                    msg = f"📰 <b>{label}</b>\n📌 <b>{title}</b>\n\n{summary}"
                    if source:
                        msg += f"\n\n📰 {source}\n🔗 {link}"
                else:
                    msg = f"📰 <b>{label}</b>\n📌 <b>{title}</b>"
                    if source:
                        msg += f"\n📰 {source}\n🔗 {link}"
                if not summary and "news.google.com" in link:
                    continue
                tg_send(msg)
                mark(state, key)
        except Exception as e:
            print(f"Google News error ({label}): {e}")

def get_market_state():
    """שואל את Yahoo Finance — מחזיר state, open_ts, close_ts"""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        meta = r.json()["chart"]["result"][0]["meta"]
        market_state = meta.get("marketState", "")
        open_ts  = meta.get("regularMarketTime", 0)
        # זמן סגירה אמיתי מ-Yahoo — עובד גם בימים קצרים
        close_ts = meta.get("currentTradingPeriod", {}).get("regular", {}).get("end", 0)
        return market_state, open_ts, close_ts
    except:
        return "", 0, 0

def check_opening_bell(state):
    """פתיחת מסחר — מזהה אוטומטית לפי Yahoo Finance"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"open:{now.strftime('%Y-%m-%d')}"
    if now.weekday() >= 5 or sent(state, key):
        return

    _, open_ts, close_ts = get_market_state()

    # בדוק שאנחנו בתוך 45 דקות מהפתיחה (13:30 UTC = 810 או 14:30 UTC = 870)
    minutes_utc = now.hour * 60 + now.minute
    is_open_window = (810 <= minutes_utc <= 855) or (870 <= minutes_utc <= 915)
    if not is_open_window:
        return

    # שמור זמן פתיחה וסגירה ב-state
    state["today_open_ts"] = int(now.timestamp())
    if close_ts:
        state["today_close_ts"] = close_ts

    # שעון ישראל אוטומטי
    # שעון קיץ ישראל: אחרון של מרץ עד אחרון של אוקטובר
    from datetime import date
    def last_sunday(year, month):
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, last_day)
        return d - timedelta(days=d.weekday() + 1) if d.weekday() != 6 else d
    dst_start = last_sunday(now.year, 3)
    dst_end = last_sunday(now.year, 10)
    now_date = now.date() if hasattr(now, 'date') else date(now.year, now.month, now.day)
    israel_offset = 3 if dst_start <= now_date <= dst_end else 2
    israel_dt = now + timedelta(hours=israel_offset)
    israel_time = israel_dt.strftime("%H:%M")

    fg_score, fg_label = get_fear_greed()
    fg_line = f"\n😨 <b>Fear & Greed:</b> {fg_score} — {fg_label}" if fg_score else ""
    lines = [f"🔔 <b>פתיחת מסחר — וול סטריט 🇺🇸 ({israel_time} 🇮🇱)</b>{fg_line}\n"]

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

    # סחורות ומתכות
    lines.append("\n🛢️ <b>סחורות ומתכות</b>")
    for symbol, label, decimals in [("GC=F","🥇 זהב",0),("SI=F","🥈 כסף",2),("CL=F","🛢️ נפט",2)]:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: ${price:.{decimals}f} ({change:+.2f}%)")

    # קריפטו
    lines.append("\n₿ <b>קריפטו</b>")
    for symbol, label in [("BTC-USD","₿ ביטקוין"),("ETH-USD","Ξ אתריום")]:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: ${price:,.0f} ({change:+.2f}%)")


    # מט"ח
    lines.append("\n💱 <b>שערי חליפין</b>")
    for symbol, label in [("USDILS=X","💵 דולר-שקל"),("EURILS=X","💶 יורו-שקל"),("EURUSD=X","💶 יורו-דולר")]:
        price, change = get_commodity(symbol)
        if price:
            arrow = "🟢" if change >= 0 else "🔴"
            lines.append(f"{arrow} {label}: ₪{price:.3f} ({change:+.2f}%)")

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
    """סיכום יומי — מחשב סגירה מזמן הסגירה האמיתי של Yahoo (כולל ימים קצרים)"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    key = f"summary:{now.strftime('%Y-%m-%d')}"
    if now.weekday() >= 5 or sent(state, key):
        return

    market_state, _, close_ts = get_market_state()
    if market_state == "REGULAR":
        return

    # קח זמן סגירה — קודם מה-state (נשמר בפתיחה), אחרת מ-Yahoo ישירות
    saved_close = state.get("today_close_ts", 0)
    effective_close = saved_close if saved_close else close_ts
    if not effective_close:
        return

    close_dt = datetime.utcfromtimestamp(effective_close)
    minutes_since_close = (now - close_dt).total_seconds() / 60
    if not (0 <= minutes_since_close <= 30):
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


# ── Fear & Greed ──────────────────────────────────────────

def get_fear_greed():
    """Fear & Greed Index מ-CNN"""
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8
        )
        data = r.json()
        score = round(data["fear_and_greed"]["score"])
        rating = data["fear_and_greed"]["rating"]
        translations = {
            "Extreme Fear": "פחד קיצוני 😱",
            "Fear": "פחד 😰",
            "Neutral": "ניטרלי 😐",
            "Greed": "חמדנות 😏",
            "Extreme Greed": "חמדנות קיצונית 🤑"
        }
        label = translations.get(rating, rating)
        return score, label
    except:
        return None, None

def get_vix():
    """VIX מ-Yahoo Finance — אחוז מסגירה של יום המסחר הקודם"""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        data = r.json()["chart"]["result"][0]
        meta = data["meta"]
        price = meta.get("regularMarketPrice", 0)
        # קח סגירה של יום המסחר הקודם מהנרות
        closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        prev = closes[-2] if len(closes) >= 2 else (closes[-1] if closes else meta.get("regularMarketPreviousClose", 0))
        change = ((price - prev) / prev * 100) if prev else 0
        return round(price, 2), round(change, 2)
    except:
        return None, None

def check_vix_alert(state):
    """התראה כשVIX עובר רמות מפתח"""
    vix, change = get_vix()
    if not vix:
        return

    level = None
    if vix >= 30:
        level = "🚨 VIX מעל 30 — פאניקה בשוק!"
    elif vix >= 25:
        level = "⚠️ VIX מעל 25 — חרדה גבוהה בשוק"
    elif vix >= 20:
        level = "⚡ VIX עבר 20 — תנודתיות עולה"

    if not level:
        return

    key = f"vix:{int(vix // 5) * 5}:{datetime.now().strftime('%Y-%m-%d')}"
    if sent(state, key):
        return

    arrow = "🟢" if change <= 0 else "🔴"
    tg_send(
        f"📊 <b>התראת VIX</b>\n"
        f"{level}\n"
        f"{arrow} VIX: {vix} ({change:+.2f}% היום)"
    )
    mark(state, key)

# ── main ─────────────────────────────────────────────────

def cleanup_old_keys(state):
    """מנקה keys ישנים מיום קודם"""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday_keys = ["open:", "summary:", "weekly:"]
    state["sent"] = [
        k for k in state.get("sent", [])
        if not any(k.startswith(p) and today not in k for p in yesterday_keys)
    ]
    # נקה open/close ts אם הם מיום קודם
    if state.get("today_open_ts", 0):
        from datetime import datetime
        ts_date = datetime.utcfromtimestamp(state["today_open_ts"]).strftime("%Y-%m-%d")
        if ts_date != today:
            state.pop("today_open_ts", None)
            state.pop("today_close_ts", None)


def check_weekly_calendar(state):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if now.weekday() != 6 or not (420 <= now.hour * 60 + now.minute <= 480):
        return
    key = "weekly_calendar:" + now.strftime("%Y-%m-%d")
    if sent(state, key):
        return
    FMP_KEY = os.environ.get("FMP_API_KEY", "")
    if not FMP_KEY:
        return
    today = now.strftime("%Y-%m-%d")
    friday = (now + timedelta(days=5)).strftime("%Y-%m-%d")
    try:
        url = "https://financialmodelingprep.com/api/v3/economic_calendar?from=" + today + "&to=" + friday + "&apikey=" + FMP_KEY
        data = json.loads(fetch_url(url, timeout=10) or "[]")
    except:
        return
    HIGH_EVENTS = ["cpi","pce","nonfarm","unemployment","gdp","fomc","fed","interest rate","retail sales","ppi","ism","jolts","payroll"]
    events = []
    for e in data:
        name = e.get("event","").lower()
        impact = e.get("impact","").lower()
        if e.get("country","") != "US":
            continue
        if impact not in ["high","medium"] and not any(k in name for k in HIGH_EVENTS):
            continue
        date_str = e.get("date","")[:10]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            days = ["שני","שלישי","רביעי","חמישי","שישי","שבת","ראשון"]
            date_fmt = days[dt.weekday()] + " " + dt.strftime("%d.%m")
        except:
            date_fmt = date_str
        emoji = "🔴" if impact == "high" else "🟡"
        events.append((date_str, emoji + " " + date_fmt + " - " + e.get("event","")))
    if not events:
        return
    events.sort(key=lambda x: x[0])
    week_end = (now + timedelta(days=5)).strftime("%d.%m")
    week_start = now.strftime("%d.%m")
    msg = "📅 <b>לוח אירועים שבועי - " + week_start + " עד " + week_end + "</b>\n\n"
    msg += "\n".join(line for _, line in events)
    msg += "\n\n🔴 השפעה גבוהה | 🟡 השפעה בינונית"
    tg_send(msg)
    mark(state, key)

# ===== MAIN =====
if __name__ == "__main__":
    state = load_state()
    cleanup_old_keys(state)
    check_opening_bell(state)
    check_news(state)
    check_sharp_moves(state)
    check_daily_summary(state)
    check_weekly_summary(state)
    check_weekly_calendar(state)
    save_state(state)
