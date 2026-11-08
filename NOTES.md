# SWADES UNIFICATION & NATIVE HARNESS ARCHITECTURE

## 1. Single Canonical Frontend
- Consolidated all disparate pages (`/ide`, `/swades_ide`, `/ide.html`, `/swades_ide.html`) onto a single canonical interface: `swades.html` at `/swades`.
- Cloudflare Pages middleware (`functions/_middleware.js`) and Phone Gateway router (`gateway.py`) enforce HTTP 302 redirects from `/ide`, `/swades_ide`, `/swades-ide` to `/swades`.
- Terminated and eliminated redundant secondary server (`swades_server.py` on port 8088).

## 2. Authentic Native Swades ReAct Backend
- Displaced legacy node/alpine worker invocation in `gateway.py` with pure sovereign Python execution using `~/Swades/main.py`.
- Architecture:
  - Ephemeral sandbox management via `SwadesGitManager`: clones repository, provisions `swades/<job_id>` branch, and tracks visual git diffs.
  - Harness instantiation: Loads `swades_core.Config.load(llm=True, root=workspace_path)` with Groq provider (`openai/gpt-oss-120b`).
  - Real-time SSE streaming: `StreamingSwadesReAct` subclasses `swades_core.ReAct` to pipe `_say` (reasoning thoughts), `_plan` (delta & ordered steps), `_log` (tool execution & tool results), visual git diffs, and critic review verdicts directly to `_job_manager.append_log()`.
  - Frontend delivery: Events stream over `/v1/agent/stream/<job_id>` and persist in SQLite `~/.swades_jobs/swades.db` for instantaneous polling fallback.

## 3. Verified Live Endpoints
- Canonical URL: `https://phone-whisper-server.pages.dev/swades` (HTTP 200)
- Task Submission: `POST https://phone-whisper-server.pages.dev/v1/agent/submit`
- Live Stream: `GET https://phone-whisper-server.pages.dev/v1/agent/stream/<job_id>`
- Task History: `GET https://phone-whisper-server.pages.dev/v1/agent/tasks?user=Electroiscoding`
- Remote Studio Frame: `GET https://phone-whisper-server.pages.dev/v1/screen/frame`

## 4. Qwen Autonomous Closed-Loop Experimentation Engine
- **Engine Architecture**:
  - `qwen_experimenter.py`: Sovereign closed-loop scientist engine running as a native background daemon on physical phone server (`192.168.29.2:8080`, PID `24942`).
  - Scientist Model: Groq LPU (`qwen/qwen3.8-27b`) formulates hypotheses, proposes mutations, evaluates benchmark deltas, and writes authoritative scientific conclusions.
  - Experimental Subject: Local Qwen 2.5 0.5B Instruct GGUF (`qwen2.5-0.5b-instruct-q4_k_m.gguf`) served on `127.0.0.1:8001` via `llama-server` on ARM NEON CPU.
  - Benchmark Battery: 3 quantitative evaluations per experiment cycle:
    1. Strict JSON Extraction (Structure & syntax fidelity)
    2. 1-Sentence Science Reasoning (Factual density & concise deduction)
    3. Python Lambda Synthesis (Executable code generation)
  - Rollback / Commit Gate: Strict regression threshold. Any mutation degrading speed by >15% or latency by >20% is rolled back immediately (`REJECTED_ROLLBACK`).
  - Persistence: Every move, hypothesis, raw token output, benchmark score, and conclusion is appended synchronously to `/data/data/com.termux/files/home/qwen_experiments.log` and serialized in `qwen_state.json`.
- **Pure Monochrome OLED UX (Nir Eyal Hook Model)**:
  - Canonical Public Dashboard: `https://phone-whisper-server.pages.dev/qwen` (< 18 KB, pure `#000000` black and `#FFFFFF` white, zero external libraries).
  - External Trigger: Live indicator & ping frequency.
  - Action: Manual "Trigger Mutation Cycle" button / Spacebar shortcut.
  - Variable Reward: Quantitative deltas, benchmark throughput, and scientific verdicts.
  - Investment: Scrollable log viewer and raw `.log` exporter.
- **Endpoints**:
  - Dashboard: `GET https://phone-whisper-server.pages.dev/qwen`
  - Experiments & Biodata State: `GET https://phone-whisper-server.pages.dev/v1/qwen/experiments`
  - Raw Audit Log: `GET https://phone-whisper-server.pages.dev/v1/qwen/logs`
  - Manual Trigger: `POST https://phone-whisper-server.pages.dev/v1/qwen/experiment/trigger`

