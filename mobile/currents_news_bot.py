import os
import sys
import json
import time
import sqlite3
import random
import urllib.request
import urllib.parse
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "44bccfe9e25bf03a19e0a5a1be36335bdf596ba87fc363a1c9dd1a91966618f2")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyAD0NdeeIAZhOU2qrGYzZWXLUkIsw2j5vA")
FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "ntaf-754e1")
CURRENTS_EMAIL = os.environ.get("CURRENTS_EMAIL", "currents@nta.com")
CURRENTS_PASS = os.environ.get("CURRENTS_PASS", "6663629")

DB_DIR = os.environ.get("HOME", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "currents_news.db")

TOPIC_CATEGORIES = [
    {
        "name": "wire_services",
        "q": "breaking OR policy OR economy (Reuters OR \"Associated Press\" OR AFP OR Bloomberg)",
        "gl": "us",
        "category_label": "Wire Service"
    },
    {
        "name": "newspapers",
        "q": "investigation OR interview OR politics (NYT OR \"Washington Post\" OR \"Wall Street Journal\" OR Guardian OR \"Financial Times\")",
        "gl": "us",
        "category_label": "Newspaper"
    },
    {
        "name": "broadcast_media",
        "q": "breaking news OR interview (BBC OR CNN OR CNBC OR \"Sky News\")",
        "gl": "us",
        "category_label": "Broadcast Media"
    },
    {
        "name": "technology_publications",
        "q": "artificial intelligence OR chip OR software (TechCrunch OR \"The Verge\" OR ArsTechnica OR Wired OR \"MIT Technology Review\")",
        "gl": "us",
        "category_label": "Technology Publication"
    },
    {
        "name": "business_financial_media",
        "q": "markets OR earnings OR merger OR acquisition (Bloomberg OR Forbes OR Fortune OR Barron's OR MarketWatch)",
        "gl": "us",
        "category_label": "Business & Financial Media"
    },
    {
        "name": "official_company_sources",
        "q": "announces OR \"press release\" OR launch (OpenAI OR Microsoft OR Google OR Apple OR Nvidia OR Tesla OR SpaceX)",
        "gl": "us",
        "category_label": "Official Company Source"
    },
    {
        "name": "government_sources",
        "q": "regulation OR policy OR statement (gov OR \"White House\" OR NASA OR EPA OR SEC OR FTC OR \"Ministry of External Affairs\")",
        "gl": "us",
        "category_label": "Government Source"
    },
    {
        "name": "regulatory_court_filings",
        "q": "lawsuit OR antitrust OR ruling OR \"court filing\" OR SEC (antitrust OR supreme court OR federal court)",
        "gl": "us",
        "category_label": "Regulatory & Legal Filing"
    },
    {
        "name": "academic_scientific_sources",
        "q": "research OR discovery OR study (Nature OR Science OR \"arXiv\" OR PLOS OR Cell)",
        "gl": "us",
        "category_label": "Academic & Scientific Source"
    },
    {
        "name": "industry_specialist_publications",
        "q": "semiconductor OR aerospace OR energy (EE Times OR AnandTech OR AviationWeek OR SpaceNews OR Electrek)",
        "gl": "us",
        "category_label": "Specialist Publication"
    },
    {
        "name": "local_regional_publications",
        "q": "India development OR parliament OR elections (\"The Hindu\" OR \"Hindustan Times\" OR \"Indian Express\" OR \"Times of India\" OR NDTV)",
        "gl": "in",
        "category_label": "Regional Publication"
    },
    {
        "name": "public_databases_statistical_sources",
        "q": "statistics OR economic forecast OR census (World Bank OR IMF OR OECD OR \"Federal Reserve\" OR RBI)",
        "gl": "us",
        "category_label": "Statistical Database"
    },
    {
        "name": "elon_starlink_india",
        "q": "Elon Musk Starlink India Ambani spectrum telecom (Reuters OR Bloomberg OR \"The Hindu\" OR \"Economic Times\")",
        "gl": "in",
        "category_label": "Wire Service & Regional Report"
    }
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
    if path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".png") or path.endswith(".webp"):
        return True
    if "googleusercontent.com" in url or "wikimedia.org" in url or "twimg.com" in url or "fbcdn.net" in url or "cloudfront.net" in url:
        return True
    return False

def mirror_image_to_nta(image_url):
    for _ in range(2):
        try:
            req = urllib.request.Request(
                image_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
                if not data or len(data) < 200:
                    continue

                clean_p = image_url.split("?")[0].lower()
                ext = "png" if (clean_p.endswith(".png") or data.startswith(b'\x89PNG')) else "jpg"
                mime = "image/png" if ext == "png" else "image/jpeg"
                unique_name = f"{int(time.time())}_{random.randint(1000, 9999)}_currents.{ext}"
                put_url = f"https://ntamediaserver.pages.dev/v1/storage/objects/media/{unique_name}?project_id=netuark_media"

                put_req = urllib.request.Request(
                    put_url,
                    data=data,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Content-Type": mime,
                        "X-Project-Id": "netuark_media"
                    },
                    method="PUT"
                )
                with urllib.request.urlopen(put_req, timeout=15) as put_resp:
                    if put_resp.status in [200, 201]:
                        return f"https://ntamediaserver.pages.dev/v1/storage/objects/media/{unique_name}"
        except Exception:
            time.sleep(1)
    return ""

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
        for attempt in range(6):
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
                payload = json.dumps({
                    "email": CURRENTS_EMAIL,
                    "password": CURRENTS_PASS,
                    "returnSecureToken": True
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.id_token = data.get("idToken")
                    self.refresh_token = data.get("refreshToken")
                    self.token_expiry = time.time() + int(data.get("expiresIn", 3600)) - 120
                    return self.id_token
            except Exception:
                time.sleep(min(30, 2 ** attempt))
        return None

    def get_valid_token(self):
        if not self.id_token or time.time() >= self.token_expiry:
            return self.login()
        return self.id_token

    def fetch_news_rss(self, query):
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            channel = root.find("channel")
            if channel is None:
                return []
            items = []
            for item in channel.findall("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                source_el = item.find("source")
                if title_el is not None and link_el is not None:
                    title_text = title_el.text or ""
                    link_text = link_el.text or ""
                    source_text = source_el.text if source_el is not None and source_el.text else "Google News Wire"
                    items.append({
                        "title": title_text,
                        "link": link_text,
                        "source": source_text,
                        "thumbnail": ""
                    })
            return items
        except Exception as e:
            print(f"RSS fallback notice: {e}", file=sys.stderr)
            return []

    def fetch_news_for_category(self, cat):
        try:
            params = {
                "engine": "google_news",
                "q": cat["q"],
                "gl": cat.get("gl", "us"),
                "hl": "en",
                "api_key": SERPAPI_KEY
            }
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "Currents-Wire/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("news_results", [])
                if results:
                    return results
        except Exception:
            pass

        return self.fetch_news_rss(cat["q"])

    def fetch_serp_image(self, query_text):
        try:
            params = {
                "engine": "google_images",
                "q": query_text,
                "api_key": SERPAPI_KEY
            }
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
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

    def fetch_article_og_image(self, link):
        try:
            req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                m = re.search(r"""<meta\s+property=["\x27]og:image["\x27]\s+content=["\x27]([^"\x27]+)["\x27]""", html, re.I)
                if not m:
                    m = re.search(r"""<meta\s+content=["\x27]([^"\x27]+)["\x27]\s+property=["\x27]og:image["\x27]""", html, re.I)
                if m:
                    candidate = m.group(1).strip()
                    if is_valid_jpg_or_png(candidate):
                        return candidate
        except Exception:
            pass
        return ""

    def fetch_wikipedia_image(self, query_text):
        try:
            clean_term = query_text.replace("\"", "").replace("'", "").strip()
            url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(clean_term)}&prop=pageimages&format=json&pithumbsize=800"
            req = urllib.request.Request(url, headers={"User-Agent": "CurrentsNewsBot/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for _, page_info in pages.items():
                    thumb = page_info.get("thumbnail", {}).get("source")
                    if thumb and is_valid_jpg_or_png(thumb):
                        return thumb
        except Exception:
            pass
        return ""

    def get_guaranteed_image(self, title, source, item_thumb, article_link=""):
        if is_valid_jpg_or_png(item_thumb):
            return item_thumb

        if article_link:
            og_img = self.fetch_article_og_image(article_link)
            if og_img:
                return og_img

        clean_words = [w for w in title.replace(":", " ").replace("-", " ").replace("'", "").split() if len(w) > 3][:6]
        q1 = " ".join(clean_words)
        img1 = self.fetch_serp_image(q1)
        if img1:
            return img1

        if source:
            wiki_source_img = self.fetch_wikipedia_image(source)
            if wiki_source_img:
                return wiki_source_img

        if clean_words:
            wiki_topic_img = self.fetch_wikipedia_image(clean_words[0])
            if wiki_topic_img:
                return wiki_topic_img

        return ""

    def generate_news_body(self, title, source, link, category_name):
        prefix = random.choice(HEADER_PREFIXES)
        analysis_hdr = random.choice(ANALYSIS_HEADERS)
        clean_title = title.split(" - ")[0].split(" | ")[0].strip()

        if category_name == "wire_services":
            bullets = [
                "- Rapid fast-breaking factual developments verified across news wires",
                "- High-frequency global coverage tracking executive and regulatory actions",
                "- Structured independent verification establishing primary event timeline"
            ]
            analysis = "Real-time wire reporting establishes the factual foundation for cross-market event tracking and government decision cycles."
        elif category_name == "newspapers":
            bullets = [
                "- Deep investigative reporting uncovering long-term public interest context",
                "- Key stakeholder interviews examining administrative and civic ramifications",
                "- Rigorous editorial verification evaluating complex institutional narratives"
            ]
            analysis = "Independent investigative journalism provides vital accountability and deep civic context beyond rapid headline cycles."
        elif category_name == "broadcast_media":
            bullets = [
                "- Live breaking event updates tracking fast-moving physical and economic developments",
                "- Direct broadcast statements and on-the-record executive interviews",
                "- Visual and audio field reporting confirming ground-truth realities"
            ]
            analysis = "Broadcast reporting delivers immediate eyewitness verification and high-speed updates during rapidly unfolding scenarios."
        elif category_name == "technology_publications":
            bullets = [
                "- Architecture updates and technical teardowns across compute, AI, and developer tools",
                "- Deep technical scrutiny separating marketing claims from engineering reality",
                "- Developer ecosystem adoption metrics tracking real-world implementation"
            ]
            analysis = "Specialist technology journalism surfaces architectural trade-offs and developer adoption dynamics that general outlets miss."
        elif category_name == "business_financial_media":
            bullets = [
                "- Capital allocation shifts, earnings performance, and valuation benchmarks",
                "- Market liquidity reactions and enterprise capital expenditure forecasts",
                "- M&A consolidation and strategic restructuring reshaping competitive moats"
            ]
            analysis = "Financial media analysis connects capital formation, market pricing, and balance sheet resilience to long-term industry structure."
        elif category_name == "official_company_sources":
            bullets = [
                "- Direct primary disclosures from engineering blogs, product releases, and IR filings",
                "- Official statements establishing formal corporate positions and commitments",
                "- Technical documentation and roadmap releases defining product capabilities"
            ]
            analysis = "Primary corporate statements document official capability milestones and product roadmaps directly from source engineering teams."
        elif category_name == "government_sources":
            bullets = [
                "- Formal administrative rulings, statutory updates, and public policy declarations",
                "- Official regulatory directives impacting economic and technological sovereignty",
                "- Public interest mandates and institutional governance standards enacted"
            ]
            analysis = "Government regulatory announcements define the legal boundaries, compliance regimes, and economic frameworks for domestic and cross-border operations."
        elif category_name == "regulatory_court_filings":
            bullets = [
                "- Primary legal petitions, antitrust briefs, and binding judicial opinions",
                "- Securities and exchange regulatory disclosures detailing risk factors",
                "- Enforceable precedent and contractual obligations established in court records"
            ]
            analysis = "Court filings and regulatory dockets provide unvarnished legal facts, establishing precise evidentiary records beyond secondary media summaries."
        elif category_name == "academic_scientific_sources":
            bullets = [
                "- Peer-reviewed methodologies and reproducible empirical laboratory results",
                "- Preprint benchmark releases pushing algorithmic and material frontiers",
                "- Formal scientific consensus examining validity, error margins, and rigor"
            ]
            analysis = "Peer-reviewed scientific research grounds technological and medical advances in rigorous empirical verification and reproducible evidence."
        elif category_name == "industry_specialist_publications":
            bullets = [
                "- Highly focused technical coverage of supply chains, yields, and fabrication nodes",
                "- Specialized domain analysis of aerospace, energy, and semiconductor telemetry",
                "- Deep industry-specific nomenclature clarifying operational constraints"
            ]
            analysis = "Specialist domain coverage captures intricate packaging yields, supply-chain bottlenecks, and industrial tradecraft that define execution reality."
        elif category_name == "local_regional_publications":
            bullets = [
                "- State-level policy execution, infrastructure progress, and regional economics",
                "- Ground-level community developments and domestic parliamentary dynamics",
                "- Sub-national governance impacts often omitted by international media"
            ]
            analysis = "Regional reporting delivers crucial granularity on infrastructure deployment, local policy adoption, and community impact."
        elif category_name == "public_databases_statistical_sources":
            bullets = [
                "- Macroeconomic benchmarks, census metrics, and central bank statistical releases",
                "- Quantitative dataset tracking validating numerical claims across industries",
                "- Longitudinal economic indicators measuring inflation, trade, and productivity"
            ]
            analysis = "Statistical databases and public repositories anchor news narratives to verifiable empirical data rather than speculative reporting."
        elif category_name == "elon_starlink_india":
            bullets = [
                "- Satellite spectrum allocation and regulatory licensing moving toward resolution",
                "- Cross-industry competition between orbital constellation providers and domestic telecom giants",
                "- Sovereignty, data security, and regional satellite broadband connectivity milestones"
            ]
            analysis = "The collision between orbital satellite networks and established telecom infrastructure represents a pivotal test for national spectrum policy and digital connectivity."
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
            f"Source: {source}",
            f"Link: {link}"
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
        token = self.login()
        if not token:
            print("Currents login deferred: Network or authentication temporarily unreachable", file=sys.stderr)
            return 0

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
                raw_source = item.get("source")
                if isinstance(raw_source, dict):
                    source = raw_source.get("name", "News Wire")
                elif isinstance(raw_source, str) and raw_source:
                    source = raw_source
                else:
                    source = "News Wire"
                if not link or not title:
                    continue
                if self.is_posted(link):
                    continue

                item_thumb = item.get("thumbnail") or ""
                raw_image_url = self.get_guaranteed_image(title, source, item_thumb, article_link=link)

                if not is_valid_jpg_or_png(raw_image_url):
                    continue

                final_image_url = mirror_image_to_nta(raw_image_url)
                if not final_image_url or not final_image_url.startswith("https://ntamediaserver.pages.dev/"):
                    continue

                post_text = self.generate_news_body(title, source, link, cat["name"])
                post_id = self.publish_post(post_text, final_image_url, link, source)
                if not post_id:
                    continue
                self.mark_posted(link, title, source, post_id)
                print(f"Published [{post_id}] in [{cat['name']}]:")
                print(f"Image: {final_image_url}")
                print(f"Link: {link}")
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
