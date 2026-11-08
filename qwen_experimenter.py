import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "qwen_experiments.log"
STATE_FILE = BASE_DIR / "qwen_state.json"
GROQ_KEY_FILE = Path.home() / ".groq_key"

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_MODEL_FALLBACK = "openai/gpt-oss-120b"

LOCAL_QWEN_URLS = [
    "http://192.168.29.2:8080/v1/chat/completions",
    "http://127.0.0.1:8080/v1/chat/completions"
]

BENCHMARK_SUITE = [
    {
        "id": "json_strict",
        "name": "Strict JSON Extraction",
        "prompt": "Extract valid JSON only: Name is Nova, Score is 98. Output JSON: {\"name\": str, \"score\": int}",
        "validator": lambda text: ('"name"' in text and '"score"' in text and "98" in text)
    },
    {
        "id": "one_sentence_reasoning",
        "name": "1-Sentence Science Reasoning",
        "prompt": "Explain why the sky appears blue in exactly one sentence.",
        "validator": lambda text: (len(text.strip().split("\n")) <= 2 and len(text.strip()) > 15)
    },
    {
        "id": "code_lambda",
        "name": "Python Lambda Synthesis",
        "prompt": "Write a single-line Python lambda function to compute the square of a number. Code only.",
        "validator": lambda text: ("lambda" in text and ("**" in text or "*" in text))
    }
]

DEFAULT_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 40,
    "repetition_penalty": 1.1,
    "max_tokens": 64,
    "system_prompt": "You are a concise, precise AI assistant. Output only accurate answers with zero fluff."
}

MODEL_BIODATA = {
    "name": "Qwen 2.5 0.5B Instruct",
    "architecture": "qwen2",
    "parameters": "490M (0.49 Billion)",
    "quantization": "Q4_K_M (4-bit medium GGUF)",
    "context_window": 32768,
    "active_context_limit": 2048,
    "engine": "llama.cpp via Termux ARM NEON",
    "device": "Xiaomi Redmi 9i (MediaTek Helio G25, 8x Cortex-A53, 4GB RAM)",
    "runtime_governor": "dynamic_elastic_jit"
}

class QwenExperimenter:
    def __init__(self, on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.on_event = on_event or (lambda e: None)
        self.groq_key = self._load_groq_key()
        self.active_qwen_url = self._detect_qwen_endpoint()
        self.state = self._load_state()

    def _load_groq_key(self) -> str:
        key = os.environ.get("GROQ_API_KEY")
        if key:
            return key.strip()
        if GROQ_KEY_FILE.exists():
            return GROQ_KEY_FILE.read_text(encoding="utf-8").strip()
        candidates = [
            Path.home() / "groqkey.txt",
            Path("/data/data/com.termux/files/home/.groq_key")
        ]
        for c in candidates:
            if c.exists():
                return c.read_text(encoding="utf-8").strip()
        raise ValueError("Groq API key not found in ~/.groq_key or GROQ_API_KEY env.")

    def _detect_qwen_endpoint(self) -> str:
        for url in LOCAL_QWEN_URLS:
            try:
                base = url.replace("/v1/chat/completions", "/health")
                req = urllib.request.Request(base, headers={"User-Agent": "Swades-Qwen-Lab/1.0"})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return url
            except Exception:
                pass
        return LOCAL_QWEN_URLS[0]

    def _load_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        initial_state = {
            "model_biodata": MODEL_BIODATA,
            "total_cycles": 0,
            "successful_mutations": 0,
            "optimal_config": dict(DEFAULT_CONFIG),
            "current_config": dict(DEFAULT_CONFIG),
            "baseline_metrics": {
                "avg_latency_ms": 1100.0,
                "avg_tok_per_sec": 12.5,
                "pass_rate_pct": 100.0
            },
            "recent_experiments": []
        }
        self._save_state(initial_state)
        return initial_state

    def _save_state(self, state: Dict[str, Any]):
        state["daemon_status"] = {
            "active": getattr(self, "is_daemon", True),
            "interval_sec": getattr(self, "daemon_interval", 60),
            "pid": os.getpid(),
            "last_cycle_timestamp": time.time()
        }
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _emit(self, event_type: str, data: Dict[str, Any]):
        payload = {"type": event_type, "timestamp": time.time(), **data}
        self.on_event(payload)

    def _call_groq(self, messages: List[Dict[str, str]], model: str = GROQ_MODEL, temperature: float = 0.2) -> str:
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
            "User-Agent": "Swades-Qwen-Experimenter/1.0"
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }
        for attempt in range(3):
            req = urllib.request.Request(GROQ_API_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code == 403 and model != GROQ_MODEL_FALLBACK:
                    model = GROQ_MODEL_FALLBACK
                    body["model"] = GROQ_MODEL_FALLBACK
                    continue
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Groq API Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Groq connection error: {e}")
        return ""

    def _execute_qwen_inference(self, prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        messages = []
        if config.get("system_prompt"):
            messages.append({"role": "system", "content": config["system_prompt"]})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": config.get("temperature", 0.2),
            "top_p": config.get("top_p", 0.9),
            "max_tokens": config.get("max_tokens", 64)
        }

        req = urllib.request.Request(
            self.active_qwen_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Swades-Benchmark/1.0"}
        )

        t_start = time.perf_counter()
        tokens = []
        with urllib.request.urlopen(req, timeout=45) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            tokens.append(delta)
                    except Exception:
                        pass
                elif line == "data: [DONE]":
                    break

        elapsed = max(0.001, time.perf_counter() - t_start)
        full_text = "".join(tokens)
        tok_count = max(1, len(tokens))
        tok_per_sec = round(tok_count / elapsed, 2)

        return {
            "text": full_text,
            "elapsed_ms": round(elapsed * 1000, 2),
            "tok_count": tok_count,
            "tok_per_sec": tok_per_sec
        }

    def run_benchmark(self, config: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        passed_count = 0
        total_latency = 0.0
        total_tokens = 0

        for test in BENCHMARK_SUITE:
            inf = self._execute_qwen_inference(test["prompt"], config)
            passed = bool(test["validator"](inf["text"]))
            if passed:
                passed_count += 1
            total_latency += inf["elapsed_ms"]
            total_tokens += inf["tok_count"]

            results.append({
                "id": test["id"],
                "name": test["name"],
                "passed": passed,
                "latency_ms": inf["elapsed_ms"],
                "tok_count": inf["tok_count"],
                "tok_per_sec": inf["tok_per_sec"],
                "output_sample": inf["text"].strip()[:100]
            })

        n = len(BENCHMARK_SUITE)
        avg_latency = round(total_latency / max(1, n), 2)
        total_dur_s = max(0.001, total_latency / 1000.0)
        overall_tok_per_sec = round(total_tokens / total_dur_s, 2)
        pass_rate = round((passed_count / max(1, n)) * 100, 1)

        return {
            "pass_rate_pct": pass_rate,
            "avg_latency_ms": avg_latency,
            "avg_tok_per_sec": overall_tok_per_sec,
            "tests": results
        }

    def run_experiment_cycle(self) -> Dict[str, Any]:
        cycle_num = self.state["total_cycles"] + 1
        self._emit("cycle_start", {"cycle": cycle_num})

        current_cfg = self.state.get("current_config", dict(DEFAULT_CONFIG))
        optimal_cfg = self.state.get("optimal_config", dict(DEFAULT_CONFIG))
        base_metrics = self.state.get("baseline_metrics", {})

        past_failed = [r.get("mutations") for r in self.state.get("recent_experiments", [])[:6] if r.get("verdict") == "REJECTED_ROLLBACK"]

        # Step 1: Groq AI synthesizes mutation hypothesis
        prompt_scientist = f"""You are the Lead AI Optimization Scientist in the Swades Framework.
Target model: Qwen 2.5 0.5B Instruct (running locally on ARM MediaTek Helio G25).
Current Parameters: {json.dumps(current_cfg)}
Optimal Parameters Discovered So Far: {json.dumps(optimal_cfg)}
Baseline Performance: {json.dumps(base_metrics)}
Recently Tested and REJECTED Mutations (DO NOT REPEAT THESE): {json.dumps(past_failed)}

Your mission: Formulate a novel mutation targeting a parameter NOT recently rejected.
Available parameter space:
- repetition_penalty: 1.0 to 1.35 (e.g. 1.05, 1.15)
- top_p: 0.6 to 0.98 (e.g. 0.75, 0.85, 0.95)
- temperature: 0.1 to 0.8 (e.g. 0.15, 0.35, 0.5)
- max_tokens: 32 to 96 (e.g. 48, 64)
- system_prompt: concise instructions targeting zero hallucinations.

You must respond ONLY with a raw JSON object (no markdown fences, no comments) matching:
{{
  "experiment_name": "<Short title>",
  "hypothesis": "<1-2 sentence theoretical justification>",
  "mutated_params": {{
    "<param_name>": <value>
  }}
}}"""

        scientist_resp = self._call_groq([{"role": "user", "content": prompt_scientist}], temperature=0.7)
        try:
            clean_json = scientist_resp.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed_proposal = json.loads(clean_json)
        except Exception:
            parsed_proposal = {
                "experiment_name": f"Adaptive Temperature Shift #{cycle_num}",
                "hypothesis": "Shifting temperature closer to greedy limit reduces sampling overhead on ARM CPU.",
                "mutated_params": {"temperature": max(0.05, round(current_cfg["temperature"] * 0.85, 2))}
            }

        exp_name = parsed_proposal.get("experiment_name", f"Experiment #{cycle_num}")
        hypothesis = parsed_proposal.get("hypothesis", "Parameter mutation exploration.")
        mutations = parsed_proposal.get("mutated_params", {})

        candidate_cfg = dict(current_cfg)
        candidate_cfg.update(mutations)

        self._emit("hypothesis", {"cycle": cycle_num, "name": exp_name, "hypothesis": hypothesis, "mutations": mutations})

        # Step 2: Execute benchmark suite on local Qwen
        self._emit("benchmark_start", {"cycle": cycle_num, "config": candidate_cfg})
        results = self.run_benchmark(candidate_cfg)
        self._emit("benchmark_done", {"cycle": cycle_num, "metrics": results})

        # Step 3: Compute deltas vs baseline
        d_latency = round(results["avg_latency_ms"] - base_metrics.get("avg_latency_ms", 1100.0), 2)
        d_speed = round(results["avg_tok_per_sec"] - base_metrics.get("avg_tok_per_sec", 12.5), 2)
        d_pass = round(results["pass_rate_pct"] - base_metrics.get("pass_rate_pct", 100.0), 1)

        # Step 4: Groq synthesizes definitive conclusion
        prompt_evaluator = f"""You are the Evaluation Scientist in Swades.
Experiment: {exp_name}
Hypothesis: {hypothesis}
Mutations Tested: {json.dumps(mutations)}
Test Results:
- Pass Rate: {results['pass_rate_pct']}% (Delta: {d_pass:+.1f}%)
- Mean Latency: {results['avg_latency_ms']}ms (Delta: {d_latency:+.1f}ms)
- Mean Generation Speed: {results['avg_tok_per_sec']} tok/s (Delta: {d_speed:+.2f} tok/s)

Deliver an authoritative 2-sentence conclusion stating whether the hypothesis was confirmed or rejected, and if the mutation should be kept."""

        conclusion = self._call_groq([{"role": "user", "content": prompt_evaluator}], temperature=0.1).strip()

        # Step 5: Acceptance Gate (Nir Eyal Variable Reward & State Update)
        is_improvement = (results["pass_rate_pct"] >= 100.0) and (d_latency < 0 or d_speed > 0)
        action_verdict = "COMMITTED_OPTIMAL" if is_improvement else "REJECTED_ROLLBACK"

        if is_improvement:
            self.state["optimal_config"] = dict(candidate_cfg)
            self.state["baseline_metrics"] = {
                "avg_latency_ms": results["avg_latency_ms"],
                "avg_tok_per_sec": results["avg_tok_per_sec"],
                "pass_rate_pct": results["pass_rate_pct"]
            }
            self.state["successful_mutations"] += 1

        self.state["current_config"] = dict(candidate_cfg if is_improvement else optimal_cfg)
        self.state["total_cycles"] = cycle_num

        exp_record = {
            "cycle": cycle_num,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "name": exp_name,
            "hypothesis": hypothesis,
            "mutations": mutations,
            "metrics": {
                "pass_rate_pct": results["pass_rate_pct"],
                "avg_latency_ms": results["avg_latency_ms"],
                "avg_tok_per_sec": results["avg_tok_per_sec"],
                "delta_latency_ms": d_latency,
                "delta_speed_tok_s": d_speed
            },
            "conclusion": conclusion,
            "verdict": action_verdict
        }

        self.state["recent_experiments"].insert(0, exp_record)
        self.state["recent_experiments"] = self.state["recent_experiments"][:25]
        self._save_state(self.state)

        # Step 6: Append to persistent qwen_experiments.log
        self._append_to_log(exp_record, results["tests"])

        self._emit("cycle_complete", {"cycle": cycle_num, "record": exp_record})
        return exp_record

    def _append_to_log(self, record: Dict[str, Any], test_details: List[Dict[str, Any]]):
        log_entry = f"""
================================================================================
[EXPERIMENT #{record['cycle']:03d}] {record['timestamp']} | {record['name']}
================================================================================
[HYPOTHESIS] {record['hypothesis']}
[MUTATION]   {json.dumps(record['mutations'])}
[BENCHMARK]
  - Pass Rate : {record['metrics']['pass_rate_pct']}%
  - Latency   : {record['metrics']['avg_latency_ms']} ms ({record['metrics']['delta_latency_ms']:+.2f} ms)
  - Speed     : {record['metrics']['avg_tok_per_sec']} tok/s ({record['metrics']['delta_speed_tok_s']:+.2f} tok/s)
[TEST SUITE]"""
        for t in test_details:
            mark = "PASS" if t["passed"] else "FAIL"
            log_entry += f"\n  * [{mark}] {t['name']:28s} | {t['latency_ms']:7.1f}ms | {t['tok_per_sec']:5.1f} tok/s | Output: {t['output_sample'][:40]}..."

        log_entry += f"""
[CONCLUSION] {record['conclusion']}
[VERDICT]    {record['verdict']}
--------------------------------------------------------------------------------
"""
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Qwen Experimenter Engine")
    parser.add_argument("--cycles", type=int, default=1, help="Number of experiment cycles to execute")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background daemon loop")
    parser.add_argument("--interval", type=int, default=15, help="Interval in seconds between daemon cycles")
    args = parser.parse_args()

    experimenter = QwenExperimenter()
    print(f"[*] Autonomous Qwen Experimenter initialized. Endpoint: {experimenter.active_qwen_url}")
    print(f"[*] Log file: {LOG_FILE}")

    if args.daemon:
        experimenter.is_daemon = True
        experimenter.daemon_interval = args.interval
        print(f"[*] Entering daemon mode (Interval: {args.interval}s)...")
        while True:
            try:
                rec = experimenter.run_experiment_cycle()
                print(f"[CYCLE #{rec['cycle']:03d}] {rec['verdict']} | Latency: {rec['metrics']['avg_latency_ms']}ms | Speed: {rec['metrics']['avg_tok_per_sec']} tok/s")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n[+] Daemon stopped cleanly.")
                break
            except Exception as e:
                print(f"[!] Cycle error: {e}")
                time.sleep(10)
    else:
        for c in range(args.cycles):
            print(f"[*] Executing Experiment Cycle {c + 1}/{args.cycles}...")
            rec = experimenter.run_experiment_cycle()
            print(f"[CYCLE #{rec['cycle']:03d}] {rec['verdict']} | Latency: {rec['metrics']['avg_latency_ms']}ms | Speed: {rec['metrics']['avg_tok_per_sec']} tok/s")
            print(f"    Conclusion: {rec['conclusion']}")

if __name__ == "__main__":
    main()
