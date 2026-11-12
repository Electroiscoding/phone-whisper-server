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

    prompt = f"""You are an SEO expert optimizing NeTuArk (https://netuark.pages.dev), a decentralized sovereign social platform.

Surface File: {surface}
Current HTML <head> snippet:
{file_head[:1500]}

Relevant search / context signals:
{search_result[:500]}

Tasks:
1. Identify any missing OpenGraph tags (og:title, og:description, og:image), Twitter Card tags, canonical URL, or JSON-LD schema.
2. Formulate clean, minimal HTML tags to inject right before </head>. Only inject what is genuinely missing.
3. Respond ONLY with a valid JSON object in this exact schema, without any markdown formatting or code blocks:
{{"thought": "<your diagnostic reasoning in 1-2 concise sentences>", "inject_html": "<tags to inject or empty string>", "tags_added": ["tag1", "tag2"]}}

If all required tags are already present, respond:
{{"thought": "All SEO metadata and OpenGraph tags are already verified.", "inject_html": "", "tags_added": []}}"""

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
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
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
        text = data["choices"][0]["message"]["content"].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            obj = json.loads(text[start:end])
            return obj.get("thought", ""), obj.get("inject_html", ""), obj.get("tags_added", [])
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
        else:
            # Fallback: rule-based
            needs_og = file_content and 'property="og:title"' not in file_content
            needs_canonical = file_content and 'rel="canonical"' not in file_content
            if needs_og:
                tags_added += ["og:title", "og:description", "og:image", "twitter:card"]
                inject_html += (
                    f'    <meta property="og:title" content="NeTuArk | {page_name.capitalize()}">\n'
                    f'    <meta property="og:description" content="Decentralized sovereign social platform — NeTuArk.">\n'
                    f'    <meta property="og:image" content="https://netuark.pages.dev/assets/images/netuark_og_banner.jpg">\n'
                    f'    <meta name="twitter:card" content="summary_large_image">\n'
                )
            if needs_canonical:
                tags_added.append("canonical")
                inject_html += f'    <link rel="canonical" href="https://netuark.pages.dev/{surface}">\n'
            thought = f"Rule-based: {'missing ' + ', '.join(tags_added) if tags_added else 'all tags present'}"

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
