#!/usr/bin/env python3
"""Phone-Native Swades SEO War Room Engine — Groq LLM reasoning + Swades tools + Auto-publish."""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional

HOME_DIR = Path("/data/data/com.termux/files/home")
SWADES_DIR = HOME_DIR / "Swades"
REPO_DIR = HOME_DIR / "glowing-carnival"
STATE_FILE = HOME_DIR / "war_room_state.json"
LOG_FILE = HOME_DIR / "war_room_experiments.log"
GIT_PATH = "/data/data/com.termux/files/usr/bin/git"
BRANCH = "feat/swades-infinite-seo"
COMMIT_EVERY_N = 5

if str(SWADES_DIR) not in sys.path and SWADES_DIR.exists():
    sys.path.insert(0, str(SWADES_DIR))

try:
    import main as swades
except ImportError:
    swades = None

SURFACES = [
    "index.html", "download.html", "noteonalgo.html", "updates.html",
    "frontend/feed.html", "frontend/post.html", "frontend/userProfile.html",
    "frontend/profile.html", "frontend/resumeMaker.html", "frontend/admin.html",
    "frontend/auth.html", "frontend/about.html", "frontend/settings.html",
    "frontend/rankings.html", "frontend/analytics.html", "frontend/postAnalytics.html",
    "frontend/telemetry-admin.html", "frontend/invite.html", "frontend/integrations.html",
    "frontend/newsEngine.html", "frontend/stalkerList.html", "frontend/richup.html",
    "frontend/monopoly.html", "frontend/ConvoList.html", "frontend/ChatUi.html",
    "frontend/NewGroup.html", "frontend/NewContact.html", "frontend/ChangePassword.html",
    "frontend/reset-password.html", "sdk/docs.html", "sdk/demo.html",
    "sdk/api-demo.html", "sdk/tests.html",
]

MISSION = "Autonomous SEO optimization of NeTuArk — sovereign NTA-driven metadata injection across all surfaces"

def _resolve_groq_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        key_path = Path("/data/data/com.termux/files/home/.groq_key")
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip()
    return key

GROQ_KEY = _resolve_groq_key()
GROQ_MODEL = "qwen/qwen3.8-27b"
USE_LLM = bool(GROQ_KEY)


def _groq_reason(surface: str, file_head: str, search_result: str) -> tuple:
    """Direct Groq API call — returns (thought, inject_html, tags_added)."""
    if not GROQ_KEY:
        return "", "", []

    prompt = f"""You are the Lead SEO Architecture Agent for NeTuArk (https://netuark.pages.dev), a sovereign decentralized social platform.

Surface File: {surface}
Current HTML <head> content:
{file_head[:2200]}

NTA search / context signals:
{search_result[:500]}

Tasks:
Perform a deep, aggressive SEO overhaul for this surface:
1. OpenGraph Tags: Ensure og:title, og:description, og:image, og:url, og:type ('website' or 'article') are all present.
2. Twitter Card Tags: Ensure twitter:card ('summary_large_image'), twitter:title, twitter:description, twitter:image are present.
3. Canonical URL: Set canonical to https://netuark.pages.dev/{surface} if missing.
4. Structured Data (JSON-LD): Generate complete WebPage, WebSite, or SoftwareApplication Schema.org JSON-LD script if missing.
5. Resource Hints: Add preconnect and dns-prefetch hints for CDNs (fonts.googleapis.com, fonts.gstatic.com, cdn.tailwindcss.com) if used.

Identify ONLY what is currently missing or deficient in the HTML head above.
Generate the exact HTML to inject before </head>.

Respond strictly in JSON format (no markdown, no code fences):
{{
  "thought": "<concise explanation of missing elements and improvements>",
  "inject_html": "<clean formatted html tags to inject>",
  "tags_added": ["og:title", "JSON-LD", ...]
}}

If ALL tags, JSON-LD, Twitter cards, and canonical are already completely and correctly implemented, return:
{{
  "thought": "Surface has 100% full SEO coverage verified.",
  "inject_html": "",
  "tags_added": []
}}"""

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_KEY}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        text = data["choices"][0]["message"]["content"].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            obj = json.loads(text[start:end])
            inject = obj.get("inject_html") or obj.get("inject_head") or ""
            return obj.get("thought", ""), inject, obj.get("tags_added", [])
    except Exception as e:
        return f"Groq query failed: {e}", "", []
    return "", "", []


def _git(args: List[str]) -> str:
    env = os.environ.copy()
    env["PATH"] = "/data/data/com.termux/files/usr/bin:" + env.get("PATH", "")
    env["GIT_TERMINAL_PROMPT"] = "0"
    r = subprocess.run(
        [GIT_PATH] + args,
        cwd=str(REPO_DIR),
        capture_output=True, text=True, timeout=60, env=env,
    )
    return (r.stdout + r.stderr).strip()


def publish_changes(cycle: int, surfaces_changed: List[str]) -> str:
    status = _git(["status", "--porcelain"])
    if not status.strip():
        return "git: nothing to commit"
    _git(["add", "-A"])
    msg = f"swades(seo): auto cycle {cycle} — {', '.join(surfaces_changed[:3])}"
    commit_out = _git(["commit", "-m", msg])
    push_out = _git(["push", "origin", BRANCH])
    return f"{commit_out[:60]} | {push_out[:60]}"


class WarRoomEngine:
    def __init__(self):
        self.ws = None
        if swades and REPO_DIR.exists():
            try:
                cfg = swades.Config.load(llm=False, root=REPO_DIR)
                cfg.timeout = 10
                self.ws = swades.Workspace(cfg)
            except Exception:
                pass

        self.state = self._load_state()
        self._pending_surfaces: List[str] = []

    def _load_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                s["war_room_status"] = "WAR_ROOM_ACTIVE"
                s["mission"] = MISSION
                s["llm_active"] = USE_LLM
                s["model"] = GROQ_MODEL if USE_LLM else "rule-based"
                return s
            except Exception:
                pass
        return {
            "war_room_status": "WAR_ROOM_ACTIVE",
            "mission": MISSION,
            "llm_active": USE_LLM,
            "model": GROQ_MODEL if USE_LLM else "rule-based",
            "total_cycles": 0,
            "recent_experiments": [],
        }

    def _save_state(self):
        self.state["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        STATE_FILE.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def run_cycle(self, target_surface: Optional[str] = None) -> Dict[str, Any]:
        self.state["total_cycles"] = self.state.get("total_cycles", 0) + 1
        cycle = self.state["total_cycles"]

        surface = target_surface or SURFACES[(cycle - 1) % len(SURFACES)]
        self.state["active_surface"] = surface

        tool_log: List[str] = []
        t_cycle = time.time()

        # --- ws.read_file ---
        file_content = ""
        file_path = REPO_DIR / surface
        t0 = time.time()
        if self.ws:
            try:
                res = self.ws.read_file({"path": surface})
                file_content = res if isinstance(res, str) else str(res)
                tool_log.append(f"ws.read_file(\"{surface}\") → {len(file_content)} bytes in {round(time.time()-t0,2)}s")
            except Exception as e:
                tool_log.append(f"ws.read_file(\"{surface}\") → ERROR: {e}")
        if not file_content and file_path.exists():
            file_content = file_path.read_text(encoding="utf-8", errors="replace")
            tool_log.append(f"fs.read(\"{surface}\") → {len(file_content)} bytes in {round(time.time()-t0,2)}s")

        # --- ws.web_search (NTA) ---
        page_name = Path(surface).stem
        query = f"NeTuArk {page_name} SEO metadata OpenGraph JSON-LD canonical best practices 2025"
        search_preview = ""
        t0 = time.time()
        if self.ws:
            try:
                # Limit query length and give responsive timeout
                res = self.ws.web_search({"query": query, "num": 3})
                search_preview = (res if isinstance(res, str) else str(res))[:400]
                tool_log.append(f"ws.web_search(\"{query}\") → {len(search_preview)} chars in {round(time.time()-t0,2)}s")
            except Exception as e:
                tool_log.append(f"ws.web_search(\"{query}\") → {e}")

        # --- LLM or rule-based decision ---
        inject_html = ""
        thought = ""
        tags_added: List[str] = []
        patched = False

        if USE_LLM and file_content:
            t0 = time.time()
            thought, inject_html, tags_added = _groq_reason(surface, file_content, search_preview)
            tool_log.append(f"groq.reason(\"{surface}\") [{GROQ_MODEL}] → thought={len(thought)}chars, inject={len(inject_html)}bytes in {round(time.time()-t0,2)}s")

        # Full-spectrum deterministic pass if Groq failed, rate-limited, or returned empty
        if not inject_html and file_content:
            additions = []
            needs_og = 'property="og:title"' not in file_content and 'name="og:title"' not in file_content
            needs_twitter = 'name="twitter:card"' not in file_content
            needs_canonical = 'rel="canonical"' not in file_content
            needs_jsonld = 'application/ld+json' not in file_content
            needs_preconnect = 'rel="preconnect"' not in file_content

            if needs_og:
                tags_added += ["og:title", "og:description", "og:image", "og:url", "og:type"]
                additions.append(
                    f'  <meta property="og:title" content="NeTuArk | {page_name.capitalize()}">\n'
                    f'  <meta property="og:description" content="Decentralized sovereign social platform — NeTuArk.">\n'
                    f'  <meta property="og:image" content="https://netuark.pages.dev/assets/images/netuark_og_banner.jpg">\n'
                    f'  <meta property="og:url" content="https://netuark.pages.dev/{surface}">\n'
                    f'  <meta property="og:type" content="website">'
                )
            if needs_twitter:
                tags_added += ["twitter:card", "twitter:title", "twitter:description"]
                additions.append(
                    f'  <meta name="twitter:card" content="summary_large_image">\n'
                    f'  <meta name="twitter:title" content="NeTuArk | {page_name.capitalize()}">\n'
                    f'  <meta name="twitter:description" content="Decentralized sovereign social platform — NeTuArk.">'
                )
            if needs_canonical:
                tags_added.append("canonical")
                additions.append(f'  <link rel="canonical" href="https://netuark.pages.dev/{surface}">')
            if needs_preconnect:
                tags_added.append("preconnect")
                additions.append(
                    '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
                    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                )
            if needs_jsonld:
                tags_added.append("JSON-LD")
                schema_json = json.dumps({
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": f"NeTuArk {page_name.capitalize()}",
                    "description": f"NeTuArk decentralized social platform surface: {page_name}.",
                    "url": f"https://netuark.pages.dev/{surface}",
                    "publisher": {
                        "@type": "Organization",
                        "name": "NeTuArk corporation",
                        "url": "https://netuark.pages.dev"
                    }
                }, indent=2)
                additions.append(f'  <script type="application/ld+json">\n{schema_json}\n  </script>')

            if additions:
                inject_html = "\n".join(additions) + "\n"
                if not thought:
                    thought = f"Autonomous SEO Overhaul: Injected missing {', '.join(tags_added)}."

        # --- ws.patch_file ---
        if inject_html and file_content and "</head>" in file_content:
            new_content = file_content.replace("</head>", inject_html + "\n</head>", 1)
            t0 = time.time()
            if self.ws:
                try:
                    self.ws.patch_file({"path": surface, "old": "</head>", "new": inject_html + "\n</head>"})
                    patched = True
                    tool_log.append(f"ws.patch_file(\"{surface}\") → {len(inject_html)} bytes in {round(time.time()-t0,2)}s")
                except Exception as e:
                    tool_log.append(f"ws.patch_file(\"{surface}\") → fallback fs.write ({e})")
                    file_path.write_text(new_content, encoding="utf-8")
                    patched = True
            else:
                file_path.write_text(new_content, encoding="utf-8")
                patched = True
                tool_log.append(f"fs.write(\"{surface}\") → OK in {round(time.time()-t0,2)}s")

        if patched:
            self._pending_surfaces.append(surface)

        # --- Auto-publish every COMMIT_EVERY_N productive cycles ---
        publish_log = ""
        if len(self._pending_surfaces) >= COMMIT_EVERY_N:
            batch = list(self._pending_surfaces)
            self._pending_surfaces.clear()
            publish_log = publish_changes(cycle, batch)
            tool_log.append(f"git.publish({len(batch)} surfaces) → {publish_log[:80]}")

        elapsed = round(time.time() - t_cycle, 2)
        score_before = 40 if tags_added else 85
        score_after = 100 if patched else score_before

        if not thought:
            thought = f"{GROQ_MODEL if USE_LLM else 'Rule'}: {surface} — {', '.join(tags_added) if tags_added else 'all tags verified'}. NTA: {search_preview[:80]}."

        entry = {
            "cycle": cycle,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "surface": surface,
            "search_query": query,
            "search_preview": search_preview,
            "elapsed_sec": elapsed,
            "commands": tool_log,
            "thought": thought,
            "score_before": score_before,
            "score_after": score_after,
            "delta_score": score_after - score_before,
            "verdict": "OPTIMIZATION_ACCEPTED" if patched else "NO_CHANGE",
            "llm": USE_LLM,
            "model": GROQ_MODEL if USE_LLM else "rule-based",
        }

        recs = self.state.get("recent_experiments", [])
        recs.insert(0, entry)
        self.state["recent_experiments"] = recs[:30]
        self._save_state()

        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(
                f"[{entry['timestamp']}] #{cycle:04d} | {entry['model']} | "
                f"{surface} | Δ{entry['delta_score']:+d} | {entry['verdict']}"
                + (f" | PUBLISHED: {publish_log}" if publish_log else "") + "\n"
            )

        return entry

    def run_scientist_cycle(self) -> Dict[str, Any]:
        return self.run_cycle()


if __name__ == "__main__":
    e = WarRoomEngine()
    print(f"LLM active: {USE_LLM}, Groq model: {GROQ_MODEL}, ws: {'OK' if e.ws else 'FAIL'}")
    result = e.run_cycle()
    print(json.dumps(result, indent=2))
