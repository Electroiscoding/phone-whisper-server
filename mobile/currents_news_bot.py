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
    {"name": "politics", "q": "politics elections government policy geopolitical summit", "gl": "us"},
    {"name": "india_politics", "q": "India politics elections parliament policy governance", "gl": "in"},
    {"name": "india_news", "q": "India national news tech economy development infrastructure", "gl": "in"},
    {"name": "international", "q": "world international news diplomacy global affairs", "gl": "us"},
    {"name": "elon", "q": "Elon Musk SpaceX Tesla xAI Starlink Neuralink", "gl": "us"},
    {"name": "chips", "q": "Nvidia chip price GPU supply semiconductor TSMC foundry", "gl": "us"},
    {"name": "ai", "q": "artificial intelligence frontier AI model LLM open source", "gl": "us"},
    {"name": "bigtech", "q": "Apple Google Microsoft Meta Amazon enterprise tech", "gl": "us"},
    {"name": "startups", "q": "startup funding venture capital IPO commercial growth", "gl": "us"},
    {"name": "cyber", "q": "cybersecurity infrastructure digital defense zero day", "gl": "us"}
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

def is_valid_jpg_or_png(url):
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return False
    path = url.split("?")[0].lower()
    return path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".png")

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

    def fetch_serp_image(self, query_text):
        try:
            params = {
                "engine": "google_images",
                "q": query_text,
                "api_key": SERPAPI_KEY
            }
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("images_results", [])
                for img in results:
                    orig = img.get("original") or ""
                    if is_valid_jpg_or_png(orig):
                        return orig
                for img in results:
                    thumb = img.get("thumbnail") or ""
                    if is_valid_jpg_or_png(thumb):
                        return thumb
        except Exception:
            pass
        return ""

    def get_guaranteed_image(self, title, source, item_thumb):
        if is_valid_jpg_or_png(item_thumb):
            return item_thumb

        clean_words = [w for w in title.replace(":", " ").replace("-", " ").replace("'", "").split() if len(w) > 3][:6]
        q1 = " ".join(clean_words)
        img1 = self.fetch_serp_image(q1)
        if img1:
            return img1

        q2 = f"{clean_words[0]} {clean_words[1]} {source}" if len(clean_words) >= 2 else f"{title[:25]} news"
        img2 = self.fetch_serp_image(q2)
        if img2:
            return img2

        return ""

    def generate_news_body(self, title, source, category_name):
        prefix = random.choice(HEADER_PREFIXES)
        analysis_hdr = random.choice(ANALYSIS_HEADERS)
        clean_title = title.split(" - ")[0].split(" | ")[0].strip()

        if category_name in ["politics", "india_politics"]:
            bullets = [
                "- Key policy alignments and legislative agendas moving into active execution",
                "- Political leadership and administrative bodies responding to strategic public priorities",
                "- Governance frameworks shaping upcoming regulatory and economic shifts"
            ]
            analysis = "Policy decisions and institutional alignments continue to directly influence market stability and administrative priorities."
        elif category_name in ["india_news", "india"]:
            bullets = [
                "- Rapid domestic development accelerating across regional and national sectors",
                "- Infrastructure initiatives and economic momentum bolstering long-term growth",
                "- Enterprise execution and institutional support aligning on key milestones"
            ]
            analysis = "India's domestic growth trajectory reflects accelerating investments across digital infrastructure, governance, and enterprise development."
        elif category_name == "chips":
            bullets = [
                "- Semiconductor supply chain adjustments affecting enterprise wafer allocations",
                "- High-performance compute pricing reflecting shifting fabrication capacity",
                "- Next-generation hardware allocations prioritized for large-scale infrastructure"
            ]
            analysis = "Global hardware economics continue to hinge on silicon packaging yields and enterprise demand."
        elif category_name == "elon":
            bullets = [
                "- Multi-front operations spanning satellite networks, autonomous systems, and compute",
                "- Direct disruption to traditional legacy market players as commercial scaling accelerates",
                "- Operational milestones indicate accelerating deployment across flagship ventures"
            ]
            analysis = "Aggressive execution across orbital infrastructure and autonomous compute continues to challenge incumbent legacy industries."
        elif category_name == "international":
            bullets = [
                "- Multilateral diplomatic shifts impacting cross-border trade and governance",
                "- International agreements redefining global standards and diplomatic security",
                "- Geopolitical developments influencing supply lines and economic cooperation"
            ]
            analysis = "Global diplomacy and cross-border accords are increasingly determining geopolitical stability and international market access."
        elif category_name == "ai":
            bullets = [
                "- Model architecture updates improving efficiency and benchmark performance",
                "- Accelerated adoption across production workflows and developer ecosystems",
                "- Frontier capabilities challenging existing software paradigms"
            ]
            analysis = "The transition from theoretical benchmarks to reliable tooling is compressing technological cycles worldwide."
        elif category_name == "bigtech":
            bullets = [
                "- Major platform shifts impacting developer integrations and ecosystem revenues",
                "- Strategic reallocation of capital toward next-generation hardware and software",
                "- Competitive responses reshaping industry dominance across consumer ecosystems"
            ]
            analysis = "Platform incumbents are adjusting core strategies to defend distribution moats against rapid innovations."
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

                item_thumb = item.get("thumbnail") or ""
                image_url = self.get_guaranteed_image(title, source, item_thumb)

                if not is_valid_jpg_or_png(image_url):
                    continue

                post_text = self.generate_news_body(title, source, cat["name"])
                post_id = self.publish_post(post_text, image_url, link, source)
                self.mark_posted(link, title, source, post_id)
                print(f"Published [{post_id}] in [{cat['name']}] with verified .jpg/.png image:")
                print(f"Image: {image_url}")
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
