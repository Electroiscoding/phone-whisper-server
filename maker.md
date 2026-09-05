# Sovereign Phone AI Datacenter — Agent Connection Directive (`maker.md`)
**Document ID**: `PROTOCOL-DIRECTIVE-v3.2`  
**Classification**: AI Agent & Autonomous System Native Specification  
**Canonical Spec URI**: `https://phone-whisper-server.pages.dev/maker.md`  
**Target Hardware**: Xiaomi Redmi 9i (MediaTek Helio G25, 8x Cortex-A53 @ 2.0GHz, 4GB LPDDR4X, 64GB eMMC 5.1)  
**Kernel & OS**: Linux 4.19 (Android 10) on Termux 0.118 + Alpine Linux 3.20 (PRoot)  

---

## 1. Executive Protocol Summary for Autonomous Agents

This document is an exhaustive, machine-actionable directive designed for autonomous AI coding agents (Antigravity, Cursor, Windsurf, Claude, GPT-4, Devin, AutoGPT, LangChain, LlamaIndex).

You are connecting to a **physical micro-datacenter running directly on an Android smartphone**. The node hosts quantized neural network inference engines (`whisper.cpp`, `llama.cpp`, `piper-tts`, `bge-embed`), an asynchronous Python multi-modal gateway, an L1 microsecond reflection cache, a resilient SQLite database, a multi-tier storage pool manager, and an autonomous containerized coding agent engine (`Swades-Agent`).

```
                    ┌─────────────────────────────────────────────────────────┐
                    │        Cloudflare Edge Gateway (Global 330+ PoPs)       │
                    │         https://phone-whisper-server.pages.dev          │
                    └───────────────┬─────────────────────────┬───────────────┘
                                    │ Failover                │ Primary Proxy
                                    ▼                         ▼
┌───────────────────────────┐  ┌────────────────────────────────────────────────────────┐
│  Dynamic Endpoint Mirror  │  │        Cloudflare Zero-Trust Secure Tunnel             │
│  jsdelivr / Raw GitHub    │  │     https://*.trycloudflare.com (dynamic probe)        │
└─────────────┬─────────────┘  └──────────────────────────────┬─────────────────────────┘
              │ Fallback URL Discovery                       │ TCP / HTTP/2 Stream
              └─────────────────────────────┬────────────────┘
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│              PHYSICAL PHONE NODE: Xiaomi Redmi 9i (192.168.29.2:8080)                 │
│                                                                                       │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────┐  │
│  │   Multi-Modal Gateway   │  │  Elastic Memory Governor │  │ L1 Reflection Cache  │  │
│  │    (Python 3.14 Async)  │  │  (Zero-OOM JIT Eviction) │  │  (45ns Microsecond)  │  │
│  └────────────┬────────────┘  └─────────────┬────────────┘  └──────────┬───────────┘  │
│               │                             │                          │              │
│  ┌────────────▼─────────────────────────────▼──────────────────────────▼───────────┐  │
│  │                            Native Inference Daemons                             │  │
│  │   • whisper.cpp (STT)      • llama.cpp (Qwen Chat)    • Piper TTS (Voice)       │  │
│  │   • BGE-Micro (Embeddings) • BGE-Reranker             • Swades Agent Engine     │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Hardware & Storage                                 │  │
│  │   • Internal eMMC Flash    • Shared Storage (/sdcard) • Battery & Thermal Daemon│  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Base URIs & Dynamic Fallback Discovery

Always route through the Edge Base URL first. If you experience an edge disruption, discover the active tunnel endpoint directly using the Dynamic Discovery URIs.

| Route Type | URI | Behavior |
| :--- | :--- | :--- |
| **Global Edge Base** | `https://phone-whisper-server.pages.dev` | Global edge proxy with auto-retry, zero-DNS delay, and CORS enabled (`*`). |
| **Direct Tunnel (Live)** | Discover dynamically via `endpoint.json` | Direct Cloudflare trycloudflare tunnel bypassing edge proxy. |
| **Local LAN Direct** | `http://192.168.29.2:8080` | Zero-latency LAN access when on the same Wi-Fi network. |
| **Fast Discovery CDN** | `https://cdn.jsdelivr.net/gh/Electroiscoding/phone-whisper-server@main/endpoint.json` | 100% fresh edge mirror, immune to GitHub API rate limits. |
| **Raw GitHub CDN** | `https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json` | Fallback raw mirror. |

### Dynamic Endpoint Schema (`endpoint.json`):
```json
{
  "endpoint": "https://interesting-unexpected-interval-bedroom.trycloudflare.com",
  "inference": "https://interesting-unexpected-interval-bedroom.trycloudflare.com/inference",
  "telemetry": "https://interesting-unexpected-interval-bedroom.trycloudflare.com/telemetry",
  "phone_lan_ip": "http://192.168.29.2:8080",
  "mode": "dual_worldwide_and_local",
  "port": 8080,
  "updated_at": "2026-09-05T05:40:45Z"
}
```

---

## 3. Resilience & Exponential Backoff Protocol

The physical phone node runs an autonomous kernel supervisor. When network transitions occur, the tunnel may self-heal within 2 to 4 seconds.

### Client Agent Retry Algorithm:
1. **Initial Request**: Timeout = `8000ms`.
2. **If HTTP 503 or Connection Error**:
   - Check response JSON for `"status": "reconnecting"`.
   - Read `retry_after_sec` (defaults to `2`).
   - Sleep for $2^{\text{attempt}} \times 500\text{ms}$ (e.g., 1.0s, 2.0s, 4.0s).
   - Before full retry, probe `GET /telemetry` with a 3-second timeout.
   - If telemetry returns `200 OK`, resume pending request.
   - Max retry limit: `4 attempts`.

---

## 4. Zero-Auth Public Endpoints

The following endpoints do NOT require an `Authorization` header or API key:

### 4.1 System Telemetry
- **Path**: `GET /telemetry`
- **Purpose**: Real-time hardware vitals, battery level, SoC temperature, governor states, and RAM.
- **Example Request**:
  ```bash
  curl -s https://phone-whisper-server.pages.dev/telemetry
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "battery": {
      "level": 86,
      "status": "Discharging",
      "temperature": 33.0,
      "voltage_mv": 4173,
      "ac_powered": false,
      "usb_powered": false
    },
    "cpu": {
      "usage_percent": 0.4,
      "cores": 8,
      "is_active": false,
      "active_daemon": null
    },
    "memory": {
      "total_mb": 3790,
      "available_mb": 2100,
      "used_mb": 1690
    },
    "governor": {
      "active_models": [],
      "idle_evicted_models": ["whisper", "qwen_chat", "bge_embed", "bge_rerank"],
      "idle_timeout_sec": 75.0,
      "governor_policy": "dynamic_elastic_jit"
    },
    "total_requests": 42,
    "uptime_seconds": 62450,
    "timestamp": 1788586320
  }
  ```

### 4.2 Health Check
- **Path**: `GET /health`
- **Response**: `{"status": "healthy", "timestamp": 1788586320}`

### 4.3 Models & Capabilities
- **Path**: `GET /models`
- **Response**:
  ```json
  {
    "models": [
      {"id": "whisper-base.en", "type": "speech_to_text", "quantization": "q5_1", "vram_mb": 145},
      {"id": "qwen2.5-0.5b-instruct", "type": "chat_completion", "quantization": "q4_k_m", "vram_mb": 380},
      {"id": "bge-micro-v2", "type": "embeddings", "dimensions": 384, "vram_mb": 65},
      {"id": "piper-en-lessac", "type": "text_to_speech", "sample_rate": 22050, "vram_mb": 40}
    ]
  }
  ```

### 4.4 Speech-to-Text Transcription (`whisper.cpp`)
- **Path**: `POST /inference`
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `file`: Audio binary (WAV, MP3, M4A, OGG, WebM). 16kHz mono recommended.
  - `temperature`: (Optional) `0.0`
  - `language`: (Optional) `"en"`
- **Example Request**:
  ```bash
  curl -X POST https://phone-whisper-server.pages.dev/inference \
    -F "file=@sample.wav" \
    -F "language=en"
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "text": "Autonomous agent connected to sovereign phone node successfully.",
    "duration_sec": 3.42,
    "inference_time_ms": 482.1,
    "model": "whisper-base.en-q5_1"
  }
  ```

### 4.5 Neural Text-to-Speech (`piper-tts`)
- **Path**: `POST /tts`
- **Content-Type**: `application/json`
- **Body**: `{"text": "Datacenter online. Battery at 86 percent."}`
- **Response**: `audio/wav` binary stream.

---

## 5. Autonomous Coding Agent Engine (`Swades-Agent`)

The node hosts a full PRoot Alpine Linux environment capable of running autonomous coding workflows (cloning Git repositories, creating branches, modifying code, performing self-verification syntax checks, and opening GitHub Pull Requests).

### 5.1 Submitting an Agent Task
- **Path**: `POST /v1/agent/submit`
- **Content-Type**: `application/json`
- **Payload Schema**:
  ```json
  {
    "repo_url": "https://github.com/Electroiscoding/xerv",
    "task": "Add health check endpoint with uptime and battery stats in server.js",
    "github_token": "ghp_optional_if_opening_pr",
    "llm_provider": "openrouter",
    "model": "openrouter/free"
  }
  ```
- *Note*: If `llm_api_key` is omitted, the gateway automatically injects its on-device secure OpenRouter key vault with automatic 6-model fallback cycling (`openrouter/free` -> `inclusionai/ling-3.0-flash-fin:free` -> `nvidia/nemotron-3.5-lightning:free` -> `thinkingmachines/inkling-small:free` -> `inception/mercury-2.5-preview`).
- **Response (200 OK)**:
  ```json
  {
    "status": "QUEUED",
    "job_id": "job_9a8f4c1b2",
    "stream_url": "/v1/agent/stream/job_9a8f4c1b2",
    "logs_url": "/v1/agent/logs/job_9a8f4c1b2"
  }
  ```

### 5.2 Streaming Real-Time Agent Execution (SSE)
- **Path**: `GET /v1/agent/stream/{job_id}`
- **Accept**: `text/event-stream`
- **Event Types**:
  - `status`: Lifecycle updates (`CLONING`, `THINKING`, `EDITING`, `VERIFYING`, `COMPLETED`).
  - `thinking`: Inner monologue of the LLM reasoning about the codebase.
  - `tool_start`: File inspection, edit, or bash command execution.
  - `diff_update`: Real-time unified git diff of modified files.
  - `verification`: Self-verification syntax compile result (`node --check`, `py_compile`).
  - `pr_opened`: GitHub Pull Request URL if opened.

### 5.3 Fetching Execution Logs
- **Path**: `GET /v1/agent/logs/{job_id}`
- **Response**: Full structured array of all events, tool calls, and final git diff.

---

## 6. Authenticated Storage & Database Operations

For persistent storage, key management, and relational data operations:

### 6.1 Authentication Flow
1. **Register**: `POST /v1/storage/auth/register` with `{"username": "agent_alpha", "password": "<secret>"}`.
2. **Login**: `POST /v1/storage/auth/login` with `{"username": "agent_alpha", "password": "<secret>"}`.
3. **Obtain API Key**:
   - Headers: `Authorization: Bearer <token>` or `x-api-key: <key>`

### 6.2 Key Management
- `GET /v1/storage/auth/keys` — List all active API keys.
- `POST /v1/storage/auth/keys/generate` — Create scoped API key (`label`, `permissions`: `["read", "write", "admin"]`).

### 6.3 Relational Database Engine (`/v1/db/*`)
- **List Tables**: `GET /v1/db/tables`
- **Execute Query**:
  ```bash
  curl -X POST https://phone-whisper-server.pages.dev/v1/db/query \
    -H "x-api-key: <your_key>" \
    -H "Content-Type: application/json" \
    -d '{"query": "SELECT * FROM telemetry_events ORDER BY id DESC LIMIT 10"}'
  ```
- **Execute Mutation**:
  ```bash
  curl -X POST https://phone-whisper-server.pages.dev/v1/db/mutate \
    -H "x-api-key: <your_key>" \
    -H "Content-Type: application/json" \
    -d '{"statement": "INSERT INTO agent_checkpoints (job_id, step, state) VALUES (?, ?, ?)", "params": ["job_123", 1, "INITIALIZED"]}'
  ```

### 6.4 Distributed Storage Pools (`/v1/storage/*`)
- **Inspect Pools**: `GET /v1/dashboard/storage`
  - Returns capacity and health across:
    1. `Internal Flash (NVMe/eMMC)` — High-speed primary.
    2. `Public Shared Storage (/sdcard)` — Accessible via Android file system.
    3. `External Drive / SD / USB OTG` — Removable mass storage.
- **Upload Object**: `PUT /v1/storage/objects/{key}` with binary body.
- **Retrieve Object**: `GET /s/{project_id}/{key}` or `GET /v1/storage/objects/{key}`.

### 6.5 Sovereign Multi-Project Architecture (Firebase-Style Data Isolation)

Developers and applications are 100% physically isolated from each other. Rather than storing tables and blobs in a shared global pool, each project operates as a completely sovereign sandbox:

- **Isolated Physical Database**: Every project receives its own dedicated SQLite database file located at `.swades_storage/projects/<project_id>/data.db`. Tables created in Project A (e.g. `users`, `orders`) are completely invisible and inaccessible to Project B.
- **Dedicated Object Store Bucket**: Uploaded media and objects are isolated per project namespace (`.swades_storage/projects/<project_id>/blobs/` and memory index).
- **Request Scoping Header**: Autonomous agents and apps scope any API call to an individual project by passing the `X-Project-Id: <project_id>` HTTP header or `?project_id=<id>` query parameter.
- **Default Fallback**: If `X-Project-Id` is omitted, requests safely default to the user's primary workspace.

#### Multi-Project Management Endpoints:
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/v1/projects` | List all active projects owned by authenticated user with table count, disk size, and storage metrics. |
| `POST` | `/v1/projects` | Create a new isolated project (`{"name": "...", "description": "..."}`). Automatically provisions `data.db` and starter schema. |
| `GET` | `/v1/projects/{id}` | Inspect a specific project's live database size, table count, and blob metrics. |
| `DELETE` | `/v1/projects/{id}` | Deactivate an isolated project. |

---

## 7. Administrative & Console APIs (`/v1/dashboard/*`)

These endpoints power the high-end developer console (`dashboard.html`):

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/dashboard/overview` | Cluster summary (active users, key count, storage bytes, active flags, SoC vitals). | Yes |
| `GET` | `/v1/dashboard/analytics?horizon=15m` | Time-series request volume, latency p50/p95/p99, error rates. | Yes |
| `GET` | `/v1/dashboard/flags` | List all 8 feature flags and canary weights. | Yes |
| `POST` | `/v1/dashboard/flags/toggle` | Mutate feature flag state (`{"flag": "ai_agent_autonomous_dispatch", "enabled": true}`). | Yes |
| `GET` | `/v1/dashboard/remote-config` | Fetch active JSON remote configuration. | Yes |
| `POST` | `/v1/dashboard/remote-config` | Update hot-reloaded configuration object. | Yes |
| `GET` | `/v1/dashboard/experiments` | A/B testing experiment definitions and variant distribution. | Yes |
| `GET` | `/v1/dashboard/users` | List registered users, roles, and status. | Yes |
| `GET` | `/v1/dashboard/tables` | Inspect database table schemas and row counts. | Yes |
| `GET` | `/v1/dashboard/performance` | Latency flame graph data and thermal throttling governor status. | Yes |
| `GET` | `/v1/dashboard/logs` | Query append-only audit trail. | Yes |

---

## 8. Python SDK Connection Snippet for AI Agents

Autonomous agents can instantiate this resilient client helper to interface directly with the datacenter:

```python
import time
import requests

class PhoneDatacenterClient:
    def __init__(self, base_url="https://phone-whisper-server.pages.dev", api_key=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"x-api-key": self.api_key})

    def request_with_retry(self, method, path, **kwargs):
        kwargs.setdefault("timeout", 8.0)
        attempts = 0
        max_attempts = 4

        while attempts < max_attempts:
            attempts += 1
            try:
                url = f"{self.base_url}{path}"
                res = self.session.request(method, url, **kwargs)
                if res.status_code == 503 and attempts < max_attempts:
                    # Autonomous phone self-healing wait
                    retry_sec = float(res.headers.get("Retry-After", 2.0))
                    time.sleep(retry_sec * (1.5 ** attempts))
                    continue
                res.raise_for_status()
                return res.json()
            except (requests.RequestException, ValueError) as err:
                if attempts >= max_attempts:
                    raise
                time.sleep(1.0 * attempts)

    def get_telemetry(self):
        return self.request_with_retry("GET", "/telemetry")

    def transcribe_audio(self, audio_file_path):
        with open(audio_file_path, "rb") as f:
            return self.request_with_retry("POST", "/inference", files={"file": f})

    def submit_coding_job(self, repo_url, task):
        payload = {"repo_url": repo_url, "task": task}
        return self.request_with_retry("POST", "/v1/agent/submit", json=payload)

# Quick Verification
if __name__ == "__main__":
    client = PhoneDatacenterClient()
    vitals = client.get_telemetry()
    print(f"Node Battery: {vitals['battery']['level']}% | Temp: {vitals['battery']['temperature']}°C")
```

---

## 9. Error Reference & Troubleshooting Matrix

| HTTP Status | Reason | Agent Recovery Directive |
| :--- | :--- | :--- |
| `503 Service Unavailable` | `Phone AI Datacenter is self-healing / refreshing tunnel.` | Do NOT crash or stop. Sleep for `2.0s` and retry with exponential backoff. The supervisor re-establishes the tunnel automatically within 3 seconds. |
| `401 Unauthorized` | Missing or invalid `x-api-key` or session token. | Authenticate against `/v1/storage/auth/login` to acquire valid credentials. |
| `429 Too Many Requests` | Rate limit on inference queue. | Concurrency limit is 1 concurrent active LLM on physical ARM64 SoC. Wait 2 seconds and retry. |
| `504 Gateway Timeout` | Llama/Whisper execution exceeded timeout on heavy input. | Reduce input audio length or chunk text context into smaller token windows. |

---

## 10. Verification Directive for Connecting Agents

When you receive an instruction to integrate with this datacenter:
1. Verify connectivity: `curl -s https://phone-whisper-server.pages.dev/telemetry`.
2. Ensure you handle `503 reconnecting` gracefully with exponential backoff.
3. Keep this directive (`maker.md`) in your system prompt or tool context to invoke endpoints accurately.

---

## 11. Sovereign Cloud Database, Storage & 1-Line SDK (Firebase Alternative)

The phone datacenter operates as a high-speed sovereign cloud backend alternative to Google Firebase / Supabase:

### 11.1 Relational Database Engine (Firestore Alternative)
- **100% Isolated SQLite WAL per Project**: Scoped in `projects/<project_id>/data.db`.
- **Query Endpoint**: `POST /v1/db/sql` or `POST /v1/db/query`
  - Headers: `x-api-key: <KEY>`, `x-project-id: <PROJECT_ID>`
  - Body: `{"query": "SELECT * FROM items;"}`
- **Mutation Endpoint**: `POST /v1/db/mutate`
  - Body: `{"action": "insert_row", "table": "items", "data": {"title": "Product", "price": 19.99}}`
  - Body: `{"action": "delete_row", "table": "items", "pk_col": "id", "pk_val": 1}`
  - Body: `{"action": "update_cell", "table": "items", "pk_col": "id", "pk_val": 1, "column": "price", "new_val": 24.99}`

### 11.2 S3-Compatible Object Storage (Firebase Storage Alternative)
- **Upload Endpoint**: `PUT /v1/storage/objects/<key>`
  - Headers: `x-api-key: <KEY>`, `x-project-id: <PROJECT_ID>`, `Content-Type: <MIME>`
  - Body: Raw binary bytes
- **Public CDN Permalink**: `GET /s/<project_id>/<key>` (Instant edge CDN permalink)
- **List Objects**: `GET /v1/storage/objects`
- **Delete Object**: `DELETE /v1/storage/objects/<key>`

### 11.3 Instant 1-Line Client SDK
Include the client SDK in any web project:
```html
<script src="https://phone-whisper-server.pages.dev/swades.js"></script>
```
Execute queries, uploads, and auth in 1 line:
```javascript
const db = Swades.init({ apiKey: 'YOUR_KEY', project: 'YOUR_PROJECT' });

// 1-line SQL query
const items = await db.query("SELECT * FROM items;");

// 1-line insert
await db.insert("items", { title: "Phone Case", price: 12.50 });

// 1-line file upload to S3 CDN
const { url } = await db.storage.upload(file);
```
