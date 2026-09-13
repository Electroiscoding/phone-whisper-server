#!/usr/bin/env python3
"""
=============================================================================
  SWADES HYPER-DATACENTER CONTINUOUS MULTI-ITERATION STRESS & TEST ENGINE 5.0
  Tests all modalities, Zstandard Level 1/3 dual-tier compression, Piper TTS,
  PBKDF2 accounts, scoped keys, multi-tenancy, L1 RAM engine, SQLite WAL,
  and ACC thermal telemetry in continuous high-throughput iterations.
=============================================================================
"""

import sys
import os
import time
import json
import base64
import secrets
import wave
import struct
import math
import argparse
import urllib.request
import urllib.error

# ANSI Styling (Zero Emojis)
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
            "zstd_compress": [],
            "zstd_decompress": [],
            "piper_tts": [],
            "qwen_chat": [],
            "bge_embed": [],
            "bge_rerank": [],
            "acc_telemetry": []
        }

    def request(self, path: str, method="GET", data=None, headers=None, timeout=60):
        url = f"{self.base_url}{path}"
        req_headers = {"User-Agent": "SwadesStressEngine/5.0", "X-Client-IP": "10.0.99.1"}
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
        r_reg = self.request("/v1/storage/auth/register", method="POST", data={"username": uname, "password": pwd})
        ok_reg = (r_reg["status"] == 201 and r_reg["json"] and r_reg["json"].get("success"))
        self._record_op("Account Registration (201 Created)", ok_reg, f"{r_reg['elapsed_ms']:.1f}ms")
        if not ok_reg: round_passed = False

        if ok_reg:
            user_id = r_reg["json"]["user_id"]
            api_key = r_reg["json"]["api_key"]

        r_dup = self.request("/v1/storage/auth/register", method="POST", data={"username": uname, "password": "any"})
        ok_dup = (r_dup["status"] == 400)
        self._record_op("Duplicate Account Rejection (400)", ok_dup, f"HTTP {r_dup['status']}")
        if not ok_dup: round_passed = False

        r_login = self.request("/v1/storage/auth/login", method="POST", data={"username": uname, "password": pwd})
        ok_login = (r_login["status"] == 200 and r_login["json"] and r_login["json"].get("success"))
        self._record_op("PBKDF2 Password Login (200 OK)", ok_login, f"{r_login['elapsed_ms']:.1f}ms")
        if ok_login: self.latencies["account_auth"].append(r_login["elapsed_ms"])
        else: round_passed = False

        # ---------------------------------------------------------------------
        # 2. SCOPED KEYS & GRANULAR ACCESS CONTROL
        # ---------------------------------------------------------------------
        if api_key:
            r_ro = self.request("/v1/storage/auth/keys", method="POST", headers={"x-api-key": api_key},
                                data={"name": f"RO_Key_{suffix}", "restrictions": "read_only"})
            ok_ro = (r_ro["status"] == 201 and r_ro["json"] and r_ro["json"].get("api_key"))
            ro_key = r_ro["json"]["api_key"] if ok_ro else ""
            self._record_op("Scoped Key Generation ('read_only')", ok_ro, f"key_id={r_ro['json'].get('key_id') if ok_ro else ''}")
            if not ok_ro: round_passed = False

            r_ro_put = self.request(f"/v1/storage/objects/test_{suffix}.txt", method="PUT", headers={"x-api-key": ro_key}, data="test")
            ok_ro_block = (r_ro_put["status"] == 403)
            self._record_op("Scoped Read-Only Blocks Write (403)", ok_ro_block, f"HTTP {r_ro_put['status']}")
            if not ok_ro_block: round_passed = False

        # ---------------------------------------------------------------------
        # 3. CLOUD STORAGE ENGINE & L1 RAM REFLECTION (Level 3 Vault Storage)
        # ---------------------------------------------------------------------
        if api_key:
            blob_data = f"Swades Sovereign Inverter-Protected Vault Blob [{round_num} : {suffix}] " * 16
            blob_key = f"datasets/iter_{round_num}_{suffix}.txt"

            r_put = self.request(f"/v1/storage/objects/{blob_key}", method="PUT", headers={"x-api-key": api_key}, data=blob_data)
            ok_put = (r_put["status"] == 201)
            self._record_op("Blob Upload (Level 3 Vault Persistence)", ok_put, f"{r_put['elapsed_ms']:.1f}ms")
            if not ok_put: round_passed = False

            r_get = self.request(f"/v1/storage/objects/{blob_key}", method="GET", headers={"x-api-key": api_key})
            recovered_text = r_get["body"].decode("utf-8", errors="ignore")
            ok_get = (r_get["status"] == 200 and recovered_text == blob_data)
            self._record_op("Blob GET Lossless Recovery (200 OK)", ok_get, f"{r_get['elapsed_ms']:.1f}ms")
            if ok_get: self.latencies["cloud_blob"].append(r_get["elapsed_ms"])
            else: round_passed = False

            if user_id:
                r_cdn = self.request(f"/s/{user_id}/{blob_key}")
                ok_cdn = (r_cdn["status"] == 200 and len(r_cdn["body"]) == len(blob_data))
                self._record_op("Worldwide Public CDN Stream (/s/*)", ok_cdn, f"{r_cdn['elapsed_ms']:.1f}ms")
                if not ok_cdn: round_passed = False

        # ---------------------------------------------------------------------
        # 4. ZSTANDARD (zstd v1.5.7) HARDWARE DUAL-TIER ENGINE
        # ---------------------------------------------------------------------
        # 4.1 Level 1 Developer API Compression
        sample_payload = {"tenant": uname, "metric": "uptime_1000pct", "iteration": round_num, "buffer": "X" * 512}
        r_comp = self.request("/v1/compress", method="POST", data=sample_payload)
        ok_comp = (r_comp["status"] == 200 and r_comp["json"] and r_comp["json"].get("status") == "success")
        c_b64 = r_comp["json"].get("compressed_base64") if ok_comp else None
        ratio = r_comp["json"].get("compression_ratio", 1.0) if ok_comp else 1.0
        self._record_op("Zstd Level 1 (-1 -T4) API Compression", ok_comp, f"{r_comp['elapsed_ms']:.2f}ms (Ratio: {ratio}x)")
        if ok_comp: self.latencies["zstd_compress"].append(r_comp["elapsed_ms"])
        else: round_passed = False

        # 4.2 Lossless Microsecond Decompression
        if c_b64:
            r_decomp = self.request("/v1/decompress", method="POST", data={"data": c_b64, "as_text": True})
            ok_decomp = (r_decomp["status"] == 200 and r_decomp["json"] and r_decomp["json"].get("status") == "success")
            self._record_op("Zstd Lossless Decompression (/v1/decompress)", ok_decomp, f"{r_decomp['elapsed_ms']:.2f}ms")
            if ok_decomp: self.latencies["zstd_decompress"].append(r_decomp["elapsed_ms"])
            else: round_passed = False

        # 4.3 Native Image Compression & Decompression
        raw_rgb = b"\xFF\x00\x00\x00\xFF\x00\x00\x00\xFF\x80\x80\x80" * 256 # 3072 bytes
        r_img_c = self.request("/v1/images/compress", method="POST", data=raw_rgb, headers={"Content-Type": "application/octet-stream"})
        ok_img_c = (r_img_c["status"] == 200 and len(r_img_c["body"]) > 0 and len(r_img_c["body"]) < len(raw_rgb))
        self._record_op("Native Image Zstd Stream Compression", ok_img_c, f"{r_img_c['elapsed_ms']:.2f}ms (ratio: {len(raw_rgb)/max(1, len(r_img_c['body'])):.1f}x)")
        if not ok_img_c: round_passed = False

        if ok_img_c:
            r_img_d = self.request("/v1/images/decompress", method="POST", data=r_img_c["body"], headers={"Content-Type": "application/octet-stream"})
            ok_img_d = (r_img_d["status"] == 200 and r_img_d["body"] == raw_rgb)
            self._record_op("Native Image Zstd Stream Decompression", ok_img_d, f"{r_img_d['elapsed_ms']:.2f}ms")
            if not ok_img_d: round_passed = False

        # ---------------------------------------------------------------------
        # 5. PIPER VITS NEURAL TTS (/v1/audio/speech)
        # ---------------------------------------------------------------------
        r_tts = self.request("/v1/audio/speech", method="POST", data={
            "input": f"Datacenter node operational round {round_num}",
            "voice": "amy",
            "response_format": "wav"
        }, timeout=30)
        ok_tts = (r_tts["status"] == 200 and len(r_tts["body"]) > 1000 and r_tts["body"][:4] == b"RIFF")
        self._record_op("Piper VITS Neural TTS Synthesis", ok_tts, f"{r_tts['elapsed_ms']:.1f}ms (WAV: {len(r_tts['body'])} bytes)")
        if ok_tts: self.latencies["piper_tts"].append(r_tts["elapsed_ms"])
        else: round_passed = False

        # ---------------------------------------------------------------------
        # 6. AI INFERENCE SUBSYSTEMS (Zero-Auth / Free)
        # ---------------------------------------------------------------------
        # 6.1 Qwen 2.5 0.5B Chat Completion
        r_chat = self.request("/v1/chat/completions", method="POST", data={
            "model": "qwen",
            "messages": [{"role": "user", "content": "Respond with one word: online"}],
            "stream": False,
            "max_tokens": 10
        }, timeout=45)
        ok_chat = (r_chat["status"] == 200 and r_chat["json"] and len(r_chat["json"].get("choices", [])) > 0)
        chat_text = r_chat["json"]["choices"][0]["message"]["content"].strip() if ok_chat else ""
        self._record_op("AI Chat Completion (Qwen 2.5 0.5B)", ok_chat, f"{r_chat['elapsed_ms']:.1f}ms -> '{chat_text[:20]}'")
        if ok_chat: self.latencies["qwen_chat"].append(r_chat["elapsed_ms"])
        else: round_passed = False

        # 6.2 BGE-Small Vector Embeddings
        r_embed = self.request("/v1/embeddings", method="POST", data={
            "input": f"Datacenter iteration test {round_num}"
        }, timeout=20)
        ok_embed = (r_embed["status"] == 200 and r_embed["json"] and len(r_embed["json"].get("data", [])) > 0)
        dim = len(r_embed["json"]["data"][0]["embedding"]) if ok_embed else 0
        self._record_op("AI Vector Embeddings (BGE-Small 384-dim)", ok_embed, f"{r_embed['elapsed_ms']:.1f}ms (dim={dim})")
        if ok_embed: self.latencies["bge_embed"].append(r_embed["elapsed_ms"])
        else: round_passed = False

        # 6.3 BGE-Reranker-Base Cross-Encoder
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

        # ---------------------------------------------------------------------
        # 7. ADVANCED CHARGING CONTROLLER (ACC) & HARDWARE TELEMETRY
        # ---------------------------------------------------------------------
        r_acc = self.request("/v1/acc/info")
        ok_acc = (r_acc["status"] == 200 and r_acc["json"] and r_acc["json"].get("status") == "success")
        acc_info = r_acc["json"].get("telemetry", {}) if ok_acc else {}
        self._record_op("ACC Battery Guardian Telemetry", ok_acc, f"Level: {acc_info.get('level')}% | Temp: {acc_info.get('temperature_c')}C | State: {acc_info.get('state')}")
        if ok_acc: self.latencies["acc_telemetry"].append(r_acc["elapsed_ms"])
        else: round_passed = False

        # ---------------------------------------------------------------------
        # 8. DATABASE CONCURRENCY & ZERO-POLLUTION TEARDOWN
        # ---------------------------------------------------------------------
        r_int = self.request("/v1/dashboard/db/integrity")
        ok_int = (r_int["status"] == 200 and r_int["json"] and r_int["json"].get("ok") is True)
        self._record_op("SQLite WAL PRAGMA integrity_check", ok_int, f"Status: {r_int['json'].get('status') if ok_int else ''}")
        if not ok_int: round_passed = False

        if user_id:
            r_del = self.request("/v1/dashboard/users", method="POST", data={"action": "delete_user", "user_id": user_id})
            ok_del = (r_del["status"] == 200 and r_del["json"] and r_del["json"].get("status") == "deleted")
            self._record_op("Zero-Pollution Account Teardown", ok_del, f"user_id={user_id}")
            if not ok_del: round_passed = False

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
            print(f"  {GREEN}[PASS]{RESET} {name:<44} {DIM}{details}{RESET}")
        else:
            self.failed_ops += 1
            print(f"  {RED}[FAIL]{RESET} {name:<44} {RED}{details}{RESET}")

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
                print(f"  [*] {CYAN}{k:<18}{RESET}: Avg: {BOLD}{avg:6.2f} ms{RESET} | P50: {BOLD}{p50:6.2f} ms{RESET} | P95: {BOLD}{p95:6.2f} ms{RESET}")

        print(f"{BOLD}{CYAN}========================================================================={RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Continuous Stress & Self-Healing Test Engine")
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8080", help="Target URL (default: http://127.0.0.1:8080)")
    parser.add_argument("--iterations", "-n", type=int, default=3, help="Number of full cycles to execute (default: 3)")
    parser.add_argument("--delay", "-d", type=float, default=1.0, help="Delay in seconds between rounds (default: 1.0)")
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
