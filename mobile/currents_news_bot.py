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

TOPIC_CATEGORIES = [
    {"name": "elon", "q": "Elon Musk SpaceX OR Tesla OR xAI OR Starlink", "gl": "us"},
    {"name": "chips", "q": "Nvidia chip price OR GPU supply OR TSMC semiconductor", "gl": "us"},
    {"name": "india", "q": "India news OR India tech economy OR startup Bengaluru", "gl": "in"},
    {"name": "international", "q": "international world news OR global summit diplomacy", "gl": "us"},
    {"name": "ai", "q": "artificial intelligence OR frontier AI model OR LLM release", "gl": "us"},
    {"name": "bigtech", "q": "Apple OR Google OR Microsoft OR Meta Big Tech", "gl": "us"},
    {"name": "startups", "q": "startup funding round OR venture capital acquisition", "gl": "us"},
    {"name": "cyber", "q": "cybersecurity infrastructure OR open source Linux security", "gl": "us"}
]

HEADER_PREFIXES = [
    "JUST IN :",
    "Breaking:",
    "Just announced:",
    "Report:",
    "Update:"
]

ANALYSIS_HEADERS = [
    "Why this matters:",
    "Key win:",
    "What this means:",
    "Context:"
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

    def fetch_news_for_category(self, cat):
        params = {
            "engine": "google_news",
            "q": cat["q"],
            "gl": cat.get("gl", "us"),
            "hl": "en",
            "api_key": SERPAPI_KEY
        }
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Currents-Wire/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("news_results", [])

    def fetch_high_res_image(self, title, source):
        try:
            clean_words = [w for w in title.replace(":", " ").replace("-", " ").split() if len(w) > 3][:6]
            query = " ".join(clean_words)
            params = {
                "engine": "google_images",
                "q": query,
                "api_key": SERPAPI_KEY
            }
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("images_results", [])
                if results and len(results) > 0:
                    for img in results[:3]:
                        candidate = img.get("original") or img.get("thumbnail")
                        if candidate and candidate.startswith("http") and "favicon" not in candidate:
                            return candidate
        except Exception:
            pass
        return ""

    def generate_news_body(self, title, source, category_name):
        prefix = random.choice(HEADER_PREFIXES)
        analysis_hdr = random.choice(ANALYSIS_HEADERS)
        clean_title = title.split(" - ")[0].split(" | ")[0].strip()

        if category_name == "chips":
            bullets = [
                "- Semiconductor supply chain adjustments affecting enterprise wafer orders",
                "- High-performance compute pricing reflecting shifting fabrication capacity",
                "- Next-generation hardware allocations prioritized for AI infrastructure"
            ]
            analysis = "Global hardware economics continue to hinge on silicon packaging yields and enterprise demand."
        elif category_name == "elon":
            bullets = [
                "- Cross-industry operations spanning satellite bandwidth, autonomous transport, and compute",
                "- Direct challenge to legacy market players as commercial deployment scales",
                "- Regulatory filing updates indicate accelerating operational rollout"
            ]
            analysis = "Rapid cross-sector moves continue shifting market valuations across telecommunications and robotics."
        elif category_name == "india":
            bullets = [
                "- Key domestic market developments accelerating enterprise and consumer adoption",
                "- Foreign direct investment and engineering talent driving local technological expansion",
                "- Strategic regulatory alignment supporting scalable digital infrastructure"
            ]
            analysis = "India's technological ecosystem is solidifying its position as a primary global driver of hardware and software expansion."
        elif category_name == "international":
            bullets = [
                "- Multilateral policy shifts impacting international technology trade and governance",
                "- Cross-border agreements redefining global infrastructure standards",
                "- Geopolitical developments influencing supply chains and commercial sovereignty"
            ]
            analysis = "Global tech diplomacy is increasingly dictating operational security and software market reach."
        elif category_name == "ai":
            bullets = [
                "- Model architecture updates improving efficiency and benchmark performance",
                "- Accelerated adoption across production workflows and developer ecosystems",
                "- Frontier capabilities challenging existing software paradigms"
            ]
            analysis = "The transition from theoretical benchmarks to reliable developer tooling is compressing product cycles worldwide."
        elif category_name == "bigtech":
            bullets = [
                "- Major platform shifts impacting developer integrations and ecosystem revenues",
                "- Strategic reallocation of capital toward next-generation hardware and software",
                "- Compliance and competitive responses reshaping industry dominance"
            ]
            analysis = "Platform incumbents are adjusting core strategies to protect distribution moats against agile contenders."
        else:
            bullets = [
                "- Key structural update impacting commercial ecosystem dynamics",
                "- Engineering execution moving from roadmap planning to live deployment",
                "- Industry participants responding to shifts in capital and technology distribution"
            ]
            analysis = "Execution speed remains the primary differentiator as market participants react to the new development."

        lines = [
            f"{prefix} {clean_title}.",
            "",
            "\n".join(bullets),
            "",
            f"{analysis_hdr}",
            f"{analysis}",
            "",
            f"Source: {source}"
        ]
        return "\n".join(lines)

    def publish_post(self, text, media_url="", source_url="", publisher=""):
        token = self.get_valid_token()
        url = f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT_ID}/databases/(default)/documents/posts"
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "fields": {
                "author": {"stringValue": CURRENTS_EMAIL},
                "authorName": {"stringValue": "Currents"},
                "text": {"stringValue": text},
                "mediaUrl": {"stringValue": media_url},
                "mediaType": {"stringValue": "image"},
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
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Currents scraper cycle initiated...")
        self.login()

        shuffled_categories = list(TOPIC_CATEGORIES)
        random.shuffle(shuffled_categories)

        posted_count = 0
        for cat in shuffled_categories:
            print(f"Scanning topic category: {cat['name']}...")
            try:
                articles = self.fetch_news_for_category(cat)
            except Exception as e:
                print(f"Category fetch warning ({cat['name']}): {e}", file=sys.stderr)
                continue

            for item in articles:
                link = item.get("link")
                title = item.get("title")
                source = item.get("source", {}).get("name", "News Wire")
                if not link or not title:
                    continue
                if self.is_posted(link):
                    continue

                image_url = item.get("thumbnail") or ""
                if not image_url or "gstatic.com" in image_url:
                    image_url = self.fetch_high_res_image(title, source) or image_url

                if not image_url or not image_url.startswith("http"):
                    continue

                post_text = self.generate_news_body(title, source, cat["name"])
                post_id = self.publish_post(post_text, image_url, link, source)
                self.mark_posted(link, title, source, post_id)
                print(f"Published [{post_id}] in [{cat['name']}] with image: {image_url[:60]}...")
                print(f"Title: {title[:70]}")
                posted_count += 1
                return posted_count

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
