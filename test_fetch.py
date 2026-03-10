import urllib.request, re

sites = [
    ('cnbc.com', 'https://www.cnbc.com/2026/03/10/stocks-making-the-biggest-moves-premarket-kss-casy-vrtx.html'),
    ('bloomberg.com', 'https://www.bloomberg.com/'),
    ('businessinsider.com', 'https://www.businessinsider.com/'),
    ('forbes.com', 'https://www.forbes.com/'),
    ('techcrunch.com', 'https://techcrunch.com/'),
    ('apnews.com', 'https://apnews.com/'),
    ('reuters.com', 'https://www.reuters.com/'),
]

for name, url in sites:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode('utf-8', errors='ignore')
        blocked = any(p in html.lower() for p in ['subscribe to read','sign in to read','403 forbidden','access denied','paywall','subscribe now'])
        print(f'{"🔒" if blocked else "✅"} {name}: {len(html)} תווים {"(paywall)" if blocked else ""}')
    except Exception as e:
        print(f'❌ {name}: {e}')
