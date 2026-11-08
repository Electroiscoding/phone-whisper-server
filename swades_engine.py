import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Seamless integration with ~/Swades core
SWADES_REPO_PATH = Path.home() / "Swades"
if str(SWADES_REPO_PATH) not in sys.path and SWADES_REPO_PATH.exists():
    sys.path.insert(0, str(SWADES_REPO_PATH))

try:
    import main as swades_core
except ImportError:
    swades_core = None

MODEL_CODE = "openai/gpt-oss-120b"
MODEL_CODE_FAST = "openai/gpt-oss-20b"
MODEL_VISION = "qwen/qwen3.8-27b"
BANNED_MODELS = {"allam", "allam-7b", "allam-2-7b"}

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

class SwadesAgentEngine:
    def __init__(self, workspace_path: Path, on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.workspace_path = Path(workspace_path)
        self.on_event = on_event or (lambda e: None)
        self.groq_key = self._load_groq_key()
        if not self.groq_key:
            raise ValueError("Groq API key not found in ~/.groq_key or environment variable GROQ_API_KEY.")

        # Initialize native ~/Swades Workspace
        self.swades_ws = None
        if swades_core:
            try:
                cfg = swades_core.Config.load(llm=False, root=self.workspace_path)
                self.swades_ws = swades_core.Workspace(cfg)
            except Exception:
                pass

    def _load_groq_key(self) -> Optional[str]:
        key = os.environ.get("GROQ_API_KEY")
        if key:
            return key.strip()
        candidates = [
            Path.home() / ".groq_key",
            Path.home() / "groqkey.txt",
            Path("/data/data/com.termux/files/home/.groq_key")
        ]
        for p in candidates:
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        return content
                except Exception:
                    pass
        return None

    def _emit(self, event_type: str, data: Dict[str, Any]):
        payload = {"type": event_type, "timestamp": time.time(), **data}
        self.on_event(payload)

    def _call_groq(self, messages: List[Dict[str, Any]], model: str = MODEL_CODE, temperature: float = 0.2, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if any(banned in model.lower() for banned in BANNED_MODELS):
            model = MODEL_CODE

        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
            "User-Agent": "Swades-Agentic-IDE/1.0"
        }
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        for attempt in range(5):
            req = urllib.request.Request(GROQ_API_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                if e.code in [429, 500, 502, 503, 504] and attempt < 4:
                    if body["model"] == MODEL_CODE and attempt >= 1:
                        body["model"] = MODEL_CODE_FAST
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Groq API Error {e.code}: {err_msg}")
            except Exception as e:
                if attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Groq connection error: {e}")


    # --- Native Swades Tool Dispatchers ---
    def map_repo(self, path: str = ".", depth: int = 4) -> str:
        if self.swades_ws:
            try:
                return str(self.swades_ws.map_repo({"path": path, "depth": depth}))
            except Exception:
                pass
        return self.list_dir(path)

    def read_file(self, rel_path: str, offset: int = 1, limit: int = 200) -> str:
        if self.swades_ws:
            try:
                res = self.swades_ws.read_file({"path": rel_path, "start": offset, "end": offset + limit - 1})
                return str(res)
            except Exception:
                pass

        target = (self.workspace_path / rel_path).resolve()
        if not target.is_relative_to(self.workspace_path) or not target.exists():
            return f"Error: File '{rel_path}' not found."
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            start = max(1, offset)
            end = min(total, start + limit - 1)
            numbered = [f"{start + i}|{line}" for i, line in enumerate(lines[start-1:end])]
            return f"{rel_path} {start}-{end}/{total}\n" + "".join(numbered)
        except Exception as e:
            return f"Error reading file: {e}"

    def write_file(self, rel_path: str, content: str) -> str:
        if self.swades_ws:
            try:
                return str(self.swades_ws.create_file({"path": rel_path, "content": content, "overwrite": True}))
            except Exception:
                pass

        target = (self.workspace_path / rel_path).resolve()
        if not target.is_relative_to(self.workspace_path):
            return "Error: Path traversal outside workspace denied."
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote {len(content)} characters to {rel_path}."
        except Exception as e:
            return f"Error writing file: {e}"

    def patch_file(self, rel_path: str, old: str, new: str) -> str:
        if self.swades_ws:
            try:
                return str(self.swades_ws.patch_file({"path": rel_path, "old": old, "new": new}))
            except Exception as e:
                return f"Patch error: {e}"

        target = (self.workspace_path / rel_path).resolve()
        if not target.exists():
            return f"Error: File '{rel_path}' does not exist."
        try:
            content = target.read_text(encoding="utf-8")
            if old not in content:
                return f"Error: Old content not found in {rel_path}."
            updated = content.replace(old, new, 1)
            target.write_text(updated, encoding="utf-8")
            return f"Successfully patched {rel_path}."
        except Exception as e:
            return f"Error patching file: {e}"

    def list_dir(self, rel_path: str = ".") -> str:
        target = (self.workspace_path / rel_path).resolve()
        if not target.is_relative_to(self.workspace_path) or not target.exists():
            return f"Error: Directory '{rel_path}' does not exist."
        try:
            entries = []
            for item in sorted(target.iterdir()):
                if item.name.startswith(".git"):
                    continue
                kind = "DIR " if item.is_dir() else "FILE"
                entries.append(f"{kind} {item.relative_to(self.workspace_path)}")
            return "\n".join(entries[:150])
        except Exception as e:
            return f"Error listing directory: {e}"

    def search_code(self, pattern: str, rel_path: str = ".") -> str:
        if self.swades_ws:
            try:
                return str(self.swades_ws.grep({"pattern": pattern, "path": rel_path}))
            except Exception:
                pass
        target = (self.workspace_path / rel_path).resolve()
        cmd = ["grep", "-rnI", "--exclude-dir=.git", pattern, str(target)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = [l.replace(str(self.workspace_path) + "/", "") for l in res.stdout.strip().split("\n") if l]
        return "\n".join(lines[:80]) if lines else "No matches found."

    def run_command(self, command: str, timeout: int = 60) -> str:
        if self.swades_ws:
            try:
                return str(self.swades_ws.run({"cmd": command, "timeout": timeout}))
            except Exception:
                pass

        forbidden = ["rm -rf /", ":(){ :|:& };:", "dd if=", "mkfs"]
        if any(f in command for f in forbidden):
            return "Error: Command rejected for security safety."
        try:
            res = subprocess.run(command, shell=True, cwd=self.workspace_path, capture_output=True, text=True, timeout=timeout)
            out = res.stdout.strip()
            err = res.stderr.strip()
            code = res.returncode
            summary = f"[Exit Code: {code}]\n"
            if out: summary += f"STDOUT:\n{out[:4000]}\n"
            if err: summary += f"STDERR:\n{err[:4000]}\n"
            return summary if (out or err) else f"[Command executed with exit code {code} (no output)]"
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds."
        except Exception as e:
            return f"Error running command: {e}"

    def inspect_image(self, b64_image_or_url: str, prompt: str) -> str:
        messages = [
            {
                "role": "user",
                "content": f"[Attached UI Screenshot Context]\nUser instructions: {prompt}\nAnalyze visual components, CSS layout, and styling bug details."
            }
        ]
        res = self._call_groq(messages, model=MODEL_VISION, temperature=0.1)
        return res["choices"][0]["message"]["content"]

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read line-numbered contents of a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rel_path": {"type": "string", "description": "Relative file path."},
                            "offset": {"type": "integer", "description": "Start line (1-indexed)."},
                            "limit": {"type": "integer", "description": "Number of lines."}
                        },
                        "required": ["rel_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or overwrite content into a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rel_path": {"type": "string", "description": "Relative file path."},
                            "content": {"type": "string", "description": "Full file content."}
                        },
                        "required": ["rel_path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "patch_file",
                    "description": "Surgically replace old text block with new text in a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rel_path": {"type": "string", "description": "Relative file path."},
                            "old": {"type": "string", "description": "Exact text to replace."},
                            "new": {"type": "string", "description": "Replacement text."}
                        },
                        "required": ["rel_path", "old", "new"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "map_repo",
                    "description": "Show repository file tree with sizes and file counts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path."}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Grep for regex or text pattern in code files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Search pattern."},
                            "rel_path": {"type": "string", "description": "Subdirectory to restrict."}
                        },
                        "required": ["pattern"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute shell command (tests, build, linter).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Shell command to run."},
                            "timeout": {"type": "integer", "description": "Timeout in seconds."}
                        },
                        "required": ["command"]
                    }
                }
            }
        ]

    def _execute_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        if name == "read_file":
            return self.read_file(args.get("rel_path", ""), args.get("offset", 1), args.get("limit", 200))
        elif name == "write_file":
            return self.write_file(args.get("rel_path", ""), args.get("content", ""))
        elif name == "patch_file":
            return self.patch_file(args.get("rel_path", ""), args.get("old", ""), args.get("new", ""))
        elif name == "map_repo":
            return self.map_repo(args.get("path", "."))
        elif name == "search_code":
            return self.search_code(args.get("pattern", ""), args.get("rel_path", "."))
        elif name == "run_command":
            return self.run_command(args.get("command", ""), args.get("timeout", 60))
        return f"Unknown tool: {name}"

    def execute_task(self, prompt: str, image_data: Optional[str] = None, test_command: Optional[str] = None) -> Dict[str, Any]:
        self._emit("status", {"state": "PLANNING", "message": "Swades Agent analyzing repository and formulating execution plan..."})

        agents_rule = ""
        for rule_name in ["AGENTS.md", "GEMINI.md", ".cursorrules", "README.md"]:
            rf = self.workspace_path / rule_name
            if rf.exists():
                try:
                    agents_rule += f"\n--- {rule_name} ---\n" + rf.read_text(encoding="utf-8")[:2500]
                except Exception:
                    pass

        repo_map = self.map_repo(".")

        vision_analysis = ""
        if image_data:
            self._emit("status", {"state": "VISION_ANALYZING", "message": "Swades Multimodal Vision inspecting UI screenshot..."})
            try:
                vision_analysis = self.inspect_image(image_data, f"Analyze this UI screenshot and identify layout bugs or styling requirements matching: {prompt}")
                self._emit("vision_result", {"analysis": vision_analysis})
            except Exception as e:
                vision_analysis = f"Vision notice: {e}"

        system_prompt = f"""You are Swades, an elite autonomous software engineering agent running inside an isolated repository sandbox powered by ~/Swades core.
You must solve the user's task completely by inspecting files, writing modifications, and verifying tests.

RULES:
1. Strict quality: Zero placeholders, no '//TODO', no untested stubs.
2. Minimal changes: Solve with the absolute minimum lines and moving parts.
3. Use your tools (`read_file`, `write_file`, `patch_file`, `map_repo`, `search_code`, `run_command`).
4. Output your plan first, then execute tool calls until completion.
5. When done, output: 'TASK_COMPLETE: <concise summary of changes>'.

REPOSITORY ROOT CONTEXT:
{agents_rule}

CURRENT WORKSPACE MAP:
{repo_map}
"""
        user_message_content = f"TASK:\n{prompt}"
        if vision_analysis:
            user_message_content += f"\n\nMULTIMODAL UI VISION OBSERVATIONS:\n{vision_analysis}"
        if test_command:
            user_message_content += f"\n\nVERIFICATION TEST COMMAND:\nRun `{test_command}` to verify your changes."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_content}
        ]

        tools = self._get_tool_schemas()
        max_iterations = 12
        iterations = 0
        executed_steps = []

        self._emit("status", {"state": "EXECUTING", "message": "Swades executing autonomous tool loop..."})

        while iterations < max_iterations:
            iterations += 1
            response = self._call_groq(messages, model=MODEL_CODE, temperature=0.1, tools=tools)
            choice = response["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            thought_snippet = (msg.get("content") or msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
            if thought_snippet:
                self._emit("thought", {"thought": thought_snippet, "iteration": iterations})

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                if "TASK_COMPLETE" in (msg.get("content") or ""):
                    break
                messages.append({"role": "user", "content": "Please verify your work with run_command if needed, or reply 'TASK_COMPLETE: <summary>'."})
                continue

            for tc in tool_calls:
                fn = tc["function"]
                fn_name = fn["name"]
                try:
                    fn_args = json.loads(fn["arguments"])
                except Exception:
                    fn_args = {}

                self._emit("tool_start", {"tool": fn_name, "args": fn_args})
                res_str = self._execute_tool_call(fn_name, fn_args)
                self._emit("tool_result", {"tool": fn_name, "result": res_str[:300]})

                executed_steps.append({"tool": fn_name, "args": fn_args, "result": res_str[:500]})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": fn_name,
                    "content": res_str
                })

            time.sleep(1.0)


        # Bounded Self-Healing Test Verification Phase (Max 2 repair iterations)
        tests_passed = True
        test_output = ""
        if test_command:
            self._emit("status", {"state": "VERIFYING", "message": f"Running verification tests: `{test_command}`..."})
            test_output = self.run_command(test_command, timeout=90)
            if "[Exit Code: 0]" not in test_output and "exit code 0" not in test_output.lower():
                tests_passed = False
                self._emit("test_result", {"passed": False, "output": test_output})
                
                heal_attempts = 0
                while heal_attempts < 2 and not tests_passed:
                    heal_attempts += 1
                    self._emit("status", {"state": "SELF_HEALING", "message": f"Self-healing repair attempt {heal_attempts}/2..."})
                    heal_prompt = f"The verification test `{test_command}` failed with output:\n{test_output}\nDiagnose and fix the issue now using patch_file or write_file."
                    messages.append({"role": "user", "content": heal_prompt})
                    
                    heal_resp = self._call_groq(messages, model=MODEL_CODE, temperature=0.1, tools=tools)
                    h_msg = heal_resp["choices"][0]["message"]
                    messages.append(h_msg)
                    if h_msg.get("tool_calls"):
                        for tc in h_msg["tool_calls"]:
                            fn = tc["function"]
                            try:
                                fn_args = json.loads(fn["arguments"])
                            except Exception:
                                fn_args = {}
                            res_str = self._execute_tool_call(fn["name"], fn_args)
                            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": fn["name"], "content": res_str})
                    
                    test_output = self.run_command(test_command, timeout=90)
                    tests_passed = "[Exit Code: 0]" in test_output or "exit code 0" in test_output.lower()

        self._emit("status", {"state": "COMPLETED", "message": "Swades task execution completed."})

        return {
            "success": True,
            "iterations": iterations,
            "steps": executed_steps,
            "tests_passed": tests_passed,
            "test_output": test_output
        }
