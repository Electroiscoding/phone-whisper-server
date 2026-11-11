#!/usr/bin/env python3
"""Phone-Native Swades SEO War Room Engine — wires real tool calls, auto-commits to GitHub."""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

HOME_DIR = Path("/data/data/com.termux/files/home")
SWADES_DIR = HOME_DIR / "Swades"
REPO_DIR = HOME_DIR / "glowing-carnival"
STATE_FILE = HOME_DIR / "war_room_state.json"
LOG_FILE = HOME_DIR / "war_room_experiments.log"
GIT_PATH = "/data/data/com.termux/files/usr/bin/git"
BRANCH = "feat/swades-infinite-seo"
COMMIT_EVERY_N = 5  # commit + push after every 5 productive cycles

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
    msg = f"swades(seo): auto-publish cycle {cycle} — {len(surfaces_changed)} surface(s): {', '.join(surfaces_changed[:3])}"
    commit_out = _git(["commit", "-m", msg])
    push_out = _git(["push", "origin", BRANCH])
    return f"commit: {commit_out[:80]} | push: {push_out[:80]}"


class WarRoomEngine:
    def __init__(self):
        self.ws = None
        if swades and REPO_DIR.exists():
            try:
                cfg = swades.Config.load(llm=False, root=REPO_DIR)
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
                return s
            except Exception:
                pass
        return {
            "war_room_status": "WAR_ROOM_ACTIVE",
            "mission": MISSION,
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
        page_name = Path(surface).stem

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

        # --- ws.web_search ---
        query = f"NeTuArk {page_name} SEO metadata OpenGraph JSON-LD canonical best practices"
        search_preview = ""
        t0 = time.time()
        if self.ws:
            try:
                res = self.ws.web_search({"query": query})
                search_preview = (res if isinstance(res, str) else str(res))[:300]
                tool_log.append(f"ws.web_search(\"{query}\") → {len(search_preview)} chars in {round(time.time()-t0,2)}s")
            except Exception as e:
                tool_log.append(f"ws.web_search(\"{query}\") → ERROR: {e}")
                search_preview = f"Search error: {e}"

        # --- Decide patch ---
        needs_og = file_content and 'property="og:title"' not in file_content
        needs_canonical = file_content and 'rel="canonical"' not in file_content
        patched = False

        if (needs_og or needs_canonical) and file_content and "</head>" in file_content:
            inject = ""
            if needs_canonical:
                inject += f'    <link rel="canonical" href="https://netuark.pages.dev/{surface}">\n'
            if needs_og:
                inject += (
                    f'    <meta property="og:title" content="NeTuArk | {page_name.capitalize()}">\n'
                    f'    <meta property="og:description" content="Decentralized sovereign social platform — NeTuArk.">\n'
                    f'    <meta property="og:image" content="https://netuark.pages.dev/assets/images/netuark_og_banner.jpg">\n'
                    f'    <meta name="twitter:card" content="summary_large_image">\n'
                )
            new_content = file_content.replace("</head>", inject + "</head>", 1)

            t0 = time.time()
            if self.ws:
                try:
                    self.ws.patch_file({
                        "path": surface,
                        "old": "</head>",
                        "new": inject + "</head>",
                    })
                    patched = True
                    tool_log.append(f"ws.patch_file(\"{surface}\") → {len(inject)} bytes injected in {round(time.time()-t0,2)}s")
                except Exception as e:
                    tool_log.append(f"ws.patch_file(\"{surface}\") → ERROR: {e}, falling back to fs.write")
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
            surfaces_batch = list(self._pending_surfaces)
            self._pending_surfaces.clear()
            publish_log = publish_changes(cycle, surfaces_batch)
            tool_log.append(f"git.publish() → {publish_log}")

        elapsed = round(time.time() - t_cycle, 2)
        score_before = 40 if needs_og else 85
        score_after = 100 if patched else score_before

        missing = []
        if needs_og:
            missing.append("OG/Twitter")
        if needs_canonical:
            missing.append("canonical")

        thought = (
            f"Surface {surface}: read {len(file_content)} bytes. "
            + (f"Missing: {', '.join(missing)}. Injected tags." if missing and patched else
               ("All tags present — no patch needed." if not missing else "Skipped — no </head> found."))
            + (f" Auto-published: {publish_log}" if publish_log else "")
            + f" NTA: {search_preview[:120] if search_preview else 'no result'}."
        )

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
        }

        recs = self.state.get("recent_experiments", [])
        recs.insert(0, entry)
        self.state["recent_experiments"] = recs[:30]
        self._save_state()

        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(
                f"[{entry['timestamp']}] #{cycle:04d} | {surface} | Δ{entry['delta_score']:+d} | "
                f"{entry['verdict']}{' | PUBLISHED' if publish_log else ''}\n"
            )

        return entry

    def run_scientist_cycle(self) -> Dict[str, Any]:
        return self.run_cycle()


if __name__ == "__main__":
    e = WarRoomEngine()
    result = e.run_cycle()
    print(json.dumps(result, indent=2))
