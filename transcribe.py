#!/usr/bin/env python3
"""
Universal Multi-Modal Python SDK for Mobile AI Datacenter
Supported Modes:
1. Speech-to-Text (STT)  -> transcribe()
2. SLM Chat (Streaming)  -> chat()
3. Text-to-Speech (TTS)   -> tts()
4. Vector Embeddings     -> embed(), cosine_similarity()
5. Live Telemetry        -> get_telemetry()
"""

import os
import sys
import json
import time
import math
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Iterator

BASE_ENDPOINT = os.getenv("WHISPER_API_URL", "https://black-term-8c36.botmaker583-55e.workers.dev")


def transcribe(
    audio_source: Union[str, Path, bytes],
    response_format: str = "json",
    temperature: float = 0.0,
    timeout: int = 120
) -> Union[Dict[str, Any], str]:
    """
    Transcribes audio using on-device Whisper Base.en model.
    :param audio_source: Path to audio file or raw audio bytes (WAV, MP3, OGG, M4A).
    :param response_format: 'json', 'text', 'srt', 'vtt', or 'verbose_json'.
    :param temperature: Sampling temperature (0.0 for greedy decoding).
    :return: Dict or string containing transcription.
    """
    url = f"{BASE_ENDPOINT.rstrip('/')}/inference"
    payload = {"temperature": str(temperature), "response_format": response_format}
    files = {}
    close_file = False

    if isinstance(audio_source, (str, Path)):
        audio_path = Path(audio_source)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        f = open(audio_path, "rb")
        files["file"] = (audio_path.name, f, "audio/wav")
        close_file = True
    elif isinstance(audio_source, bytes):
        files["file"] = ("audio.wav", audio_source, "audio/wav")
    else:
        raise ValueError("audio_source must be a file path (str/Path) or bytes")

    try:
        res = requests.post(url, files=files, data=payload, timeout=timeout)
        res.raise_for_status()
        if response_format in ["json", "verbose_json"]:
            return res.json()
        return res.text
    finally:
        if close_file and "file" in files:
            files["file"][1].close()


def chat(
    prompt: str,
    system_prompt: Optional[str] = "You are a helpful on-device AI assistant.",
    temperature: float = 0.7,
    max_tokens: int = 250,
    stream: bool = False,
    timeout: int = 60
) -> Union[str, Iterator[str]]:
    """
    Generates text completions using on-device Qwen 2.5 0.5B SLM.
    :param prompt: User input prompt.
    :param system_prompt: Optional system role prompt.
    :param temperature: Sampling randomness (0.0 to 1.0).
    :param max_tokens: Maximum tokens to generate.
    :param stream: If True, yields tokens in real-time as an Iterator.
    :return: Full string or Token Iterator.
    """
    url = f"{BASE_ENDPOINT.rstrip('/')}/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }

    headers = {"Content-Type": "application/json"}
    if stream:
        headers["Accept"] = "text/event-stream"
        def stream_generator() -> Iterator[str]:
            res = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout)
            res.raise_for_status()
            for line in res.iter_lines(decode_unicode=True):
                if line:
                    line = line.strip()
                    if "[DONE]" in line:
                        break
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass
        return stream_generator()
    else:
        res = requests.post(url, json=payload, headers=headers, timeout=timeout)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()


def tts(
    text: str,
    output_path: Optional[Union[str, Path]] = "output.wav",
    speed: float = 1.0,
    timeout: int = 30
) -> bytes:
    """
    Synthesizes text into speech WAV audio bytes on-device in ~50ms.
    :param text: Text string to convert to speech.
    :param output_path: Optional local path to save WAV file.
    :param speed: Speech playback rate multiplier (0.75 - 1.5).
    :return: Raw audio WAV bytes.
    """
    url = f"{BASE_ENDPOINT.rstrip('/')}/v1/audio/speech"
    payload = {"input": text, "speed": speed}
    res = requests.post(url, json=payload, timeout=timeout)
    res.raise_for_status()
    audio_bytes = res.content
    if output_path:
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
    return audio_bytes


def embed(
    text: str,
    timeout: int = 30
) -> List[float]:
    """
    Generates an 896-dimensional dense vector embedding.
    :param text: Input sentence or document.
    :return: List of 896 floating-point values.
    """
    url = f"{BASE_ENDPOINT.rstrip('/')}/v1/embeddings"
    payload = {"input": text}
    res = requests.post(url, json=payload, timeout=timeout)
    res.raise_for_status()
    data = res.json()
    return data["data"][0]["embedding"]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def get_telemetry(timeout: int = 10) -> Dict[str, Any]:
    """
    Fetches real-time Android kernel battery, CPU load, and RAM telemetry.
    :return: Telemetry dictionary.
    """
    url = f"{BASE_ENDPOINT.rstrip('/')}/telemetry"
    res = requests.get(url, timeout=timeout)
    res.raise_for_status()
    return res.json()


# ==============================================================================
# CLI Entry Point
# ==============================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Mobile AI Datacenter SDK")
    subparsers = parser.add_subparsers(dest="command", help="AI Mode to execute")

    # STT Subcommand
    stt_p = subparsers.add_parser("transcribe", help="Transcribe audio file")
    stt_p.add_argument("file", help="Audio file path")
    stt_p.add_argument("--format", default="json", choices=["json", "text", "srt", "vtt", "verbose_json"])

    # Chat Subcommand
    chat_p = subparsers.add_parser("chat", help="Chat with Qwen 2.5 SLM")
    chat_p.add_argument("prompt", help="User prompt")
    chat_p.add_argument("--no-stream", action="store_true", help="Disable token streaming")

    # TTS Subcommand
    tts_p = subparsers.add_parser("tts", help="Synthesize text to speech")
    tts_p.add_argument("text", help="Text to speak")
    tts_p.add_argument("output", nargs="?", default="output.wav", help="Output file path (default: output.wav)")
    tts_p.add_argument("--output", dest="out_flag", default=None, help="Output file flag")
    tts_p.add_argument("--speed", type=float, default=1.0, help="Speech rate")

    # Embeddings Subcommand
    emb_p = subparsers.add_parser("embed", help="Generate vector embeddings")
    emb_p.add_argument("text", help="Text to embed")

    # Telemetry Subcommand
    subparsers.add_parser("telemetry", help="Get real-time hardware telemetry")

    args = parser.parse_args()

    print("=" * 50)
    print("🚀 Mobile AI Datacenter — Universal Python CLI")
    print(f"🔗 Permanent Endpoint: {BASE_ENDPOINT}")
    print("=" * 50)

    if args.command == "transcribe":
        print(f"🎙️ Transcribing {args.file} (Format: {args.format})...")
        t0 = time.time()
        res = transcribe(args.file, response_format=args.format)
        elapsed = time.time() - t0
        print(f"✅ Transcribed in {elapsed:.2f}s:")
        print(res if isinstance(res, str) else json.dumps(res, indent=2))

    elif args.command == "chat":
        print(f"💬 Asking Qwen 2.5 SLM: \"{args.prompt}\"...\n")
        t0 = time.time()
        if args.no_stream:
            reply = chat(args.prompt, stream=False)
            print(f"✅ Generated in {time.time()-t0:.2f}s:\n{reply}")
        else:
            token_count = 0
            for token in chat(args.prompt, stream=True):
                sys.stdout.write(token)
                sys.stdout.flush()
                token_count += 1
            print(f"\n\n⚡ Streamed in {time.time()-t0:.2f}s (~{token_count/(max(0.1, time.time()-t0)):.1f} tokens/s)")

    elif args.command == "tts":
        out_file = args.out_flag or args.output or "output.wav"
        print(f"🗣️ Synthesizing: \"{args.text}\"...")
        t0 = time.time()
        data = tts(args.text, output_path=out_file, speed=args.speed)
        print(f"✅ Generated {len(data):,} bytes in {time.time()-t0:.2f}s -> Saved to {out_file}")

    elif args.command == "embed":
        print(f"🔍 Generating vector embeddings for: \"{args.text}\"...")
        t0 = time.time()
        vec = embed(args.text)
        print(f"✅ Generated {len(vec)}-dimensional float vector in {time.time()-t0:.2f}s.")
        print(f"Preview: {vec[:5]} ...")

    elif args.command == "telemetry":
        print("📊 Querying live phone hardware metrics...")
        t = get_telemetry()
        bat = t.get("battery", {})
        mem = t.get("memory", {})
        cpu = t.get("cpu", {})
        print(f"🔋 Battery: {bat.get('level')}% ({bat.get('status')}) | Temp: {bat.get('temperature')}°C | Voltage: {bat.get('voltage_mv')} mV")
        print(f"⚡ CPU Usage: {cpu.get('usage_percent')}% (Cores: {cpu.get('cores')}, Active Daemon: {cpu.get('active_daemon')})")
        print(f"🧠 RAM: {mem.get('used_mb')} MB used / {mem.get('total_mb')} MB total ({mem.get('available_mb')} MB free)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
