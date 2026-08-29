/**
 * Universal Multi-Modal JavaScript SDK for Mobile AI Datacenter
 * Works in: Node.js (v18+), React, Vue, Next.js, Web Browsers
 * Supported Modes:
 * 1. STT: transcribe()
 * 2. SLM: chat()
 * 3. TTS: tts()
 * 4. Embeddings: embed(), cosineSimilarity()
 * 5. Telemetry: getTelemetry()
 */

const BASE_ENDPOINT = (typeof process !== "undefined" && process.env && process.env.WHISPER_API_URL)
  ? process.env.WHISPER_API_URL
  : "https://black-term-8c36.botmaker583-55e.workers.dev";

/**
 * Transcribes audio using on-device Whisper Base.en model.
 */
async function transcribe(audioInput, options = {}) {
  const endpoint = `${BASE_ENDPOINT.replace(/\/+$/, "")}/inference`;
  const responseFormat = options.responseFormat || "json";
  const temperature = options.temperature !== undefined ? String(options.temperature) : "0.0";

  const isBrowser = typeof window !== "undefined" && typeof window.document !== "undefined";
  const isNode = typeof process !== "undefined" && process.versions != null && process.versions.node != null;

  const formData = new FormData();
  formData.append("temperature", temperature);
  formData.append("response_format", responseFormat);

  if (isBrowser) {
    if (audioInput instanceof Blob || audioInput instanceof File) {
      formData.append("file", audioInput, "audio.wav");
    } else {
      throw new Error("In browser environment, audioInput must be a Blob or File instance.");
    }
  } else if (isNode) {
    if (typeof audioInput === "string") {
      const fs = await import("fs");
      const path = await import("path");
      const fileBuffer = fs.readFileSync(audioInput);
      const filename = path.basename(audioInput);
      const fileBlob = new Blob([fileBuffer], { type: "audio/wav" });
      formData.append("file", fileBlob, filename);
    } else if (Buffer.isBuffer(audioInput)) {
      const fileBlob = new Blob([audioInput], { type: "audio/wav" });
      formData.append("file", fileBlob, "audio.wav");
    } else if (audioInput instanceof Blob) {
      formData.append("file", audioInput, "audio.wav");
    } else {
      throw new Error("In Node.js, audioInput must be a file path string, Buffer, or Blob.");
    }
  }

  const response = await fetch(endpoint, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Inference failed with HTTP ${response.status}`);
  }

  return responseFormat === "json" || responseFormat === "verbose_json"
    ? await response.json()
    : await response.text();
}

/**
 * Generates chat completion using on-device Qwen 2.5 0.5B SLM.
 */
async function chat(prompt, options = {}) {
  const endpoint = `${BASE_ENDPOINT.replace(/\/+$/, "")}/v1/chat/completions`;
  const messages = [];
  if (options.systemPrompt) {
    messages.push({ role: "system", content: options.systemPrompt });
  }
  messages.push({ role: "user", content: prompt });

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      temperature: options.temperature !== undefined ? options.temperature : 0.7,
      max_tokens: options.maxTokens || 150,
    }),
  });

  if (!response.ok) throw new Error(`Chat failed with HTTP ${response.status}`);
  const data = await response.json();
  return data.choices[0].message.content.trim();
}

/**
 * Synthesizes text to speech audio bytes on-device.
 */
async function tts(text, options = {}) {
  const endpoint = `${BASE_ENDPOINT.replace(/\/+$/, "")}/v1/audio/speech`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: text, speed: options.speed || 1.0 }),
  });

  if (!response.ok) throw new Error(`TTS failed with HTTP ${response.status}`);
  return await response.arrayBuffer();
}

/**
 * Generates dense vector embeddings.
 */
async function embed(text) {
  const endpoint = `${BASE_ENDPOINT.replace(/\/+$/, "")}/v1/embeddings`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: text }),
  });

  if (!response.ok) throw new Error(`Embeddings failed with HTTP ${response.status}`);
  const data = await response.json();
  return data.data[0].embedding;
}

/**
 * Computes cosine similarity between two vector embeddings.
 */
function cosineSimilarity(v1, v2) {
  let dot = 0, n1 = 0, n2 = 0;
  for (let i = 0; i < v1.length; i++) {
    dot += v1[i] * v2[i];
    n1 += v1[i] * v1[i];
    n2 += v2[i] * v2[i];
  }
  return dot / (Math.sqrt(n1) * Math.sqrt(n2));
}

/**
 * Fetches real-time Android kernel battery and RAM telemetry.
 */
async function getTelemetry() {
  const endpoint = `${BASE_ENDPOINT.replace(/\/+$/, "")}/telemetry`;
  const response = await fetch(endpoint);
  if (!response.ok) throw new Error(`Telemetry failed with HTTP ${response.status}`);
  return await response.json();
}

// Node.js CLI Runner
if (typeof process !== "undefined" && process.argv && process.argv[1]) {
  const isCli = process.argv[1].endsWith("transcribe.js");
  if (isCli) {
    const args = process.argv.slice(2);
    const cmd = (args[0] || "").toLowerCase();

    (async () => {
      try {
        console.log(`🚀 Mobile AI Datacenter — Universal JS SDK`);
        console.log(`🔗 Permanent Endpoint: ${BASE_ENDPOINT}`);

        if (cmd === "chat" && args[1]) {
          console.log(`💬 Asking Qwen 2.5: "${args[1]}"...`);
          const reply = await chat(args[1]);
          console.log(`✅ Response:\n${reply}`);
        } else if (cmd === "embed" && args[1]) {
          console.log(`🔍 Generating vector embedding for "${args[1]}"...`);
          const vec = await embed(args[1]);
          console.log(`✅ ${vec.length}-dim vector generated. Preview:`, vec.slice(0, 5));
        } else if (cmd === "telemetry") {
          const t = await getTelemetry();
          console.log("📊 Telemetry:", JSON.stringify(t, null, 2));
        } else if (args[0]) {
          console.log(`🎙️ Transcribing ${args[0]}...`);
          const res = await transcribe(args[0]);
          console.log(typeof res === "object" ? res.text || res : res);
        } else {
          console.log("Usage: node transcribe.js [transcribe <file.wav> | chat \"prompt\" | embed \"text\" | telemetry]");
        }
      } catch (err) {
        console.error("❌ Error:", err.message);
      }
    })();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { transcribe, chat, tts, embed, cosineSimilarity, getTelemetry };
}
