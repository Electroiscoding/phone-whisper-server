/**
 * Universal JavaScript Client for Mobile Whisper AI Server
 * Works in: Node.js (v18+), Web Browsers, Next.js, React, Vue, Vanilla JS
 * Zero external dependencies.
 */

const DEFAULT_ENDPOINT = "https://hardly-assembly-guides-cache.trycloudflare.com/inference";

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
  let endpoint = options.endpoint || (typeof process !== "undefined" && process.env && process.env.WHISPER_API_URL) || DEFAULT_ENDPOINT;
  if (!endpoint.endsWith("/inference")) {
    endpoint = endpoint.replace(/\/+$/, "") + "/inference";
  }

  const responseFormat = options.responseFormat || "json";
  const temperature = options.temperature !== undefined ? options.temperature : 0.0;

  const formData = new FormData();
  formData.append("temperature", String(temperature));
  formData.append("response_format", responseFormat);

  // Check environment: Node.js vs Browser
  const isNode = typeof process !== "undefined" && process.versions != null && process.versions.node != null;

  if (isNode && typeof audioInput === "string") {
    // Node.js file path
    const fs = await import("node:fs");
    const path = await import("node:path");
    if (!fs.existsSync(audioInput)) {
      throw new Error(`File not found: ${audioInput}`);
    }
    const fileBuffer = fs.readFileSync(audioInput);
    const fileName = path.basename(audioInput);
    const blob = new Blob([fileBuffer]);
    formData.append("file", blob, fileName);
  } else if (isNode && Buffer.isBuffer(audioInput)) {
    // Node.js Buffer
    const blob = new Blob([audioInput]);
    formData.append("file", blob, "audio.wav");
  } else if (typeof Blob !== "undefined" && audioInput instanceof Blob) {
    // Browser Blob or File
    const fileName = audioInput.name || "recording.wav";
    formData.append("file", audioInput, fileName);
  } else {
    throw new Error("Invalid audio input. Must be a file path, Buffer, Blob, or File.");
  }

  const response = await fetch(endpoint, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errText = await response.text().catch(() => "");
    throw new Error(`Server returned error ${response.status}: ${errText || response.statusText}`);
  }

  if (responseFormat === "json" || responseFormat === "verbose_json") {
    return await response.json();
  }
  return await response.text();
}

// Node.js CLI execution handler
if (typeof process !== "undefined" && process.argv && process.argv[1] && process.argv[1].endsWith("transcribe.js")) {
  const args = process.argv.slice(2);
  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    console.log("Usage: node transcribe.js <audio_file_path> [--format <json|text|srt|vtt>] [--endpoint <url>]");
    process.exit(args.length === 0 ? 1 : 0);
  }

  const filePath = args[0];
  let format = "json";
  let endpoint = DEFAULT_ENDPOINT;

  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--format" || args[i] === "-f") format = args[++i];
    if (args[i] === "--endpoint" || args[i] === "-e") endpoint = args[++i];
  }

  console.log(`Connecting to: ${endpoint}`);
  console.log(`Transcribing: ${filePath} ...`);

  transcribe(filePath, { endpoint, responseFormat: format })
    .then((result) => {
      console.log("\n--- Transcription Result ---");
      if (typeof result === "object") {
        console.log(result.text || JSON.stringify(result, null, 2));
      } else {
        console.log(result.trim());
      }
    })
    .catch((err) => {
      console.error("\n[ERROR] Transcription failed:", err.message);
      process.exit(1);
    });
}

// Export for ES modules and CommonJS
if (typeof module !== "undefined" && module.exports) {
  module.exports = { transcribe, DEFAULT_ENDPOINT };
}
