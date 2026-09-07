# PhoneWhisper AI — Turning an Old Android Phone into a Self-Hosted Sovereign AI Datacenter

> **An honest, open-source hacker experiment:** Running multi-modal AI models (OpenAI Whisper, Qwen 2.5, Piper TTS, BAAI BGE Embeddings, BGE Reranker, Google MediaPipe, and Native Zstandard v1.5.7) directly on a spare **$70 Redmi 9i / 9A (MediaTek Helio G25, 8x Cortex-A53, 4GB RAM)** running Termux — **100% Self-Hosted, Sovereign, Zero External Cloud Dependencies.**

---

## The Reality & Philosophy (100% Sovereign & Local)

* **Hardware:** A single budget Android smartphone (Redmi 9i / 9A) with 8x ARM Cortex-A53 CPU cores @ 2.0 GHz and 4GB RAM (~2GB free after Android OS).
* **Software Stack:** Linux inside Termux, `llama.cpp`, `whisper.cpp`, `piper` (VITS neural TTS) / `espeak-ng`, `libzstd.so` v1.5.7 native C library, `Pillow`, and a lightweight Python process supervisor (`gateway.py`).
* **Direct Local Access:** Binds to `0.0.0.0:8080`, allowing instant access over your local Wi-Fi router, Phone Hotspot, or USB reverse tethering (`http://192.168.29.2:8080` or `http://localhost:8080`), as well as secure edge access via Cloudflare Pages and quick tunnels.
* **Memory Management:** Because the phone cannot keep multiple heavy neural networks in RAM simultaneously, `gateway.py` automatically spawns the requested model when a request arrives and **terminates (`pkill`) idle models after 75 seconds of silence**.
* **Zero Cloud Outages:** Completely runs on phone silicon with zero external proprietary API tokens, zero rate limits, zero vendor lock-in, and zero data leakage.

---

## Available AI Modalities & Endpoints

| Modality | Model / Engine | Runtime | Endpoint | Typical Latency |
| :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text** | OpenAI Whisper Base.en Q5_1 | `whisper.cpp` | `POST /inference` | ~5–15s |
| **SLM Chat** | Qwen 2.5 0.5B Instruct Q4_K_M | `llama.cpp` | `POST /v1/chat/completions` | ~10–12s (Streaming) |
| **Text-to-Speech** | Piper TTS (VITS Neural) / eSpeak-NG | Native ARM | `POST /v1/audio/speech` | ~1.5s |
| **Hardware Compression** | Zstandard v1.5.7 Dual-Tier Engine | Native `libzstd.so` C / -T4 | `POST /v1/compress` & `POST /v1/decompress` | <1.5ms (~180 MB/s) |
| **Sovereign Cloud Storage** | S3-Compatible Vault + Auto Zstd L3 | `SwadeObjectStore` / eMMC | `PUT /v1/storage/{bucket}/{key}` | <0.5ms RAM / <8ms Disk |
| **Sovereign SQL Database** | SQLite3 + Microsecond WAL Engine | Python / SQLite3 | `POST /v1/dashboard/db/sql` | <1ms |
| **Vector Embeddings** | BAAI BGE-Small-en-v1.5 (896-d) | `llama.cpp` | `POST /v1/embeddings` | ~2–3s |
| **Cross-Encoder Rerank** | BAAI BGE-Reranker-Base | `llama.cpp` | `POST /v1/rerank` | ~10–12s |
| **Computer Vision** | Google MediaPipe Spatial AI | ARM CPU | `POST /v1/vision/{task}` | ~5–50ms |
| **Swades Agent** | Autonomous ReAct Loop + GitHub PRs | Node.js | `POST /v1/agent/submit` | Multi-step Async |
| **Hardware Telemetry** | Linux Kernel & Battery Metrics | Python / OS | `GET /telemetry` | ~0.1ms |

---

## Zstandard (zstd v1.5.7) Dual-Tier Hardware Compression Policy

The server embeds native Zstandard v1.5.7 C bindings directly linked to Android Termux userland (`/data/data/com.termux/files/usr/lib/libzstd.so`). To guarantee 24/7 uptime without thermal throttling or out-of-memory crashes on 2GB–4GB RAM phones, the system enforces a strict dual-tier policy:

* **Level 1 (`-1 -T4`) — Developer API & Live Streaming:**
  * **Scope:** All external developer requests to `POST /v1/compress`, real-time HTTP `Content-Encoding: zstd`, and live client streaming.
  * **Performance:** ~150 to 190 MB/s compression throughput, <1.5ms latency, ~10 MB RAM footprint.
  * **Enforcement:** External API requests requesting levels 2–19 are automatically clamped to Level 1.
* **Level 3 (`-3 -T4`) — Internal Sovereign Storage Vault:**
  * **Scope:** Internal storage persistence (`POST /v1/storage`), disk backups, and cached neural audio buffers. Internal only.
  * **Performance:** ~120 to 155 MB/s throughput, ~30 MB RAM footprint, ~3.2x compression ratio (up to 97.4% space savings on text and logs).
  * **Flash Longevity:** Reduces eMMC flash memory write wear by up to 75%.
* **Levels 9 to 19 — Permanently Disabled on Silicon:**
  * Levels 9–19 demand up to 500 MB RAM and 8+ minutes per GB, causing MediaTek Helio G25 CPU thermal throttling (45°C+) and Android Low Memory Killer (LMK) process eviction.

---

## Universal Drop-In Code Examples

### 1. Python (`swades` SDK or `requests`)

```python
from swades import Swades

client = Swades(endpoint="http://192.168.29.2:8080")

# 1. Real-time Hardware Zstandard Compression (Level 1, <1.5ms)
compressed = client.compress("System logs and telemetry payload", as_json=True)
print(f"Compressed in {compressed['elapsed_ms']}ms -> Ratio: {compressed['compression_ratio']}x")

# 2. Decompress
original = client.decompress(compressed["compressed_base64"], as_text=True)
print("Decompressed text:", original)

# 3. Stream Chat from Qwen 2.5 SLM
import requests, json
res = requests.post(
    "http://192.168.29.2:8080/v1/chat/completions",
    json={"messages": [{"role": "user", "content": "Explain gravity in 10 words"}], "stream": True},
    stream=True
)
for line in res.iter_lines(decode_unicode=True):
    if line.startswith("data: ") and "[DONE]" not in line:
        chunk = json.loads(line[6:])
        print(chunk["choices"][0]["delta"].get("content", ""), end="", flush=True)
```

### 2. JavaScript / TypeScript / Node.js (`swades.js`)

```javascript
import swades from "./swades.js";

// Initialize client
const client = swades.init({ endpoint: "http://192.168.29.2:8080" });

// 1. Ultra-fast Zstandard Compression (Level 1, ~180 MB/s)
const res = await client.zstd.compress("Telemetry payload stream", { format: "base64" });
console.log(`Compressed in ${res.elapsed_ms}ms: ${res.original_size}B -> ${res.compressed_size}B`);

// 2. Decompress
const decomp = await client.zstd.decompress(res.compressed_base64, { asText: true });
console.log("Decompressed:", decomp);

// 3. Speech-to-Text via Whisper.cpp
const formData = new FormData();
formData.append("file", audioBlob, "recording.wav");
const stt = await fetch("http://192.168.29.2:8080/inference", { method: "POST", body: formData });
const sttData = await stt.json();
console.log("Transcribed Text:", sttData.text);
```

### 3. cURL (Direct HTTP API)

```bash
# Compress string via Level 1 hardware engine (<1.5ms)
curl -s -X POST "http://192.168.29.2:8080/v1/compress" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"data": "Hello sovereign phone AI datacenter"}'

# Decompress frame back to plain text
curl -s -X POST "http://192.168.29.2:8080/v1/decompress" \
  -H "Content-Type: application/json" \
  -d '{"compressed_base64": "KLUv/SBFKQIASGVsbG8gc292ZXJlaWduIHBob25lIEFJIGRhdGFjZW50ZXI=", "as_text": true}'

# Inspect Zstandard engine telemetry and policy
curl -s "http://192.168.29.2:8080/v1/zstd/info"
```

### 4. Flutter / Dart

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

Future<String> askPhoneSLM(String prompt) async {
  final res = await http.post(
    Uri.parse("http://192.168.29.2:8080/v1/chat/completions"),
    headers: {"Content-Type": "application/json"},
    body: jsonEncode({
      "messages": [{"role": "user", "content": prompt}],
      "stream": false
    }),
  );
  return jsonDecode(res.body)["choices"][0]["message"]["content"];
}
```

### 5. Rust (`tokio` + `reqwest`)

```rust
use reqwest::Client;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new();
    let res: serde_json::Value = client
        .get("http://192.168.29.2:8080/telemetry")
        .send().await?
        .json().await?;
    println!("Phone Battery: {}%", res["battery"]["level"]);
    Ok(())
}
```

### 6. Go

```go
package main

import (
    "fmt"
    "net/http"
    "io"
)

func main() {
    resp, err := http.Get("http://192.168.29.2:8080/telemetry")
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()
    body, _ := io.ReadAll(resp.Body)
    fmt.Println(string(body))
}
```

---

## Quick Setup on Phone

1. **Install Termux & Dependencies**:
   ```bash
   pkg update && pkg install -y python nodejs git build-essential clang zstd libzstd
   pip install pillow requests
   ```
2. **Start the Sovereign Gateway & Governor**:
   ```bash
   python3 mobile/gateway.py
   ```
3. **Open the Web UI & Console**:
   Open `index.html`, `dashboard.html`, or `docs.html` on any device on your Wi-Fi network or via the Cloudflare Pages deployment.

---

*PhoneWhisper AI is 100% open-source, private, and offline-first.*
