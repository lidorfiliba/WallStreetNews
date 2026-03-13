import requests, xml.etree.ElementTree as ET

feeds = [
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("Reuters Markets", "https://feeds.reuters.com/reuters/marketsNews"),
    ("AP Business", "https://feeds.apnews.com/apnews/business"),
    ("AP Finance", "https://feeds.apnews.com/apnews/financialmarkets"),
    ("NPR Business", "https://feeds.npr.org/1006/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
]

BLOCKED = ["fool.com","seekingalpha.com","wsj.com","barrons.com","ft.com",
    "finance.yahoo.com","marketwatch.com","benzinga.com","bloomberg.com"]

for name, url in feeds:
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        if items:
            link = items[0].findtext("link","")
            blocked = any(d in link for d in BLOCKED)
            print(f"✅ {name}: {len(items)} items | blocked={blocked} | {link[:60]}")
        else:
            print(f"⚠️ {name}: 0 items")
    except Exception as e:
        print(f"❌ {name}: {e}")
