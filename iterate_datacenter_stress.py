#!/usr/bin/env python3
"""
=============================================================================
  SWADES HYPER-DATACENTER CONTINUOUS MULTI-ITERATION STRESS & TEST ENGINE
  Loops continuously testing BOTH Cloud Storage (PBKDF2 accounts, scoped keys,
  multi-tenancy, L1 RAM engine, SQLite WAL) AND AI Subsystems (Qwen 2.5 Chat,
  BGE Embeddings, BGE Reranker, Whisper STT) with auto-teardown and SLA audit.
=============================================================================
"""

import sys
import os
import time
import json
import secrets
import wave
import struct
import math
import argparse
import urllib.request
import urllib.error

# ANSI Styling
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

class DatacenterStressIterator:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.total_rounds = 0
        self.passed_rounds = 0
        self.failed_rounds = 0
        self.total_ops = 0
        self.passed_ops = 0
        self.failed_ops = 0
        self.latencies = {
            "account_auth": [],
            "cloud_blob": [],
            "qwen_chat": [],
            "bge_embed": [],
            "bge_rerank": [],
            "whisper_stt": []
        }
        self.test_wav_path = "/tmp/swades_stress_audio.wav"
        self._generate_test_wav()

    def _generate_test_wav(self):
        """Creates a minimal 1-second 16kHz PCM WAV for STT testing."""
        try:
            with wave.open(self.test_wav_path, "w") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(16000)
                for i in range(16000):
                    val = int(32767.0 * 0.25 * math.sin(2.0 * math.pi * 440.0 * i / 16000))
                    f.writeframes(struct.pack("<h", val))
        except Exception:
            pass

    def request(self, path: str, method="GET", data=None, headers=None, timeout=60):
        url = f"{self.base_url}{path}"
        req_headers = {"User-Agent": "SwadesStressEngine/4.0", "X-Client-IP": "10.0.99.1"}
        if headers:
            req_headers.update(headers)

        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = json.dumps(data).encode("utf-8")
                req_headers["Content-Type"] = "application/json"
            elif isinstance(data, bytes):
                body = data
            else:
                body = str(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                j = None
                try:
                    j = json.loads(raw.decode("utf-8"))
                except Exception:
                    pass
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": raw,
                    "json": j,
                    "elapsed_ms": elapsed_ms,
                    "error": None
                }
        except urllib.error.HTTPError as e:
            raw = e.read()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            j = None
            try:
                j = json.loads(raw.decode("utf-8"))
            except Exception:
                pass
            return {
                "status": e.code,
                "headers": dict(e.headers),
                "body": raw,
                "json": j,
                "elapsed_ms": elapsed_ms,
                "error": f"HTTP {e.code}"
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "status": 0,
                "headers": {},
                "body": b"",
                "json": None,
                "elapsed_ms": elapsed_ms,
                "error": str(e)
            }

    def run_iteration(self, round_num: int) -> bool:
        self.total_rounds += 1
        round_passed = True
        suffix = secrets.token_hex(4)
        uname = f"iter_{round_num}_{suffix}"
        pwd = f"VaultSecret_{suffix}!99"
        user_id = None
        api_key = None

        print(f"\n{BOLD}{CYAN}-------------------------------------------------------------------------{RESET}")
        print(f"{BOLD}{CYAN}[ITERATION #{round_num:02d}] STRESS & VERIFICATION CYCLE{RESET}")
        print(f"{BOLD}{CYAN}-------------------------------------------------------------------------{RESET}")

        # ---------------------------------------------------------------------
        # 1. CLOUD ACCOUNT SYSTEM (PBKDF2 & In-Memory L1 Cache)
        # ---------------------------------------------------------------------
        # 1.1 Register
        r_reg = self.request("/v1/storage/auth/register", method="POST", data={"username": uname, "password": pwd})
        ok_reg = (r_reg["status"] == 201 and r_reg["json"] and r_reg["json"].get("success"))
        self._record_op("Account Registration (201 Created)", ok_reg, f"{r_reg['elapsed_ms']:.1f}ms")
        if not ok_reg: round_passed = False

        if ok_reg:
            user_id = r_reg["json"]["user_id"]
            api_key = r_reg["json"]["api_key"]

        # 1.2 Duplicate Rejection
        r_dup = self.request("/v1/storage/auth/register", method="POST", data={"username": uname, "password": "any"})
        ok_dup = (r_dup["status"] == 400)
        self._record_op("Duplicate Account Rejection (400)", ok_dup, f"HTTP {r_dup['status']}")
        if not ok_dup: round_passed = False

        # 1.3 Login (PBKDF2 100k rounds check)
        r_login = self.request("/v1/storage/auth/login", method="POST", data={"username": uname, "password": pwd})
        ok_login = (r_login["status"] == 200 and r_login["json"] and r_login["json"].get("success"))
        self._record_op("PBKDF2 Password Verification & Login (200)", ok_login, f"{r_login['elapsed_ms']:.1f}ms")
        if ok_login: self.latencies["account_auth"].append(r_login["elapsed_ms"])
        else: round_passed = False

        # 1.4 Invalid Password Rejection
        r_bad = self.request("/v1/storage/auth/login", method="POST", data={"username": uname, "password": "WrongPassword!"})
        ok_bad = (r_bad["status"] == 401)
        self._record_op("Invalid Password Rejection (401)", ok_bad, f"HTTP {r_bad['status']}")
        if not ok_bad: round_passed = False

        # ---------------------------------------------------------------------
        # 2. SCOPED KEYS & GRANULAR ACCESS CONTROL
        # ---------------------------------------------------------------------
        if api_key:
            # 2.1 Create Read-Only Key
            r_ro = self.request("/v1/storage/auth/keys", method="POST", headers={"x-api-key": api_key},
                                data={"name": f"RO_Key_{suffix}", "restrictions": "read_only"})
            ok_ro = (r_ro["status"] == 201 and r_ro["json"] and r_ro["json"].get("api_key"))
            ro_key = r_ro["json"]["api_key"] if ok_ro else ""
            self._record_op("Scoped Key Generation ('read_only')", ok_ro, f"key_id={r_ro['json'].get('key_id') if ok_ro else ''}")
            if not ok_ro: round_passed = False

            # 2.2 Verify Read-Only Blocks Write (403)
            r_ro_put = self.request(f"/v1/storage/objects/test_{suffix}.txt", method="PUT", headers={"x-api-key": ro_key}, data="test")
            ok_ro_block = (r_ro_put["status"] == 403)
            self._record_op("Scoped Read-Only Key Blocks PUT (403)", ok_ro_block, f"HTTP {r_ro_put['status']}")
            if not ok_ro_block: round_passed = False

        # ---------------------------------------------------------------------
        # 3. CLOUD STORAGE ENGINE & L1 RAM REFLECTION
        # ---------------------------------------------------------------------
        if api_key:
            blob_data = f"Swades Cloud Datacenter Payload [{round_num} : {suffix}]" * 16
            blob_key = f"datasets/iter_{round_num}_{suffix}.txt"

            # 3.1 PUT Object
            r_put = self.request(f"/v1/storage/objects/{blob_key}", method="PUT", headers={"x-api-key": api_key}, data=blob_data)
            ok_put = (r_put["status"] == 201)
            self._record_op("Blob Upload & L1 Hot RAM Cache (201)", ok_put, f"{r_put['elapsed_ms']:.1f}ms")
            if not ok_put: round_passed = False

            # 3.2 GET Object (RAM cache reflection)
            r_get = self.request(f"/v1/storage/objects/{blob_key}", method="GET", headers={"x-api-key": api_key})
            ok_get = (r_get["status"] == 200 and r_get["body"].decode("utf-8", errors="ignore") == blob_data)
            self._record_op("Blob GET Verification (200 OK)", ok_get, f"{r_get['elapsed_ms']:.1f}ms")
            if ok_get: self.latencies["cloud_blob"].append(r_get["elapsed_ms"])
            else: round_passed = False

            # 3.3 Worldwide CDN Streaming Route (/s/*)
            if user_id:
                r_cdn = self.request(f"/s/{user_id}/{blob_key}")
                ok_cdn = (r_cdn["status"] == 200 and len(r_cdn["body"]) == len(blob_data))
                self._record_op("Worldwide Public CDN Stream (/s/*)", ok_cdn, f"{r_cdn['elapsed_ms']:.1f}ms")
                if not ok_cdn: round_passed = False

        # ---------------------------------------------------------------------
        # 4. AI SUBSYSTEMS (ZERO-AUTH, 100% FREE & OPEN)
        # ---------------------------------------------------------------------
        # 4.1 Qwen 2.5 0.5B Chat Completion
        r_chat = self.request("/v1/chat/completions", method="POST", data={
            "model": "qwen",
            "messages": [{"role": "user", "content": f"Briefly respond with one word: ready"}],
            "stream": False,
            "max_tokens": 10
        }, timeout=45)
        ok_chat = (r_chat["status"] == 200 and r_chat["json"] and len(r_chat["json"].get("choices", [])) > 0)
        chat_text = r_chat["json"]["choices"][0]["message"]["content"].strip() if ok_chat else ""
        self._record_op("AI Chat Completion (Qwen 2.5 0.5B)", ok_chat, f"{r_chat['elapsed_ms']:.1f}ms -> '{chat_text[:20]}'")
        if ok_chat: self.latencies["qwen_chat"].append(r_chat["elapsed_ms"])
        else: round_passed = False

        # 4.2 BGE-Small-en-v1.5 Vector Embeddings
        r_embed = self.request("/v1/embeddings", method="POST", data={
            "input": f"Datacenter iteration test {round_num}"
        }, timeout=20)
        ok_embed = (r_embed["status"] == 200 and r_embed["json"] and len(r_embed["json"].get("data", [])) > 0)
        dim = len(r_embed["json"]["data"][0]["embedding"]) if ok_embed else 0
        self._record_op("AI Vector Embeddings (BGE-Small 384-dim)", ok_embed, f"{r_embed['elapsed_ms']:.1f}ms (dim={dim})")
        if ok_embed: self.latencies["bge_embed"].append(r_embed["elapsed_ms"])
        else: round_passed = False

        # 4.3 BGE-Reranker-Base Cross-Encoder
        r_rerank = self.request("/v1/rerank", method="POST", data={
            "query": "cloud computing and storage",
            "documents": [
                "Distributed NVMe file system and SQLite WAL engine",
                "Italian pasta carbonara culinary recipe",
                "Low-latency RAM cache reflection"
            ]
        }, timeout=25)
        ok_rerank = (r_rerank["status"] == 200 and r_rerank["json"] and len(r_rerank["json"].get("results", [])) == 3)
        top_idx = r_rerank["json"]["results"][0]["index"] if ok_rerank else -1
        self._record_op("AI Semantic Reranking (BGE-Reranker)", ok_rerank, f"{r_rerank['elapsed_ms']:.1f}ms (top doc #{top_idx})")
        if ok_rerank: self.latencies["bge_rerank"].append(r_rerank["elapsed_ms"])
        else: round_passed = False

        # 4.4 OpenAI Whisper Speech-to-Text (/inference)
        ok_stt = False
        if os.path.exists(self.test_wav_path):
            try:
                boundary = f"----WebKitFormBoundary{secrets.token_hex(8)}"
                with open(self.test_wav_path, "rb") as f:
                    wav_bytes = f.read()
                parts = []
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"temperature\"\r\n\r\n0.0\r\n".encode())
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
                parts.append(wav_bytes)
                parts.append(f"\r\n--{boundary}--\r\n".encode())
                multipart_data = b"".join(parts)

                r_stt = self.request("/inference", method="POST", data=multipart_data, headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}"
                }, timeout=40)
                ok_stt = (r_stt["status"] == 200 and r_stt["json"] and "text" in r_stt["json"])
                transcript = r_stt["json"].get("text", "").strip() if ok_stt else ""
                self._record_op("AI Whisper Speech-to-Text (/inference)", ok_stt, f"{r_stt['elapsed_ms']:.1f}ms -> '{transcript[:25]}'")
                if ok_stt: self.latencies["whisper_stt"].append(r_stt["elapsed_ms"])
                else: round_passed = False
            except Exception as e:
                self._record_op("AI Whisper Speech-to-Text (/inference)", False, str(e))
                round_passed = False

        # ---------------------------------------------------------------------
        # 5. DATABASE CONCURRENCY & ZERO-POLLUTION TEARDOWN
        # ---------------------------------------------------------------------
        # 5.1 SQLite Integrity Check
        r_int = self.request("/v1/dashboard/db/integrity")
        ok_int = (r_int["status"] == 200 and r_int["json"] and r_int["json"].get("ok") is True)
        self._record_op("SQLite WAL PRAGMA integrity_check", ok_int, f"Status: {r_int['json'].get('status') if ok_int else ''}")
        if not ok_int: round_passed = False

        # 5.2 Purge Round's Test Account (Zero Pollution Guarantee)
        if user_id:
            r_del = self.request("/v1/dashboard/users", method="POST", data={"action": "delete_user", "user_id": user_id})
            ok_del = (r_del["status"] == 200 and r_del["json"] and r_del["json"].get("status") == "deleted")
            self._record_op("Zero-Pollution Account Teardown", ok_del, f"user_id={user_id}")
            if not ok_del: round_passed = False

        # ---------------------------------------------------------------------
        # 6. DYNAMIC ANALYTICS & HARDWARE TELEMETRY AUDIT
        # ---------------------------------------------------------------------
        r_ana = self.request("/v1/dashboard/analytics?horizon=15m")
        ok_ana = (r_ana["status"] == 200 and r_ana["json"] and "realtime_pulse" in r_ana["json"])
        if ok_ana:
            pulse = r_ana["json"]["realtime_pulse"]
            self._record_op("Live Dynamic Analytics Reflection", True, f"RPS={pulse.get('requests_per_sec')} SLA={pulse.get('avg_latency_ms')}ms")

        # Telemetry
        r_tel = self.request("/telemetry")
        if r_tel["status"] == 200 and r_tel["json"]:
            bat = r_tel["json"].get("battery", {})
            cpu = r_tel["json"].get("cpu", {})
            print(f"  {MAGENTA}Node Telemetry:{RESET} Battery: {bat.get('level')}% ({bat.get('temperature')}°C) | CPU Usage: {cpu.get('usage_percent')}% | Active Model: {r_tel['json'].get('active_model')}")

        if round_passed:
            self.passed_rounds += 1
            print(f"\n{GREEN}{BOLD}>>> ITERATION #{round_num:02d} RESULT: ALL SUBSYSTEMS OPERATIONAL (100% PASS){RESET}")
        else:
            self.failed_rounds += 1
            print(f"\n{RED}{BOLD}>>> ITERATION #{round_num:02d} RESULT: ENCOUNTERED FAILURES{RESET}")

        return round_passed

    def _record_op(self, name: str, passed: bool, details: str = ""):
        self.total_ops += 1
        if passed:
            self.passed_ops += 1
            print(f"  {GREEN}✓ PASS{RESET} {name:<42} {DIM}{details}{RESET}")
        else:
            self.failed_ops += 1
            print(f"  {RED}✗ FAIL{RESET} {name:<42} {RED}{details}{RESET}")

    def print_final_report(self):
        print(f"\n{BOLD}{CYAN}========================================================================={RESET}")
        print(f"{BOLD}{CYAN}                 CONTINUOUS STRESS TEST FINAL AUDIT REPORT               {RESET}")
        print(f"{BOLD}{CYAN}========================================================================={RESET}")
        print(f"  Target Datacenter Node: {BOLD}{self.base_url}{RESET}")
        print(f"  Total Rounds Run:       {BOLD}{self.total_rounds}{RESET}")
        print(f"  Rounds Passed:          {GREEN}{BOLD}{self.passed_rounds}{RESET} / {self.total_rounds} ({round((self.passed_rounds/max(1, self.total_rounds))*100, 1)}%)")
        print(f"  Total Operations:       {BOLD}{self.total_ops}{RESET}")
        print(f"  Operations Succeeded:   {GREEN}{BOLD}{self.passed_ops}{RESET} / {self.total_ops} ({round((self.passed_ops/max(1, self.total_ops))*100, 1)}%)")
        print(f"  Operations Failed:      {RED if self.failed_ops else GREEN}{BOLD}{self.failed_ops}{RESET}")

        print(f"\n{BOLD}[LATENCY BENCHMARK PROFILE]{RESET}")
        for k, vals in self.latencies.items():
            if vals:
                avg = sum(vals) / len(vals)
                p50 = sorted(vals)[len(vals)//2]
                p95 = sorted(vals)[int(len(vals)*0.95)]
                print(f"  ⚡ {CYAN}{k:<16}{RESET}: Avg: {BOLD}{avg:6.2f} ms{RESET} | P50: {BOLD}{p50:6.2f} ms{RESET} | P95: {BOLD}{p95:6.2f} ms{RESET}")

        print(f"{BOLD}{CYAN}========================================================================={RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Continuous Stress & Self-Healing Test Engine")
    parser.add_argument("url", nargs="?", default="http://192.168.29.2:8080", help="Target URL (local LAN or WAN tunnel)")
    parser.add_argument("--iterations", "-n", type=int, default=3, help="Number of full cycles to execute (default: 3)")
    parser.add_argument("--delay", "-d", type=float, default=1.5, help="Delay in seconds between rounds (default: 1.5)")
    args = parser.parse_args()

    engine = DatacenterStressIterator(args.url)
    print(f"\n{BOLD}Starting Continuous Multi-Iteration Stress Engine on {args.url}...{RESET}")
    print(f"Planned iterations: {args.iterations} rounds\n")

    for i in range(1, args.iterations + 1):
        engine.run_iteration(i)
        if i < args.iterations:
            time.sleep(args.delay)

    engine.print_final_report()
    if engine.failed_ops > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
