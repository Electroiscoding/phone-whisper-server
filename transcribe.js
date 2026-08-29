/**
 * Universal JavaScript Client for Mobile Whisper AI Server
 * Works in: Node.js (v18+), Web Browsers, Next.js, React, Vue, Vanilla JS
 * Features: Zero-config Dynamic Endpoint Discovery, Permanent Global Routing.
 */

const REGISTRY_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";
const FALLBACK_ENDPOINT = "https://stands-evaluating-express-resume.trycloudflare.com/inference";

let cachedEndpoint = null;
let cachedEndpointTs = 0;

/**
 * Dynamically resolves the active Whisper inference endpoint.
 */
async function resolveEndpoint() {
  if (typeof process !== "undefined" && process.env && process.env.WHISPER_API_URL) {
    const url = process.env.WHISPER_API_URL;
    return url.endsWith("/inference") ? url : `${url.replace(/\/+$/, "")}/inference`;
  }

  const now = Date.now();
  if (cachedEndpoint && (now - cachedEndpointTs) < 60000) {
    return cachedEndpoint;
  }

  try {
    const res = await fetch(REGISTRY_URL, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data.inference) {
        cachedEndpoint = data.inference;
        cachedEndpointTs = now;
        return cachedEndpoint;
      }
    }
  } catch (e) {
    // Fallback to cached or default
  }

  return cachedEndpoint || FALLBACK_ENDPOINT;
}

/**
 * Transcribes audio using the remote mobile Whisper AI server.
 * 
 * @param {string|Buffer|Blob|File} audioInput - Audio file path (Node), Buffer (Node), or Blob/File (Browser)
 * @param {Object} options - Configuration options
 * @param {string} [options.endpoint] - Custom API endpoint URL
 * @param {string} [options.responseFormat='json'] - 'json' | 'text' | 'verbose_json' | 'srt' | 'vtt'
 * @param {number} [options.temperature=0.0] - Sampling temperature
 * @returns {Promise<Object|string>} Transcription result
 */
async function transcribe(audioInput, options = {}) {
  let endpoint = options.endpoint || await resolveEndpoint();
  if (!endpoint.endsWith("/inference")) {
    endpoint = endpoint.replace(/\/+$/, "") + "/inference";
  }

  const responseFormat = options.responseFormat || "json";
  const temperature = options.temperature !== undefined ? String(options.temperature) : "0.0";
  const temperatureInc = options.temperatureInc !== undefined ? String(options.temperatureInc) : "0.2";
  const noSpeechThold = options.noSpeechThold !== undefined ? String(options.noSpeechThold) : "0.6";

  const isBrowser = typeof window !== "undefined" && typeof window.document !== "undefined";
  const isNode = typeof process !== "undefined" && process.versions != null && process.versions.node != null;

  const formData = new FormData();
  formData.append("temperature", temperature);
  formData.append("temperature_inc", temperatureInc);
  formData.append("no_speech_thold", noSpeechThold);
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
    const errorText = await response.text().catch(() => "");
    throw new Error(`Inference failed with HTTP status ${response.status}: ${errorText || response.statusText}`);
  }

  if (responseFormat === "json" || responseFormat === "verbose_json") {
    return await response.json();
  }
  return await response.text();
}

// Node.js CLI Runner
if (typeof process !== "undefined" && process.argv && process.argv[1]) {
  const isCli = process.argv[1].endsWith("transcribe.js");
  if (isCli) {
    const args = process.argv.slice(2);
    if (args.length === 0) {
      console.log("Usage: node transcribe.js <audio_file_path> [response_format]");
      console.log("Example: node transcribe.js sample.wav json");
      process.exit(1);
    }

    const filePath = args[0];
    const fmt = args[1] || "json";

    (async () => {
      try {
        console.log(`🎙️ Resolving autonomous global endpoint...`);
        const endpoint = await resolveEndpoint();
        console.log(`🔗 Target Endpoint: ${endpoint}`);
        console.log(`⏳ Sending ${filePath} for on-device inference...`);
        const startTime = Date.now();
        const result = await transcribe(filePath, { responseFormat: fmt });
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
        console.log(`✅ Transcribed in ${elapsed}s:\n`);
        console.log(typeof result === "object" ? result.text || result : result);
      } catch (err) {
        console.error("❌ Error:", err.message);
        process.exit(1);
      }
    })();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { transcribe, resolveEndpoint };
}
