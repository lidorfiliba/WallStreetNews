import requests, json, random, string, os
from datetime import datetime, timedelta, timezone

GIST_ID = "18407cae7b0a4a4c2f1313ab835dceb4"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
TG_BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT_ID = "-1003549323911"

def gen_code():
    p1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    p2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f'{p1}-{p2}'

def update_gist(code, expires):
    content = json.dumps({"code": code, "expires": expires}, ensure_ascii=False)
    r = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
        json={"files": {"stocklens_access.json": {"content": content}}}
    )
    return r.status_code == 200

def send_telegram(code, expires_str):
    msg = (
        f"🔐 <b>קוד גישה שבועי — StockLens</b>\n\n"
        f"🗝️ <b>קוד:</b> <code>{code}</code>\n"
        f"📅 <b>תוקף עד:</b> {expires_str}\n\n"
        f"🌐 <a href='https://lidorfiliba.github.io/StockLens/'>פתח את StockLens</a>"
    )
    r = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    )
    msg_id = r.json().get("result", {}).get("message_id")
    if msg_id:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/pinChatMessage",
            json={"chat_id": TG_CHAT_ID, "message_id": msg_id, "disable_notification": True}
        )

now = datetime.now(timezone.utc)
expires = (now + timedelta(days=7)).isoformat()
expires_str = (now + timedelta(days=7)).strftime("%d.%m.%Y")
code = gen_code()

if update_gist(code, expires):
    send_telegram(code, expires_str)
    print(f"✅ קוד חדש: {code} | תוקף: {expires_str}")
else:
    print("❌ שגיאה בעדכון Gist")
