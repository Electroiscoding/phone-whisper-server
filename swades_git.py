import os
import shutil
import subprocess
import urllib.request
import urllib.error
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

class SwadesGitManager:
    def __init__(self, base_storage_dir: Optional[str] = None, github_token: Optional[str] = None):
        if base_storage_dir:
            self.storage_dir = Path(base_storage_dir)
        else:
            self.storage_dir = Path.home() / ".swades_storage" / "swades_workspaces"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.github_token = (github_token.strip() if github_token else None) or self._load_github_token()

    def _load_github_token(self) -> Optional[str]:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            return token.strip()
        candidates = [
            Path.home() / "githubpattoken.txt",
            Path.home() / ".github_token",
            Path("/data/data/com.termux/files/home/githubpattoken.txt")
        ]
        for p in candidates:
            if p.exists():
                try:
                    tok = p.read_text(encoding="utf-8").strip()
                    if tok:
                        return tok
                except Exception:
                    pass
        return None

    def _run_git_secure(self, args: list, cwd: Optional[Path] = None, timeout: int = 60) -> subprocess.CompletedProcess:
        cmd = ["git"]
        if self.github_token:
            auth_str = f"x-access-token:{self.github_token}"
            auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            cmd.extend(["-c", f"http.extraheader=Authorization: Basic {auth_b64}"])
        cmd.extend(args)
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if self.github_token:
            if self.github_token in res.stderr:
                res.stderr = res.stderr.replace(self.github_token, "[REDACTED_PAT]")
            if self.github_token in res.stdout:
                res.stdout = res.stdout.replace(self.github_token, "[REDACTED_PAT]")
        return res

    def check_storage_quota(self, min_free_mb: int = 1500) -> Tuple[bool, str]:
        total, used, free = shutil.disk_usage(self.storage_dir)
        free_mb = free / (1024 * 1024)
        if free_mb < min_free_mb:
            return False, f"Insufficient disk space ({free_mb:.1f}MB free, required {min_free_mb}MB)."
        return True, f"Storage quota OK ({free_mb:.1f}MB free)."

    def create_sandbox(self, repo_url: str, task_id: str, base_branch: str = "main") -> Path:
        ok, msg = self.check_storage_quota()
        if not ok:
            raise RuntimeError(msg)

        workspace_path = self.storage_dir / task_id
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)

        # Clone using secure in-memory header (no token inside URL or .git/config)
        clean_url = repo_url
        if clean_url.startswith("git@"):
            clone_cmd = ["clone", "--depth", "1", clean_url, str(workspace_path)]
        else:
            clone_cmd = ["clone", "--depth", "1", clean_url, str(workspace_path)]

        res = self._run_git_secure(clone_cmd, timeout=120)
        if res.returncode != 0:
            if "not found" in res.stderr or "Remote branch" in res.stderr:
                res = self._run_git_secure(["clone", clean_url, str(workspace_path)], timeout=120)
            if res.returncode != 0:
                raise RuntimeError(f"Git clone failed: {res.stderr.strip() or res.stdout.strip()}")

        branch_name = f"swades/{task_id}"
        self._run_git_secure(["checkout", "-b", branch_name], cwd=workspace_path)
        self._run_git_secure(["config", "user.name", "Swades AI Agent"], cwd=workspace_path)
        self._run_git_secure(["config", "user.email", "swades-agent@phone-server.local"], cwd=workspace_path)
        return workspace_path

    def get_diff(self, workspace_path: Path) -> str:
        res = self._run_git_secure(["diff", "HEAD"], cwd=workspace_path)
        if res.stdout.strip():
            return res.stdout
        res_cached = self._run_git_secure(["diff", "--cached"], cwd=workspace_path)
        if res_cached.stdout.strip():
            return res_cached.stdout
        res_prev = self._run_git_secure(["diff", "HEAD~1"], cwd=workspace_path)
        if res_prev.returncode == 0 and res_prev.stdout.strip():
            return res_prev.stdout
        res_show = self._run_git_secure(["show", "--stat", "--oneline"], cwd=workspace_path)
        return res_show.stdout

    def commit_changes(self, workspace_path: Path, commit_message: str) -> bool:
        self._run_git_secure(["add", "-A"], cwd=workspace_path)
        status = self._run_git_secure(["status", "--porcelain"], cwd=workspace_path)
        if not status.stdout.strip():
            return False
        res = self._run_git_secure(["commit", "-m", commit_message], cwd=workspace_path)
        return res.returncode == 0

    def push_branch(self, workspace_path: Path, branch_name: str) -> Tuple[bool, str]:
        res = self._run_git_secure(["push", "-u", "origin", branch_name, "--force"], cwd=workspace_path, timeout=60)
        return res.returncode == 0, res.stderr if res.returncode != 0 else res.stdout

    def extract_repo_slug(self, repo_url: str) -> Optional[str]:
        clean = repo_url.rstrip("/").removesuffix(".git")
        if "github.com/" in clean:
            return clean.split("github.com/")[-1]
        if "github.com:" in clean:
            return clean.split("github.com:")[-1]
        return None

    def create_pull_request(self, repo_url: str, branch_name: str, base_branch: str, title: str, body: str) -> Dict[str, Any]:
        if not self.github_token:
            return {"success": False, "error": "No GitHub PAT configured in environment or ~/githubpattoken.txt"}

        repo_slug = self.extract_repo_slug(repo_url)
        if not repo_slug:
            return {"success": False, "error": f"Invalid GitHub repo URL: {repo_url}"}

        api_url = f"https://api.github.com/repos/{repo_slug}/pulls"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Swades-Agentic-IDE"
        }
        payload = json.dumps({
            "title": title,
            "head": branch_name,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True
        }).encode("utf-8")

        req = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"success": True, "pr_url": data.get("html_url"), "pr_number": data.get("number")}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message", err_body)
            except Exception:
                msg = err_body
            return {"success": False, "error": f"GitHub API error ({e.code}): {msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def merge_to_base(self, workspace_path: Path, branch_name: str, base_branch: str = "main") -> Tuple[bool, str]:
        res_fetch = self._run_git_secure(["fetch", "origin", f"{base_branch}:{base_branch}"], cwd=workspace_path)
        res_checkout = self._run_git_secure(["checkout", base_branch], cwd=workspace_path)
        if res_checkout.returncode != 0:
            return False, f"Failed to checkout {base_branch}: {res_checkout.stderr}"
        res_merge = self._run_git_secure(["merge", branch_name, "--no-edit"], cwd=workspace_path)
        if res_merge.returncode != 0:
            self._run_git_secure(["merge", "--abort"], cwd=workspace_path)
            return False, f"Merge conflict: {res_merge.stderr or res_merge.stdout}"
        res_push = self._run_git_secure(["push", "origin", base_branch], cwd=workspace_path, timeout=60)
        return res_push.returncode == 0, res_push.stdout or res_push.stderr

    def teardown_sandbox(self, task_id: str) -> bool:
        workspace_path = self.storage_dir / task_id
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
            return True
        return False
