# 📱 PhoneWhisper AI — Turning an Old Android Phone into a Self-Hosted Sovereign AI Datacenter

> **An honest, open-source hacker experiment:** Running multi-modal AI models (OpenAI Whisper, Qwen 2.5, BAAI BGE Embeddings, BGE Reranker, and Google MediaPipe) directly on a spare **$70 Redmi 9i (MediaTek Helio G25, 4GB RAM)** running Termux — **100% Self-Hosted, Zero Cloudflare, Zero External Cloud Dependencies.**

---

## 💡 The Reality & Philosophy (100% Sovereign & Local)

* **Hardware:** A single budget Android smartphone (Redmi 9i) with 8x ARM Cortex-A53 CPU cores and 4GB RAM (~2GB free after Android OS).
* **Software Stack:** Linux inside Termux, `llama.cpp`, `whisper.cpp`, `espeak`, `Pillow`, and a lightweight Python process supervisor (`gateway.py`).
* **Direct Local Access:** Binds to `0.0.0.0:8080`, allowing instant access over your local Wi-Fi router, Phone Hotspot, or USB reverse tethering (`http://192.168.29.2:8080` or `http://localhost:8080`).
* **Memory Management:** Because the phone cannot keep multiple heavy neural networks in RAM simultaneously, `gateway.py` automatically spawns the requested model when a request arrives and **terminates (`pkill`) idle models after 75 seconds of silence**.
* **Zero Cloudflare / Zero Outages:** Completely runs in your local network with zero external proxy tunnels, zero rate limits, zero 530/522 edge timeouts, and zero data leakage.

---

## 🌟 Available AI Modalities & Endpoints

| Modality | Model / Engine | Runtime | Endpoint | Typical Latency |
| :--- | :--- | :--- | :--- | :--- |
| **🎙️ Speech-to-Text** | OpenAI Whisper Base.en Q5_1 | `whisper.cpp` | `POST /inference` | ~5–15s |
| **💬 SLM Chat** | Qwen 2.5 0.5B Instruct Q4_K_M | `llama.cpp` | `POST /v1/chat/completions` | ~10–12s (Streaming) |
| **🗣️ Text-to-Speech** | eSpeak / Neural Audio | Native ARM | `POST /v1/audio/speech` | ~1.5s |
| **🔍 Vector Embeddings** | BAAI BGE-Small-en-v1.5 (896-d) | `llama.cpp` | `POST /v1/embeddings` | ~2–3s |
| **🎯 Cross-Encoder Rerank** | BAAI BGE-Reranker-Base | `llama.cpp` | `POST /v1/rerank` | ~10–12s |
| **👁️ Computer Vision** | Google MediaPipe Spatial AI | ARM CPU | `POST /v1/vision/{task}` | ~5–50ms |
| **🤖 Swades Agent** | Autonomous ReAct Loop + GitHub PRs | Node.js | `POST /v1/agent/submit` | Multi-step Async |
| **📊 Hardware Telemetry** | Linux Kernel & Battery Metrics | Python / OS | `GET /telemetry` | ~0.1ms |

---

## 💻 Universal Drop-In Code Examples

### 1. 🐍 Python
```python
import requests, json

BASE_URL = "http://192.168.29.2:8080"  # Your phone's local Wi-Fi or USB IP

# Stream Chat from Qwen 2.5 on the phone
payload = {
    "messages": [{"role": "user", "content": "Explain relativity in 10 words"}],
    "stream": True
}
res = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, stream=True)

for line in res.iter_lines(decode_unicode=True):
    if line.startswith("data: ") and "[DONE]" not in line:
        chunk = json.loads(line[6:])
        print(chunk["choices"][0]["delta"].get("content", ""), end="", flush=True)
```

### 2. 🌐 JavaScript / React / Node
```javascript
const BASE_URL = "http://192.168.29.2:8080";

// Transcribe audio recording directly on phone
const formData = new FormData();
formData.append("file", audioBlob, "audio.wav");

const res = await fetch(`${BASE_URL}/inference`, { method: "POST", body: formData });
const data = await res.json();
console.log("Transcribed Text:", data.text);
```

### 3. 📱 Flutter / Dart
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

### 4. 🦀 Rust (`tokio` + `reqwest`)
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

### 5. 🐹 Go
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

## 🚀 Quick Setup on Phone

1. **Install Termux & Dependencies**:
   ```bash
   pkg update && pkg install -y python nodejs git build-essential clang
   pip install pillow requests
   ```
2. **Start the Sovereign Gateway & Governor**:
   ```bash
   python3 mobile/gateway.py
   ```
3. **Open the Web UI**:
   Open `index.html` on any device on your Wi-Fi network and enter your phone's IP (`http://192.168.29.2:8080`).

---

*PhoneWhisper AI is 100% open-source, private, and offline-first.*
