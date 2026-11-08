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
GROQ_MODELS_POOL = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
    "openai/gpt-oss-120b"
]
GROQ_MODEL = GROQ_MODELS_POOL[0]
GROQ_MODEL_FALLBACK = GROQ_MODELS_POOL[1]

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
    "min_p": 0.05,
    "typical_p": 1.0,
    "repeat_penalty": 1.1,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "dry_multiplier": 0.0,
    "mirostat": 0,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,
    "top_n_sigma": -1.0,
    "xtc_probability": 0.0,
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

class WeightMutator:
    """Autonomous Neural Network Weight & Tensor Perturbation Engine."""
    def __init__(self, adapter_path: Path):
        self.adapter_path = adapter_path
        self.adapter_path.parent.mkdir(parents=True, exist_ok=True)
        self.active_mutation: Optional[Dict[str, Any]] = None

    def apply_weight_mutation(self, target_layer: str, rank: int = 2, scale: float = 0.05, delta_type: str = "orthogonal") -> Dict[str, Any]:
        """Synthesizes a low-rank weight perturbation tensor directly into the active LoRA adapter."""
        try:
            import numpy as np
            import gguf

            writer = gguf.GGUFWriter(str(self.adapter_path), "qwen2")
            writer.add_string("general.type", "adapter")
            writer.add_string("adapter.type", "lora")
            writer.add_float32("adapter.lora.alpha", float(max(1.0, rank * 4.0)))

            # Qwen 2.5 0.5B exact layer dimensions:
            # hidden_size = 896, ffn_intermediate = 4864, kv_dim = 128
            in_dim = 896
            out_dim = 896
            if "attn_k" in target_layer or "attn_v" in target_layer:
                out_dim = 128
            elif "ffn_gate" in target_layer or "ffn_up" in target_layer:
                out_dim = 4864
            elif "ffn_down" in target_layer:
                in_dim = 4864
                out_dim = 896

            # GGML memory layout: A has shape (rank, in_dim); B has shape (out_dim, rank)
            if delta_type == "spectral_svd":
                A = (np.linalg.qr(np.random.randn(in_dim, rank))[0].T).astype(np.float32) * float(scale)
                B = (np.linalg.qr(np.random.randn(out_dim, rank))[0]).astype(np.float32) * float(scale)
            elif delta_type == "gaussian_jitter":
                A = (np.random.randn(rank, in_dim) * float(scale)).astype(np.float32)
                B = (np.random.randn(out_dim, rank) * float(scale)).astype(np.float32)
            else:
                A = (np.random.randn(rank, in_dim) * 0.01).astype(np.float32)
                B = (np.random.randn(out_dim, rank) * float(scale)).astype(np.float32)

            tensor_base = target_layer if target_layer.endswith(".weight") else f"{target_layer}.weight"
            writer.add_tensor(f"{tensor_base}.lora_a", A)
            writer.add_tensor(f"{tensor_base}.lora_b", B)

            writer.write_header_to_file()
            writer.write_kv_data_to_file()
            writer.write_tensors_to_file()
            writer.close()

            frobenius = float(np.linalg.norm(B @ A))
            scale_applied = self._post_lora_scale(scale)

            self.active_mutation = {
                "target_layer": target_layer,
                "rank": rank,
                "scale": scale,
                "delta_type": delta_type,
                "frobenius_norm": round(frobenius, 6),
                "adapter_size_bytes": self.adapter_path.stat().st_size if self.adapter_path.exists() else 0,
                "hot_scaled": scale_applied
            }
            return self.active_mutation
        except Exception as e:
            return {"error": str(e), "target_layer": target_layer, "hot_scaled": False}

    def _post_lora_scale(self, scale: float) -> bool:
        for p in [8001, 8080]:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{p}/lora-adapters",
                    data=json.dumps([{"id": 0, "scale": float(scale)}]).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
        return False

    def rollback(self):
        """Immediately zeroes out the LoRA scale in llama-server."""
        self._post_lora_scale(0.0)
        self.active_mutation = None

class QwenExperimenter:
    def __init__(self, on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.on_event = on_event or (lambda e: None)
        self.groq_key = self._load_groq_key()
        self.active_qwen_url = self._detect_qwen_endpoint()
        self.state = self._load_state()
        adapter_candidates = [
            Path("/data/data/com.termux/files/home/adapters/qwen_lora_active.gguf"),
            Path.cwd() / "adapters" / "qwen_lora_active.gguf"
        ]
        chosen_adapter = adapter_candidates[0] if adapter_candidates[0].parent.exists() else adapter_candidates[1]
        self.weight_mutator = WeightMutator(chosen_adapter)

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

    def _call_groq(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.2) -> str:
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
            "User-Agent": "Swades-Qwen-Experimenter/1.0"
        }
        models_to_try = list(GROQ_MODELS_POOL)
        if model and model in models_to_try:
            models_to_try.remove(model)
            models_to_try.insert(0, model)

        for current_model in models_to_try:
            body = {
                "model": current_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024
            }
            req = urllib.request.Request(GROQ_API_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 429):
                    time.sleep(0.5)
                    continue
                raise RuntimeError(f"Groq API Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
            except Exception as e:
                time.sleep(1.0)
                continue
        raise RuntimeError("All models in Groq scientist pool exhausted or rate limited.")

    def _execute_qwen_inference(self, prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        messages = []
        if config.get("system_prompt"):
            messages.append({"role": "system", "content": config["system_prompt"]})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "stream": True,
            "max_tokens": config.get("max_tokens", 64),
            "temperature": config.get("temperature", 0.2),
            "top_p": config.get("top_p", 0.9),
            "top_k": config.get("top_k", 40),
            "min_p": config.get("min_p", 0.05),
            "typical_p": config.get("typical_p", 1.0),
            "repeat_penalty": config.get("repeat_penalty", config.get("repetition_penalty", 1.1)),
            "presence_penalty": config.get("presence_penalty", 0.0),
            "frequency_penalty": config.get("frequency_penalty", 0.0),
        }

        for adv_k in [
            "mirostat", "mirostat_tau", "mirostat_eta",
            "dynatemp_range", "dynatemp_exponent",
            "top_n_sigma", "xtc_probability", "xtc_threshold",
            "dry_multiplier", "dry_base", "dry_allowed_length",
            "logit_bias", "samplers"
        ]:
            if adv_k in config:
                payload[adv_k] = config[adv_k]

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
        prompt_scientist = f"""You are the Lead Deep AI Research Scientist in the Swades Framework.
Target model: Qwen 2.5 0.5B Instruct (running locally on ARM MediaTek Helio G25 CPU via llama.cpp).
Current Parameters: {json.dumps(current_cfg)}
Optimal Parameters Discovered So Far: {json.dumps(optimal_cfg)}
Baseline Performance: {json.dumps(base_metrics)}
Recently Tested and REJECTED Mutations (DO NOT REPEAT THESE): {json.dumps(past_failed)}

Your mission: Formulate a novel, mathematically grounded scientific mutation on the local SLM. 
CRITICAL DIRECTIVE: Do NOT simply tweak temperature, top_k, or top_p. Those have been thoroughly explored and repeatedly cause severe CPU slowdown on ARM NEON. You must actively investigate DIRECT WEIGHT MUTATIONS (Vector 1), SAMPLER ALGEBRA & LOGIT BIASING (Vectors 2 & 3), or ADVANCED PROBABILITY MANIFOLDS (Vector 4).

YOU HAVE UNRESTRICTED ACCESS ACROSS DEEP SCIENTIFIC VECTORS:

VECTOR 1: DIRECT MODEL WEIGHT MUTATIONS & LORA TENSOR PERTURBATION (HIGH PRIORITY)
You have authority to synthesize low-rank weight perturbation matrices (Delta W = B * A) directly modifying the transformer layers of Qwen 2.5 0.5B!
- Target layers: blk.{{0..23}}.attn_q, blk.{{0..23}}.attn_k, blk.{{0..23}}.attn_v, blk.{{0..23}}.attn_output, blk.{{0..23}}.ffn_gate, blk.{{0..23}}.ffn_up, blk.{{0..23}}.ffn_down
- Delta types: "spectral_svd" (singular vector perturbation), "orthogonal" (orthogonal subspace rotation), "gaussian_jitter" (micro-stochastic jitter)
- Scale: -0.15 to +0.15
- Rank: 1, 2, or 4
Example weight mutation in mutated_params:
{{
  "weight_mutation": {{
    "target_layer": "blk.11.attn_q",
    "delta_type": "spectral_svd",
    "rank": 2,
    "scale": 0.04
  }}
}}

VECTOR 2: LOGIT BIASING & VOCABULARY JACOBIAN STEERING
- logit_bias: List of [token_id, bias_weight] (e.g. [[9707, 1.5], [198, -0.8]]). Directly alters pre-softmax logit landscape to steer token emission dynamics.

VECTOR 3: SAMPLER PIPELINE ALGEBRA
- samplers: Custom ordered sequence of sampling filters, e.g. ["penalties", "dry", "min_p", "top_n_sigma", "xtc", "temperature"]. Reordering changes projection on the probability simplex.

VECTOR 4: ENTROPY REGULATION & MANIFOLDS
- min_p (0.01 - 0.25): Truncate candidate logits relative to top token probability.
- typical_p (0.5 - 1.0): Locally typical sampling based on conditional entropy.
- mirostat (0, 1, 2), mirostat_tau (1.0 - 8.0), mirostat_eta (0.01 - 0.5): Dynamic cross-entropy stabilization algorithm.
- top_n_sigma (-1.0 to 3.0): Logit standard deviation thresholding.
- xtc_probability (0.0 - 0.5), xtc_threshold (0.05 - 0.3): Exclude Top Choices.
- dry_multiplier (0.0 - 2.0), dry_base (1.0 - 2.5), dry_allowed_length (1 - 5).

Propose an ambitious, non-trivial hypothesis. Prioritize direct weight tensor perturbations and structural manifold alterations.
You must respond ONLY with a raw JSON object (no markdown fences, no comments) matching:
{{
  "experiment_name": "<Short scientific title>",
  "hypothesis": "<Rigorous mathematical / empirical hypothesis explaining why this mutation alters entropy, logit distribution, weight geometry, or CPU throughput>",
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
                "experiment_name": f"Adaptive SVD Weight Perturbation #{cycle_num}",
                "hypothesis": "Rank-2 SVD perturbation on blk.0.attn_q aligns attention projections for faster token convergence.",
                "mutated_params": {
                    "weight_mutation": {
                        "target_layer": f"blk.{cycle_num % 24}.attn_q",
                        "delta_type": "spectral_svd",
                        "rank": 2,
                        "scale": 0.03
                    }
                }
            }

        exp_name = parsed_proposal.get("experiment_name", f"Experiment #{cycle_num}")
        hypothesis = parsed_proposal.get("hypothesis", "Parameter mutation exploration.")
        mutations = parsed_proposal.get("mutated_params", {})

        candidate_cfg = dict(current_cfg)
        candidate_cfg.update({k: v for k, v in mutations.items() if k != "weight_mutation"})

        # Apply real-time weight mutation if proposed
        active_wm = None
        if "weight_mutation" in mutations and isinstance(mutations["weight_mutation"], dict):
            wm_spec = mutations["weight_mutation"]
            active_wm = self.weight_mutator.apply_weight_mutation(
                target_layer=wm_spec.get("target_layer", f"blk.{cycle_num % 24}.attn_q"),
                rank=int(wm_spec.get("rank", 2)),
                scale=float(wm_spec.get("scale", 0.05)),
                delta_type=str(wm_spec.get("delta_type", "spectral_svd"))
            )
            candidate_cfg["active_weight_mutation"] = active_wm

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
            if active_wm:
                self.state["optimal_weight_mutation"] = active_wm
            self.state["baseline_metrics"] = {
                "avg_latency_ms": results["avg_latency_ms"],
                "avg_tok_per_sec": results["avg_tok_per_sec"],
                "pass_rate_pct": results["pass_rate_pct"]
            }
            self.state["successful_mutations"] += 1
        else:
            if active_wm:
                self.weight_mutator.rollback()

        self.state["current_config"] = dict(candidate_cfg if is_improvement else optimal_cfg)
        self.state["total_cycles"] = cycle_num

        exp_record = {
            "cycle": cycle_num,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "name": exp_name,
            "hypothesis": hypothesis,
            "mutations": mutations,
            "weight_mutation": active_wm,
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
        wm_block = ""
        if record.get("weight_mutation"):
            wm = record["weight_mutation"]
            wm_block = f"""
[WEIGHT TENSOR DELTA]
  - Target Layer : {wm.get('target_layer', 'unknown')}
  - Delta Method : {wm.get('delta_type', 'orthogonal')} (Rank {wm.get('rank', 2)}, scale {wm.get('scale', 0.05)})
  - Frobenius ||W||: {wm.get('frobenius_norm', 0.0)}
  - Hot-Scaled   : {wm.get('hot_scaled', False)} (Size: {wm.get('adapter_size_bytes', 0)} bytes)"""

        log_entry = f"""
================================================================================
[EXPERIMENT #{record['cycle']:03d}] {record['timestamp']} | {record['name']}
================================================================================
[HYPOTHESIS] {record['hypothesis']}
[MUTATION]   {json.dumps(record['mutations'])}{wm_block}
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
