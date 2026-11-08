import os
import sys
import time
import json
import shutil
import tempfile
import threading
import urllib.request
from pathlib import Path

from swades_git import SwadesGitManager
from swades_engine import SwadesAgentEngine
from swades_server import ThreadedHTTPServer, SwadesHTTPHandler

def test_git_manager():
    print("\n--- TEST 1: SwadesGitManager Sandbox, Security & Lifecycle ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a mock remote git repo
        remote_repo = Path(tmp_dir) / "remote_repo.git"
        remote_repo.mkdir()
        import subprocess
        subprocess.run(["git", "init", "--bare"], cwd=remote_repo, check=True, capture_output=True)

        # Seed initial commit
        work_seed = Path(tmp_dir) / "seed"
        subprocess.run(["git", "clone", str(remote_repo), str(work_seed)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Seed User"], cwd=work_seed, check=True)
        subprocess.run(["git", "config", "user.email", "seed@swades.local"], cwd=work_seed, check=True)
        (work_seed / "README.md").write_text("# Swades Repo\nInitial content\n")
        subprocess.run(["git", "add", "README.md"], cwd=work_seed, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=work_seed, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=work_seed, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=work_seed, check=True)

        # Test SwadesGitManager
        git_mgr = SwadesGitManager(base_storage_dir=os.path.join(tmp_dir, "workspaces"))
        
        # Test quota check
        ok, msg = git_mgr.check_storage_quota()
        assert ok, f"Storage quota failed: {msg}"
        print(f"✓ Storage quota check passed: {msg}")

        task_id = "task_alpha1"
        sandbox = git_mgr.create_sandbox(str(remote_repo), task_id, base_branch="main")
        assert sandbox.exists(), "Sandbox directory must exist"
        
        # Verify branch is swades/task_alpha1
        res = subprocess.run(["git", "branch", "--show-current"], cwd=sandbox, capture_output=True, text=True)
        assert res.stdout.strip() == f"swades/{task_id}", f"Expected branch swades/{task_id}, got: {res.stdout.strip()}"

        # Verify in-memory security: token NOT leaked into .git/config
        config_text = (sandbox / ".git" / "config").read_text(encoding="utf-8")
        assert "x-access-token" not in config_text, "Security violation: token found in .git/config"
        print("✓ Security verified: Zero token credentials persisted into .git/config!")

        # Modify a file and commit
        (sandbox / "swades_app.py").write_text("print('Hello from Swades')\n")
        committed = git_mgr.commit_changes(sandbox, "feat(swades): add app")
        assert committed, "Commit should succeed"

        diff = git_mgr.get_diff(sandbox)
        assert "swades_app.py" in diff or "Hello from Swades" in diff, "Diff must show changes"
        print(f"✓ Unified diff extracted cleanly:\n{diff.strip()[:200]}...")

        # Test clean sandbox teardown
        purged = git_mgr.teardown_sandbox(task_id)
        assert purged, "Teardown must report success"
        assert not sandbox.exists(), "Sandbox directory must be deleted after teardown"
        print("✓ Sandbox creation, branch isolation, unified diff, security check, and teardown PASSED!")

def test_agent_engine_local_tools():
    print("\n--- TEST 2: SwadesAgentEngine Local Tools ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        engine = SwadesAgentEngine(ws)

        # 1. write_file
        res = engine.write_file("core/calc.py", "def add(a, b):\n    return a + b\n")
        assert any(w in res.lower() for w in ["created", "wrote", "successfully"]), f"write_file failed: {res}"

        # 2. read_file
        content = engine.read_file("core/calc.py")
        assert "def add(a, b):" in content, f"read_file failed: {content}"

        # 3. list_dir
        listing = engine.list_dir(".")
        assert "core" in listing, f"list_dir failed: {listing}"

        # 4. search_code
        search = engine.search_code("def add", ".")
        assert "core/calc.py" in search, f"search_code failed: {search}"

        # 5. run_command
        cmd_out = engine.run_command("python3 -c 'from core.calc import add; print(\"SUM:\", add(2, 3))'")
        assert "SUM: 5" in cmd_out, f"run_command failed: {cmd_out}"
        print("✓ Agent tools (read_file, write_file, list_dir, search_code, run_command) PASSED!")

def test_http_server():
    print("\n--- TEST 3: Swades Agentic IDE HTTP/SSE Server ---")
    port = 8993
    server = ThreadedHTTPServer(("127.0.0.1", port), SwadesHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    try:
        # GET /
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "Swades IDE" in html
            assert "interactive-widget=resizes-content" in html
            assert "Create Pull Request" in html
            print("✓ GET / returned valid Swades IDE HTML with Nir Eyal mobile ergonomics!")

        # POST /api/swades/task (Validation for empty prompt)
        req_body = json.dumps({"prompt": "", "repo_url": "local_scratch"}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/swades/task", data=req_body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Empty prompt should fail with 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            print("✓ POST /api/swades/task rejected empty prompt as expected!")

        # POST /api/swades/task (Valid task)
        req_body = json.dumps({"prompt": "Create math_mod.py with an add function", "repo_url": "local_scratch"}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/swades/task", data=req_body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            task_id = data.get("task_id")
            assert task_id and task_id.startswith("swades_"), f"Invalid task_id: {task_id}"
            print(f"✓ Task successfully queued with task_id: {task_id}")

        # GET /api/swades/status
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/swades/status") as resp:
            assert resp.status == 200
            sdata = json.loads(resp.read().decode("utf-8"))
            assert "active_tasks" in sdata
            print(f"✓ GET /api/swades/status verified active daemon state.")

    finally:
        server.shutdown()
        server.server_close()
        print("✓ Swades server shut down cleanly.")

if __name__ == "__main__":
    test_git_manager()
    test_agent_engine_local_tools()
    test_http_server()
    print("\n==============================================")
    print("ALL 3 SWADES IDE TEST SUITES PASSED 100%!")
    print("==============================================")
