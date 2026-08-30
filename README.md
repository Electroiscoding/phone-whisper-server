# 📱 PhoneWhisper AI — Turning an Old Android Phone into a Self-Hosted AI Server

> **An honest, open-source hacker experiment:** Running multi-modal AI models (OpenAI Whisper, Qwen 2.5, BAAI BGE Embeddings, BGE Reranker, and Google MediaPipe) on a spare **$70 Redmi 9i (MediaTek Helio G25, 4GB RAM)** running Termux, exposed to the web via Cloudflare Tunnels.

---

## 💡 The Reality (No Marketing Hype)

* **Hardware:** A single budget Android smartphone (Redmi 9i) with 8x ARM Cortex-A53 CPU cores and 4GB RAM (~2GB free after Android OS).
* **Software Stack:** Linux inside Termux, `llama.cpp`, `whisper.cpp`, `espeak`, `Pillow`, `cloudflared`, and a lightweight Python process supervisor (`gateway.py`).
* **Memory Management:** Because the phone cannot keep multiple heavy neural networks in RAM simultaneously, `gateway.py` automatically spawns the requested model when a request arrives and **terminates (`pkill`) idle models after 75 seconds of silence**.
* **Latency & Compute:**
  * **Edge Ping:** ~35ms round-trip to Cloudflare's Anycast network.
  * **On-Phone CPU Compute Times:**
    * 🎙️ **Whisper STT:** ~5–15 seconds per audio clip (ARM NEON quantized).
    * 💬 **Qwen 2.5 0.5B Chat:** ~10–20 tokens/sec (~8–12 seconds total generation).
    * 🔍 **Vector Embeddings (BGE-Small):** ~2–3 seconds per text.
    * 🎯 **Cross-Attention Reranker (BGE-Reranker-Base):** ~10–12 seconds per query.
    * 👁️ **Google MediaPipe Vision:** ~5–50ms on CPU.

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
| **📊 Hardware Telemetry** | Linux Kernel Metrics | Python / OS | `GET /telemetry` | ~0.1ms |

---

## 💻 Universal Drop-In Code Examples

### 1. 🐍 Python
```python
import requests, json

BASE_URL = "https://black-term-8c36.botmaker583-55e.workers.dev"

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

### 2. 🌐 JavaScript / React
```javascript
const BASE_URL = "https://black-term-8c36.botmaker583-55e.workers.dev";

// Transcribe audio recording
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
    Uri.parse("https://black-term-8c36.botmaker583-55e.workers.dev/v1/chat/completions"),
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
        .get("https://black-term-8c36.botmaker583-55e.workers.dev/telemetry")
        .send().await?
        .json().await?;
    println!("🔋 Phone Battery: {}%", res["battery"]["level"]);
    Ok(())
}
```

---

## 📱 How to Host This on Your Own Android Phone

1. **Install Termux** (from F-Droid or GitHub Releases).
2. **Install Packages**:
   ```bash
   pkg update && pkg install -y git clang cmake cloudflared tmux espeak python
   ```
3. **Clone Repo & Build C++ Binaries**:
   ```bash
   git clone --recursive https://github.com/Electroiscoding/phone-whisper-server
   cd phone-whisper-server
   ```
4. **Start the Supervisor**:
   ```bash
   python3 mobile/nuclear_watchdog.py
   ```

---

## 📄 License
MIT License • Open Source Hacker Experiment by [Soham (@Electroiscoding)](https://github.com/Electroiscoding)
