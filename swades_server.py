import os
import sys
import json
import time
import uuid
import queue
import threading
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from swades_git import SwadesGitManager
from swades_engine import SwadesAgentEngine

TASK_QUEUES = {}
TASK_CONTEXTS = {}
TASK_EVENTS = {}
TASKS_LOCK = threading.Lock()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class SwadesHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/ide", "/index.html"]:
            self.serve_html()
        elif path == "/favicon.ico":
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()
        elif path == "/api/swades/stream":
            self.handle_stream(parsed)
        elif path == "/api/swades/events":
            self.handle_events(parsed)
        elif path == "/api/swades/status":
            self.handle_status(parsed)
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b"Not Found")


    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/swades/task":
            self.handle_create_task()
        elif path == "/api/swades/action":
            self.handle_action()
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def serve_html(self):
        html_path = Path(__file__).parent / "swades_ide.html"
        if not html_path.exists():
            html_path = Path.cwd() / "swades_ide.html"
        if html_path.exists():
            data = html_path.read_bytes()
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"swades_ide.html not found.")

    def handle_create_task(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        try:
            req_data = json.loads(body)
        except Exception as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        repo_url = req_data.get("repo_url", "local_scratch")
        prompt = req_data.get("prompt", "")
        image_data = req_data.get("image_data")
        test_command = req_data.get("test_command")
        github_token = req_data.get("github_token")

        if not prompt:
            self._send_json({"error": "Prompt cannot be empty."}, status=400)
            return

        task_id = f"swades_{uuid.uuid4().hex[:8]}"
        q = queue.Queue()
        with TASKS_LOCK:
            TASK_QUEUES[task_id] = q

        worker = threading.Thread(
            target=run_async_swades_task,
            args=(task_id, repo_url, prompt, image_data, test_command, q, github_token),
            daemon=True
        )
        worker.start()

        self._send_json({"task_id": task_id, "status": "queued"})

    def handle_stream(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        task_id = qs.get("task_id", [""])[0]
        with TASKS_LOCK:
            q = TASK_QUEUES.get(task_id)

        if not q:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b"Task stream not found.")
            return

        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                try:
                    event = q.get(timeout=15.0)
                    msg = f"data: {json.dumps(event)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                    if event.get("type") in ["completed", "error"]:
                        break
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_events(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        task_id = qs.get("task_id", [""])[0]
        since = int(qs.get("since", [0])[0])
        with TASKS_LOCK:
            evs = list(TASK_EVENTS.get(task_id, []))
            ctx = TASK_CONTEXTS.get(task_id)
        status = "completed" if (ctx and ctx.get("diff")) else ("active" if evs else "none")
        new_evs = evs[since:] if since < len(evs) else []
        self._send_json({"task_id": task_id, "status": status, "events": new_evs, "next_index": len(evs)})


    def handle_action(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        try:
            req_data = json.loads(body)
        except Exception:
            self._send_json({"error": "Invalid JSON"}, status=400)
            return

        task_id = req_data.get("task_id", "")
        action = req_data.get("action", "")

        with TASKS_LOCK:
            ctx = TASK_CONTEXTS.get(task_id)

        if not ctx:
            self._send_json({"error": "Task context not found or already purged."}, status=404)
            return

        git_mgr = ctx["git_mgr"]
        workspace = ctx["workspace"]
        repo_url = ctx["repo_url"]
        branch_name = f"swades/{task_id}"

        if action == "branch":
            ok, msg = git_mgr.push_branch(workspace, branch_name)
            self._send_json({"success": ok, "message": f"Branch {branch_name} pushed. {msg}"})
        elif action == "pr":
            git_mgr.push_branch(workspace, branch_name)
            title = f"feat(swades): {ctx.get('summary', 'Automated task resolution')}"
            body_text = f"Automated Pull Request generated by Swades Agentic IDE.\n\nTask:\n{ctx.get('prompt')}\n\nVerification:\n{ctx.get('test_output', 'Verified in isolated sandbox')}"
            pr_res = git_mgr.create_pull_request(repo_url, branch_name, "main", title, body_text)
            self._send_json(pr_res)
        elif action == "merge":
            ok, msg = git_mgr.merge_to_base(workspace, branch_name, "main")
            self._send_json({"success": ok, "message": f"Merged to main: {msg}"})
        elif action == "purge":
            git_mgr.teardown_sandbox(task_id)
            with TASKS_LOCK:
                TASK_CONTEXTS.pop(task_id, None)
            self._send_json({"success": True, "message": f"Sandbox {task_id} cleanly purged from storage."})
        else:
            self._send_json({"error": f"Unknown action: {action}"}, status=400)

    def handle_status(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        task_id = qs.get("task_id", [""])[0]
        with TASKS_LOCK:
            ctx = TASK_CONTEXTS.get(task_id)
        if ctx:
            self._send_json({"status": "active", "task_id": task_id, "repo": ctx.get("repo_url")})
        else:
            self._send_json({"status": "none", "active_tasks": len(TASK_CONTEXTS)})

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        resp = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

def run_async_swades_task(task_id: str, repo_url: str, prompt: str, image_data: Optional[str], test_command: Optional[str], q: queue.Queue, github_token: Optional[str] = None):
    git_mgr = SwadesGitManager(github_token=github_token)
    workspace = None

    def emit(ev):
        with TASKS_LOCK:
            if task_id not in TASK_EVENTS:
                TASK_EVENTS[task_id] = []
            TASK_EVENTS[task_id].append(ev)
        q.put(ev)

    try:
        emit({"type": "status", "state": "CLONING", "message": f"Swades provisioning sandbox for {repo_url}..."})
        if repo_url == "local_scratch" or not repo_url.startswith("http"):
            workspace = git_mgr.storage_dir / task_id
            workspace.mkdir(parents=True, exist_ok=True)
            import subprocess
            subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Swades AI Agent"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.email", "swades-agent@phone-server.local"], cwd=workspace, check=True)
            subprocess.run(["git", "checkout", "-b", f"swades/{task_id}"], cwd=workspace, check=True, capture_output=True)
        else:
            workspace = git_mgr.create_sandbox(repo_url, task_id)

        def event_cb(ev):
            emit(ev)

        engine = SwadesAgentEngine(workspace, on_event=event_cb)
        result = engine.execute_task(prompt, image_data=image_data, test_command=test_command)

        # Commit and extract diff
        git_mgr.commit_changes(workspace, f"feat(swades): {prompt[:50]}")
        diff_text = git_mgr.get_diff(workspace)
        emit({"type": "diff", "diff": diff_text})

        with TASKS_LOCK:
            TASK_CONTEXTS[task_id] = {
                "git_mgr": git_mgr,
                "workspace": workspace,
                "repo_url": repo_url,
                "prompt": prompt,
                "summary": prompt[:60],
                "test_output": result.get("test_output", ""),
                "diff": diff_text
            }

        emit({"type": "completed", "result": result})

    except Exception as e:
        emit({"type": "error", "message": str(e)})


def run_server(port: int = 8088):
    server = ThreadedHTTPServer(("0.0.0.0", port), SwadesHTTPHandler)
    print(f"Swades Agentic IDE Server running at http://0.0.0.0:{port} (serving swades_ide.html)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    run_server(p)
