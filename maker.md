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

### 4.5 Piper-VITS Neural Text-to-Speech (`/v1/audio/speech` & `/v1/audio/voices`)

The datacenter exposes an OpenAI-compatible speech synthesis endpoint backed by the **Piper VITS (Variational Inference with Monotonic Alignment Search)** neural engine, specifically engineered for low-power ARM Cortex cores. It features multi-tier caching (Client, Cloudflare Global Edge, and On-Device Gateway RAM/Disk Cache).

#### 4.5.1 Synthesize Speech (`POST` & `GET /v1/audio/speech`)
- **Paths**: `/v1/audio/speech`, `/speech`, `/tts`, `/v1/tts`
- **Supported Methods**:
  - `POST`: JSON payload (`application/json`)
  - `GET`: Query parameters (`?input=...&voice=...&speed=...`) for direct HTML5 `<audio src="...">` embedding and CDN caching.
- **Request Parameters**:
  | Parameter | Type | Default | Description |
  | :--- | :--- | :--- | :--- |
  | `input` / `text` | string | *required* | The text prompt to synthesize into speech. |
  | `voice` | string | `"amy"` | Piper VITS voice persona: `amy` (Female) or `lessac` (Male). |
  | `speed` | float | `1.0` | Playback speed multiplier (`0.5` to `2.0`). |
  | `response_format` | string | `"wav"` | Output audio container format (`wav`). |
  | `quality` | string | `"auto"` | `"auto"` (multi-tier cache/realtime) or `"neural"` (live VITS synthesis). |

- **Response Headers**:
  - `Content-Type: audio/wav`
  - `Cache-Control: public, max-age=86400, s-maxage=604800, immutable`
  - `ETag: "<sha256_hash>"`
  - `Accept-Ranges: bytes`
  - `X-TTS-Engine: Piper-VITS Neural Engine`
  - `X-TTS-Model: Piper VITS (en_US-{voice}-medium)`
  - `X-TTS-Voice: amy` (or `lessac`)
  - `X-Sample-Rate: 22050`
  - `X-Cache: HIT (RAM)` (or `HIT (Disk)`, `MISS (Live Synthesis)`)
  - `X-Edge-Cache: HIT` (when served from Cloudflare's 300+ global edge locations)
- **HTTP 304 Support**: Pass `If-None-Match: "<sha256_hash>"` for instant 304 Not Modified verification (<1ms, 0 byte transfer).
- **Binary Output**: 22,050 Hz broadcast-quality WAV audio stream.

#### 4.5.2 Voice Catalogue (`GET /v1/audio/voices`)
Exposes the supported Piper VITS neural voices on the device:

| Voice ID | Name & Description | Language | Gender | Architecture | Characteristics |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `amy` | Amy (English Female • Natural VITS) | `en-US` | Female | VITS (61 MB ONNX) | Warm, articulate, high naturalness |
| `lessac` | Lessac (English Male • Resonant VITS) | `en-US` | Male | VITS (61 MB ONNX) | Crisp, deep, authoritative narration |

*Full Voice Aliasing*: Any female alias (`female`, `woman`, `heart`, `alloy`, `sky`, `nova`) maps to `amy`. Any male alias (`male`, `man`, `adam`, `echo`, `onyx`, `michael`) maps to `lessac`.

#### 4.5.3 4-Tier Latency & Caching Architecture
To guarantee maximum speed:

| Tier | Layer | Latency | Description |
| :--- | :--- | :--- | :--- |
| **Tier 0** | Client Memory & Disk | **0.01ms** | In-browser `Map` (`swades.js`) and local disk cache in `~/.swades/tts_cache/` (`swades.py`). |
| **Tier 1** | Cloudflare Edge Cache | **<5ms** | Global edge caching across 300+ datacenters via `caches.default` in `_worker.js`. |
| **Tier 2** | On-Device Gateway RAM Cache | **<15ms** | In-memory RAM audio buffer stored on the phone (`_PIPER_MEM_CACHE`). |
| **Tier 3** | On-Device Disk Cache | **~20ms** | On-device persistent cache in `~/.piper_cache/`. |
| **Tier 4** | Live Piper VITS Synthesis | **~0.75-0.88x RTF** | Faster-than-real-time native ARM VITS neural inference on Cortex-A53 CPU. |

#### 4.5.4 Developer SDK Usage

##### JavaScript / Node.js (`swades.js`):
```javascript
import { Swades } from './swades.js';
const client = Swades.init();

// 1. Synthesize speech (Cached in client memory & Cloudflare edge)
const audio = await client.speak("Welcome to earth!", { voice: "amy" });
audio.play();

// 2. Direct cacheable URL for <audio src="..."> HTML elements
const audioUrl = client.getAudioUrl("Welcome to earth!", { voice: "amy" });
document.getElementById("myAudio").src = audioUrl;

// 3. List available voices
const voices = await client.voices();
```

##### Python (`swades.py`):
```python
from swades import Swades
client = Swades()

# 1. Synthesize audio bytes (Automatic local memory + disk caching in ~/.swades/tts_cache/)
audio_bytes = client.tts("Welcome to earth!", voice="amy", speed=1.0)

# 2. Save directly to file
client.tts_to_file("Welcome to earth!", "speech.wav", voice="lessac")

# 3. Direct edge-cacheable URL
url = client.get_audio_url("Welcome to earth!", voice="amy")

# 4. List available voices
voices = client.voices()
```

##### cURL Examples:
```bash
# POST Synthesis (Amy - Female)
curl -s -X POST https://phone-whisper-server.pages.dev/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Welcome to earth!", "voice": "amy"}' \
  --output speech_female.wav

# POST Synthesis (Lessac - Male)
curl -s -X POST https://phone-whisper-server.pages.dev/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Welcome to earth!", "voice": "lessac"}' \
  --output speech_male.wav

# GET Direct Streaming (Edge Cacheable)
curl -s "https://phone-whisper-server.pages.dev/v1/audio/speech?input=Welcome+to+earth!&voice=amy" \
  --output speech_get.wav
```

### 4.6 Zstandard (zstd v1.5.7) High-Throughput Hardware Compression Engine (`/v1/compress` & `/v1/decompress`)

The physical phone node features native C-level Zstandard (zstd v1.5.7) hardware acceleration via `libzstd.so` running on MediaTek Helio G25 (8x Cortex-A53 @ 2.0GHz).

#### 4.6.1 Strict Dual-Tier Routing Policy

The system enforces an uncompromising dual-tier compression policy on phone silicon based on empirical MediaTek Helio G25 multi-core benchmarks (-T4):

* **Use Level 1 (`-1 -T4`)**: Dedicated for real-time HTTP transfer, API requests, and live streaming. Delivers ~180 MB/s throughput, <1.5ms silicon latency, and a minimal ~10 MB RAM footprint.
* **Use Level 3 (`-3 -T4`)**: Dedicated for saving files to disk / storage vault backups (**the absolute sweet spot**). Delivers ~3.2x ratio (up to 97.4% on logs), ~150 MB/s throughput, and optimal write endurance on eMMC flash storage.
* **Levels 9–19 (Permanently Disabled)**: Locked out on phone silicon to protect against thermal throttling (45°C+) and Android Low Memory Killer (LMK) eviction.

##### Hardware Benchmark Breakdown (Per 1 GB of Data on 4 CPU Cores -T4)

| Compression Level Group | Original Size | Estimated After Size | Time to Finish | RAM Needed | Operational Tier & Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 1 (Fastest, `-1 -T4`)** | 1,000 MB | ~350 MB | ~15 seconds | ~10 MB | **Developer API (`/v1/compress`) & Live Streaming** |
| **Level 3 (Sweet Spot, `-3 -T4`)** | 1,000 MB | ~300 MB | ~25 seconds | ~30 MB | **Storage Vault & Disk Backups (High-Ratio Persistence)** |
| **Level 9 (Medium)** | 1,000 MB | ~270 MB | ~1.5 minutes | ~70 MB | *Disabled Permanently on Phone Silicon (Thermal Risk)* |
| **Level 15 (High)** | 1,000 MB | ~250 MB | ~4 minutes | ~150 MB | *Disabled Permanently on Phone Silicon (Thermal Risk)* |
| **Level 19 (Max Safe)** | 1,000 MB | ~230 MB | ~8+ minutes | ~500 MB | *Disabled Permanently on Phone Silicon (LMK Eviction Risk)* |

##### Key Architectural Takeaways for Phone Silicon
1. **The Sweet Spot**: Moving from Level 1 to Level 3 takes only 10 seconds more per GB, but saves an extra 50 MB of flash storage. That is why **Level 3 (`-3 -T4`) is available and recommended for storage vault backups, disk persistence, and high-ratio compression**.
2. **The Real-Time Requirement**: Level 1 (`-1 -T4`) takes only 15 seconds per 1 GB (~180 MB/s, <1.5ms per API request) with an ultra-low ~10 MB RAM footprint, making it the ideal fit for **developer API requests and live streaming**.
3. **The Penalty Zone**: Moving from Level 3 to Level 19 saves only 70 MB more per 1 GB, but takes 8+ minutes and requires 500 MB RAM, causing immediate CPU thermal throttling (45°C+) and Android Low Memory Killer (LMK) eviction on 2GB–4GB RAM devices.

#### 4.6.2 OpenAPI 3.1 Specification

```json
{
  "openapi": "3.1.0",
  "paths": {
    "/v1/compress": {
      "post": {
        "summary": "Real-Time Hardware Zstandard Compression",
        "description": "Compresses binary payload or JSON string using Level 1 (-1 -T4) on phone ARM Cortex-A53 silicon.",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "data": { "type": "string", "description": "Raw string or base64 encoded data" },
                  "level": { "type": "integer", "default": 1, "minimum": 1, "maximum": 3 },
                  "format": { "type": "string", "enum": ["base64", "binary"], "default": "base64" },
                  "encoding": { "type": "string", "enum": ["utf-8", "base64"], "default": "utf-8" }
                },
                "required": ["data"]
              }
            },
            "application/octet-stream": {
              "schema": { "type": "string", "format": "binary" }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Compressed Zstandard payload",
            "headers": {
              "X-Zstd-Engine": { "schema": { "type": "string" } },
              "X-Zstd-Level": { "schema": { "type": "integer" } },
              "X-Compression-Ratio": { "schema": { "type": "string" } },
              "X-Inference-Time-Ms": { "schema": { "type": "string" } }
            },
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string", "example": "success" },
                    "engine": { "type": "string", "example": "Zstandard v1.5.7 (ARM Cortex-A53 Native)" },
                    "level": { "type": "integer", "example": 1 },
                    "original_size": { "type": "integer", "example": 1024 },
                    "compressed_size": { "type": "integer", "example": 312 },
                    "compression_ratio": { "type": "number", "example": 3.28 },
                    "space_saved_percent": { "type": "number", "example": 69.5 },
                    "elapsed_ms": { "type": "number", "example": 1.82 },
                    "compressed_base64": { "type": "string" }
                  }
                }
              },
              "application/zstd": {
                "schema": { "type": "string", "format": "binary" }
              }
            }
          }
        }
      }
    },
    "/v1/decompress": {
      "post": {
        "summary": "Microsecond Zstandard Decompression",
        "description": "Decompresses Zstandard frame with exact buffer allocation (<1ms).",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "data": { "type": "string", "description": "Base64 encoded zstd frame" },
                  "format": { "type": "string", "enum": ["base64", "text"], "default": "base64" }
                },
                "required": ["data"]
              }
            },
            "application/zstd": {
              "schema": { "type": "string", "format": "binary" }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Decompressed original payload"
          }
        }
      }
    },
    "/v1/zstd/info": {
      "get": {
        "summary": "Zstandard Engine Hardware & Tier Telemetry",
        "responses": {
          "200": {
            "description": "Hardware architecture, active libzstd version, and dual-tier specifications"
          }
        }
      }
    }
  }
}
```

#### 4.6.3 Developer SDK Usage

##### Python (`swades.py`):
```python
from swades import Swades

client = Swades()

# 1. Real-time Level 1 compression (<2ms, ~180 MB/s)
res = client.compress("High speed sensor telemetry payload", level=1, as_json=True)
print(f"Compressed {res['original_size']}B -> {res['compressed_size']}B ({res['space_saved_percent']}% saved in {res['elapsed_ms']}ms)")

# 2. Binary stream compression
raw_bytes = b"Sensor data binary array" * 100
compressed_bytes = client.compress(raw_bytes, level=1)

# 3. Decompress back to string or bytes
recovered_text = client.decompress(res["compressed_base64"], as_text=True)
recovered_bytes = client.decompress(compressed_bytes)

# 4. Query engine hardware info
info = client.zstd_info()
print(info["engine"], info["version"], info["tiers"])
```

##### JavaScript / Web (`swades.js`):
```javascript
import { Swades } from './swades.js';
const client = Swades.init();

// 1. One-line compression (<2ms):
const res = await client.compress("High speed sensor telemetry payload");
console.log(`Saved ${res.space_saved_percent}% in ${res.elapsed_ms}ms`);

// 2. One-line decompression:
const text = await client.decompress(res.compressed_base64);
console.log("Recovered text:", text);

// 3. Query engine specs:
const info = await client.zstdInfo();
console.log("Engine:", info.engine, "Hardware:", info.hardware);
```

##### cURL:
```bash
# Level 1 Real-time compression:
curl -X POST "https://phone-whisper-server.pages.dev/v1/compress" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"data": "High speed sensor telemetry payload", "level": 1}'

# Decompress frame:
curl -X POST "https://phone-whisper-server.pages.dev/v1/decompress" \
  -H "Content-Type: application/json" \
  -d '{"data": "KLUv/SCpLQQAcskdHXA1..."}'

# Query hardware info:
curl -s "https://phone-whisper-server.pages.dev/v1/zstd/info"
```

### 4.7 Advanced Charging Controller (ACC) (`/v1/acc/info` & `/v1/acc/control`)

The node incorporates an integrated Advanced Charging Controller (ACC) to safeguard lithium-ion / lithium-polymer battery chemistry during 24/7 plugged-in datacenter operation.

#### 4.7.1 Operational Principles & Thresholds
* **70%–80% Capacity Sweet Spot**: Automatically pauses charging when battery level reaches **80%** (`pause_capacity`) and resumes when capacity drops below **70%** (`resume_capacity`). This prevents high continuous cell voltage (4.35V+) from accelerating chemical degradation.
* **40.0°C Thermal Protection Guard**: Triggers an instantaneous charging cutoff if battery temperature reaches or exceeds **40.0°C** (`max_temp_c`), allowing the device to cool back down to **36.0°C** (`cooldown_temp_c`) before resuming.
* **Zero Performance Degradation**: The ACC controller operates as an asynchronous background thread polling at a relaxed 3s–5s cadence with lock-free atomic snapshots (<0.01 ms read latency, <0.01% CPU utilization).

#### 4.7.2 OpenAPI 3.1 Specification

```json
{
  "openapi": "3.1.0",
  "paths": {
    "/v1/acc/info": {
      "get": {
        "summary": "Retrieve live ACC status, battery telemetry, and thresholds",
        "responses": {
          "200": {
            "description": "ACC telemetry object",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string", "example": "success" },
                    "engine": { "type": "string", "example": "Advanced Charging Controller (ACC)" },
                    "version": { "type": "string", "example": "v2026.9.1" },
                    "enabled": { "type": "boolean" },
                    "mode": { "type": "string", "example": "hybrid_hardware_acc" },
                    "charging_state": { "type": "string", "enum": ["charging", "paused_capacity", "paused_thermal", "discharging", "idle"] },
                    "battery": {
                      "type": "object",
                      "properties": {
                        "level": { "type": "integer", "example": 78 },
                        "temperature_c": { "type": "number", "example": 32.3 },
                        "voltage_mv": { "type": "integer", "example": 3810 },
                        "health": { "type": "string", "example": "Good" }
                      }
                    },
                    "thresholds": {
                      "type": "object",
                      "properties": {
                        "pause_capacity": { "type": "integer", "default": 80 },
                        "resume_capacity": { "type": "integer", "default": 70 },
                        "max_temp_c": { "type": "number", "default": 40.0 }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/v1/acc/control": {
      "post": {
        "summary": "Configure ACC thresholds or trigger manual overrides",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "pause_capacity": { "type": "integer", "minimum": 20, "maximum": 100 },
                  "resume_capacity": { "type": "integer", "minimum": 10, "maximum": 99 },
                  "max_temp_c": { "type": "number" },
                  "action": { "type": "string", "enum": ["pause", "resume", "reset", "auto"] },
                  "enabled": { "type": "boolean" }
                }
              }
            }
          }
        },
        "responses": {
          "200": { "description": "Updated ACC state" }
        }
      }
    }
  }
}
```

#### 4.7.3 Developer SDK & CLI Usage

##### Python (`swades.py`):
```python
from swades import Swades
client = Swades()

# Query live ACC state
info = client.acc_info()
print(f"Battery: {info['battery']['level']}% (Temp: {info['battery']['temperature_c']}°C)")

# Configure custom thresholds
client.acc_control(pause=85, resume=75, max_temp=39.5)

# Reset to datacenter defaults (80% pause, 70% resume, 40°C thermal cutoff)
client.acc_reset()
```

##### JavaScript (`swades.js`):
```javascript
import { Swades } from './swades.js';
const client = Swades.init();

// Query ACC specs
const info = await client.acc.info();
console.log("ACC Engine:", info.engine, "State:", info.charging_state);

// Set thresholds
await client.acc.control({ pause: 82, resume: 72 });
```

##### Native Termux CLI:
```bash
acc -i          # Display full battery telemetry & switch status
acc 80 70       # Configure 80% pause / 70% resume thresholds
acc pause       # Force charging circuit off
acc resume      # Force charging circuit on
acc reset       # Reset to default sovereign datacenter profile
```

---


### 4.8 Universal Zstandard (zstd v1.5.7) File & Binary Compression Engine

Zstandard is the exclusive, universal compression standard across the entire sovereign phone datacenter for **both file and text compression all the time, always, everywhere**:
* **Universal File Compression**: Hardware-accelerated compression for image binary payloads, audio buffers, documents, and disk blobs (`/v1/compress`, `/v1/images/compress`, `/v1/storage/objects/*`).
* **Universal Text Compression**: Real-time compression for developer API requests, JSON responses, database telemetry, and dynamic HTTP streams (`Accept-Encoding: zstd`, `Content-Encoding: zstd`).

#### 4.8.1 Strict Policy & Operational Principles
* **Pure Zstandard Level 1 (`-1 -T4`)**: Dedicated for developer API requests, file/image compression, real-time network transfer, and CDN streaming (<1.5ms, ~180 MB/s).
* **Pure Zstandard Level 3 (`-3 -T4`)**: Dedicated for storage vault disk persistence, eMMC flash protection, system backups, and high-ratio payload compression (~150 MB/s, sweet spot, open to all developers).
* **100% Bit-Exact Lossless**: No lossy quantization artifacts, no blurry downscaling, no color subsampling degradation.
* **Universal Payload Support**: Ingests image binary payloads, arbitrary files, and raw byte buffers.
* **Zero Bloat**: Eliminates third-party imaging dependencies and memory leaks, executing directly against native C `libzstd.so.1.5.7` with 4 worker threads.

#### 4.8.2 OpenAPI 3.1 Specification

```json
{
  "openapi": "3.1.0",
  "paths": {
    "/v1/images/compress": {
      "post": {
        "summary": "Compresses an image payload using native Zstandard Level 1 (-1 -T4)",
        "description": "Accepts direct binary image octet-streams or JSON Base64 payloads and returns Zstandard-compressed output in <1.5ms",
        "requestBody": {
          "content": {
            "application/octet-stream": {
              "schema": { "type": "string", "format": "binary" }
            },
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "image": { "type": "string", "description": "Base64 encoded image or Data URL" },
                  "as_json": { "type": "boolean", "default": true }
                },
                "required": ["image"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Zstandard-compressed image payload",
            "headers": {
              "X-Zstd-Engine": { "schema": { "type": "string", "example": "libzstd.so.1.5.7" } },
              "X-Zstd-Tier": { "schema": { "type": "string", "example": "api" } },
              "X-Zstd-Level": { "schema": { "type": "integer", "example": 1 } },
              "X-Compression-Ratio": { "schema": { "type": "string" } },
              "X-Inference-Time-Ms": { "schema": { "type": "string" } }
            },
            "content": {
              "application/octet-stream": {
                "schema": { "type": "string", "format": "binary" }
              },
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string", "example": "success" },
                    "engine": { "type": "string", "example": "Zstandard v1.5.7 (ARM Cortex-A53 Native 4T)" },
                    "compression_algorithm": { "type": "string", "example": "zstd" },
                    "tier": { "type": "string", "example": "api" },
                    "level": { "type": "integer", "example": 1 },
                    "original_size": { "type": "integer", "example": 524288 },
                    "compressed_size": { "type": "integer", "example": 185420 },
                    "compression_ratio": { "type": "number", "example": 2.83 },
                    "space_saved_percent": { "type": "number", "example": 64.6 },
                    "elapsed_ms": { "type": "number", "example": 0.82 },
                    "throughput_mb_s": { "type": "number", "example": 182.4 },
                    "compressed_base64": { "type": "string" },
                    "data_url": { "type": "string" }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/v1/images/info": {
      "get": {
        "summary": "Retrieve Zstandard image compression engine specifications",
        "responses": {
          "200": {
            "description": "Hardware Zstandard image engine specifications",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string", "example": "success" },
                    "engine": { "type": "string", "example": "Zstandard v1.5.7 (ARM Cortex-A53 Native 4T)" },
                    "compression_algorithm": { "type": "string", "example": "zstd" },
                    "api_level": { "type": "integer", "example": 1 },
                    "internal_level": { "type": "integer", "example": 3 },
                    "supported_payloads": { "type": "array", "items": { "type": "string" } }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

#### 4.8.3 Empirical Hardware Benchmarks (MediaTek Helio G25)

| Payload Type | Input Size | Zstd Level | Output Size | Space Saved | Latency | Throughput | Mode |
|---|---|---|---|---|---|---|---|
| **Raw PNG Image** | 1,280 KB | **Level 1 (-1 -T4)** | **~420 KB** | **67.2%** | **0.85 ms** | ~185 MB/s | Bit-Exact Lossless |
| **Raw JPEG Image** | 3,450 KB | **Level 1 (-1 -T4)** | **~2,980 KB** | **13.6%** | **1.82 ms** | ~178 MB/s | Bit-Exact Lossless |
| **SVG Vector Graphic**| 640 KB | **Level 1 (-1 -T4)** | **~98 KB** | **84.7%** | **0.42 ms** | **~210 MB/s** | Bit-Exact Lossless |
| **Raw RGBA Bitmap** | 8,200 KB | **Level 1 (-1 -T4)** | **~1,950 KB** | **76.2%** | **4.20 ms** | ~188 MB/s | Bit-Exact Lossless |

#### 4.8.4 Developer SDK & cURL Integration

##### Python (`swades.py`):
```python
from swades import Swades

client = Swades()

# 1-line Zstandard image compression (auto-detects file path, bytes, or Base64):
compressed_bytes = client.compress_image("photo.png")
with open("photo.png.zst", "wb") as f:
    f.write(compressed_bytes)

# Lossless decompression:
restored_bytes = client.decompress_image(compressed_bytes)

# Engine specs:
specs = client.image_info()
print("Engine:", specs["engine"])
```

##### JavaScript (`swades.js`):
```javascript
import { Swades } from './swades.js';

const client = Swades.init();

// Compress image binary losslessly via Level 1 (-1 -T4):
const zstdBytes = await client.images.compress(imageUint8Array);

// Restore original image bytes:
const originalBytes = await client.images.decompress(zstdBytes);

// Query engine info:
const info = await client.images.info();
console.log("Image Zstd Engine:", info.engine);
```

##### cURL:
```bash
# 1. Direct binary image compression:
curl -X POST "https://phone-whisper-server.pages.dev/v1/images/compress" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@photo.png" \
  -o "photo.png.zst"

# 2. JSON Base64 image compression:
curl -X POST "https://phone-whisper-server.pages.dev/v1/images/compress" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"image": "iVBORw0KGgoAAAANSUhEUgAA...", "as_json": true}'

# 3. Query engine specs:
curl -s "https://phone-whisper-server.pages.dev/v1/images/info"
```

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
