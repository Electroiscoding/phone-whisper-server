import os
import sys
import json
import time
import sqlite3
import random
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "44bccfe9e25bf03a19e0a5a1be36335bdf596ba87fc363a1c9dd1a91966618f2")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyAD0NdeeIAZhOU2qrGYzZWXLUkIsw2j5vA")
FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "ntaf-754e1")
CURRENTS_EMAIL = os.environ.get("CURRENTS_EMAIL", "currents@nta.com")
CURRENTS_PASS = os.environ.get("CURRENTS_PASS", "6663629")

DB_DIR = os.environ.get("HOME", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "currents_news.db")

TECH_QUERIES = [
    "artificial intelligence breakthrough OR LLM OR OpenAI OR Claude Anthropic",
    "Nvidia GPU chips semiconductor quantum computing",
    "software engineering cybersecurity open source Linux",
    "robotics autonomous tech humanoid robotics",
    "Silicon Valley tech startup developer tools",
    "space tech aerospace satellite internet SpaceX",
    "next gen smartphones hardware wearable computing"
]

HOOK_TEMPLATES = [
    ("⚡ Hold up, this is massive for tech:", "What's wild here is how fast this moved from lab theory to production.", "If this trajectory holds, the whole stack changes by next year. Thoughts?"),
    ("🧠 We need to talk about what just happened in tech:", "Here's the part the headlines are totally skipping over:", "Are we actually ready for this, or are we just pretending we are?"),
    ("🔥 This just dropped and the timeline is sleeping on it:", "The raw implications here are wild for builders:", "Watch how fast competitors copy this in the next 60 days."),
    ("👀 Major signal cutting through the noise today:", "The real unlock isn't just the announcement—it's what comes next:", "Is this a genuine game-changer or just peak tech hype?"),
    ("🚀 Tech moves stupidly fast. Case in point:", "Break down the mechanics and it becomes obvious why this matters:", "Curious what the builders on NeTuArk think about this play.")
]

class CurrentsNewsBot:
    def __init__(self):
        self._init_db()
        self.id_token = None
        self.refresh_token = None
        self.token_expiry = 0

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posted_articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                post_id TEXT,
                posted_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def is_posted(self, url):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM posted_articles WHERE url = ?", (url,))
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def mark_posted(self, url, title, source, post_id):
        conn = sqlite3.connect(DB_PATH)
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO posted_articles (url, title, source, post_id, posted_at) VALUES (?, ?, ?, ?, ?)", (url, title, source, post_id, now_iso))
        conn.commit()
        conn.close()

    def login(self):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
        payload = json.dumps({
            "email": CURRENTS_EMAIL,
            "password": CURRENTS_PASS,
            "returnSecureToken": True
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.id_token = data.get("idToken")
            self.refresh_token = data.get("refreshToken")
            self.token_expiry = time.time() + int(data.get("expiresIn", 3600)) - 120
            return self.id_token

    def get_valid_token(self):
        if not self.id_token or time.time() >= self.token_expiry:
            return self.login()
        return self.id_token

    def fetch_trending_news(self):
        query = random.choice(TECH_QUERIES)
        params = {
            "engine": "google_news",
            "q": query,
            "gl": "us",
            "hl": "en",
            "api_key": SERPAPI_KEY
        }
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Currents-Scraper/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("news_results", [])

    def fetch_high_res_image(self, title, source):
        try:
            clean_title = title.split(" - ")[0].split(" | ")[0]
            query = f"{clean_title} {source}"
            params = {
                "engine": "google_images",
                "q": query,
                "api_key": SERPAPI_KEY,
                "ijn": "0"
            }
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "Currents-Image-Scraper/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("images_results", [])
                if results and len(results) > 0:
                    first = results[0]
                    return first.get("original") or first.get("thumbnail") or ""
        except Exception:
            pass
        return ""

    def generate_hooked_post(self, title, source, link):
        clean_title = title.split(" - ")[0].split(" | ")[0].strip()
        intro, bridge, outro = random.choice(HOOK_TEMPLATES)
        post_lines = [
            f"{intro}",
            f"",
            f"📰 {clean_title}",
            f"",
            f"{bridge} ({source})",
            f"",
            f"{outro}",
            f"",
            f"🔗 Read full: {link}"
        ]
        return "\n".join(post_lines)

    def publish_post(self, text, media_url="", source_url="", publisher=""):
        token = self.get_valid_token()
        url = f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT_ID}/databases/(default)/documents/posts"
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "fields": {
                "author": {"stringValue": CURRENTS_EMAIL},
                "authorName": {"stringValue": "Currents"},
                "text": {"stringValue": text},
                "mediaUrl": {"stringValue": media_url or ""},
                "mediaType": {"stringValue": "image" if media_url else ""},
                "type": {"stringValue": "post"},
                "likes": {"arrayValue": {"values": []}},
                "reposts": {"arrayValue": {"values": []}},
                "commentCount": {"integerValue": "0"},
                "viewsCount": {"integerValue": "0"},
                "timestamp": {"timestampValue": now_iso},
                "sourceUrl": {"stringValue": source_url or ""},
                "sourcePublisher": {"stringValue": publisher or ""}
            }
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            doc_name = data.get("name", "")
            return doc_name.split("/")[-1]

    def run_cycle(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking latest tech news...")
        self.login()
        articles = self.fetch_trending_news()
        print(f"Found {len(articles)} news items from SerpApi.")
        posted_count = 0
        for item in articles:
            link = item.get("link")
            title = item.get("title")
            source = item.get("source", {}).get("name", "Tech Wire")
            if not link or not title:
                continue
            if self.is_posted(link):
                continue

            thumbnail = item.get("thumbnail") or ""
            if not thumbnail or "gstatic.com" in thumbnail:
                high_res = self.fetch_high_res_image(title, source)
                if high_res:
                    thumbnail = high_res

            post_text = self.generate_hooked_post(title, source, link)
            post_id = self.publish_post(post_text, thumbnail, link, source)
            self.mark_posted(link, title, source, post_id)
            print(f"Successfully published post [{post_id}]: {title[:60]}...")
            posted_count += 1
            break
        return posted_count

    def loop(self, interval_seconds=1800):
        print(f"Starting Currents 24/7 autonomous loop (Interval: {interval_seconds}s)...")
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"Cycle notice: {e}", file=sys.stderr)
            time.sleep(interval_seconds)

if __name__ == "__main__":
    bot = CurrentsNewsBot()
    if "--run-once" in sys.argv:
        bot.run_cycle()
    else:
        interval = 1800
        for arg in sys.argv[1:]:
            if arg.isdigit():
                interval = int(arg)
        bot.loop(interval)
