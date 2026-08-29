#!/usr/bin/env python3
"""
Universal Multi-Modal Python SDK for Mobile AI Datacenter
Supported Modes:
1. Speech-to-Text (STT)  -> transcribe()
2. SLM Chat              -> chat()
3. Text-to-Speech (TTS)   -> tts()
4. Vector Embeddings     -> embed()
5. Live Telemetry        -> get_telemetry()
"""

import os
import sys
import time
import math
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Union, List

BASE_ENDPOINT = os.getenv("WHISPER_API_URL", "https://black-term-8c36.botmaker583-55e.workers.dev")


def transcribe(
    audio_source: Union[str, Path, bytes],
    response_format: str = "json",
    temperature: float = 0.0,
    timeout: int = 120
) -> Union[Dict[str, Any], str]:
    """Transcribes audio using on-device Whisper Base.en model."""
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
    max_tokens: int = 150,
    timeout: int = 60
) -> str:
    """Generates text completions using on-device Qwen 2.5 0.5B SLM."""
    url = f"{BASE_ENDPOINT.rstrip('/')}/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    res = requests.post(url, json=payload, timeout=timeout)
    res.raise_for_status()
    data = res.json()
    return data["choices"][0]["message"]["content"].strip()


def tts(
    text: str,
    output_path: Optional[Union[str, Path]] = "output.wav",
    speed: float = 1.0,
    timeout: int = 30
) -> bytes:
    """Synthesizes text into speech WAV audio bytes on-device."""
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
    text: Union[str, List[str]],
    timeout: int = 30
) -> List[float]:
    """Generates dense vector embeddings using on-device Qwen 2.5 model."""
    url = f"{BASE_ENDPOINT.rstrip('/')}/v1/embeddings"
    payload = {"input": text}
    res = requests.post(url, json=payload, timeout=timeout)
    res.raise_for_status()
    data = res.json()
    return data["data"][0]["embedding"]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two embedding vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


def get_telemetry(timeout: int = 10) -> Dict[str, Any]:
    """Fetches real-time Android kernel battery & RAM telemetry."""
    url = f"{BASE_ENDPOINT.rstrip('/')}/telemetry"
    res = requests.get(url, timeout=timeout)
    res.raise_for_status()
    return res.json()


def main():
    print("==================================================")
    print("🚀 Mobile AI Datacenter — Universal Python CLI")
    print(f"🔗 Permanent Endpoint: {BASE_ENDPOINT}")
    print("==================================================")

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python transcribe.py transcribe <audio.wav>")
        print("  python transcribe.py chat \"Why is the sky blue?\"")
        print("  python transcribe.py tts \"Hello world from phone\" [output.wav]")
        print("  python transcribe.py embed \"Semantic search text\"")
        print("  python transcribe.py telemetry")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "transcribe" and len(sys.argv) > 2:
        audio_file = sys.argv[2]
        print(f"🎙️ Transcribing {audio_file} with Whisper Base.en...")
        t0 = time.time()
        res = transcribe(audio_file)
        print(f"✅ Transcribed in {time.time()-t0:.2f}s:\n{res.get('text', res) if isinstance(res, dict) else res}")

    elif cmd == "chat" and len(sys.argv) > 2:
        prompt = sys.argv[2]
        print(f"💬 Asking Qwen 2.5 SLM: \"{prompt}\"...")
        t0 = time.time()
        reply = chat(prompt)
        print(f"✅ Generated in {time.time()-t0:.2f}s:\n{reply}")

    elif cmd == "tts" and len(sys.argv) > 2:
        text = sys.argv[2]
        out_file = sys.argv[3] if len(sys.argv) > 3 else "speech.wav"
        print(f"🗣️ Synthesizing speech for: \"{text}\"...")
        t0 = time.time()
        tts(text, out_file)
        print(f"✅ Saved audio to {out_file} in {time.time()-t0:.2f}s")

    elif cmd == "embed" and len(sys.argv) > 2:
        text = sys.argv[2]
        print(f"🔍 Generating vector embedding for: \"{text}\"...")
        t0 = time.time()
        vec = embed(text)
        print(f"✅ Generated {len(vec)}-dimensional vector in {time.time()-t0:.2f}s. Preview: {vec[:5]}...")

    elif cmd == "telemetry":
        print(f"📊 Querying live phone hardware metrics...")
        stats = get_telemetry()
        bat = stats.get("battery", {})
        mem = stats.get("memory", {})
        print(f"🔋 Battery: {bat.get('level')}% ({bat.get('status')}) | Temp: {bat.get('temperature')}°C | Voltage: {bat.get('voltage_mv')} mV")
        print(f"🧠 RAM: {mem.get('used_mb')} MB used / {mem.get('total_mb')} MB total ({mem.get('available_mb')} MB free)")

    else:
        # Backward compatibility for direct file argument
        audio_file = sys.argv[1]
        print(f"🎙️ Transcribing {audio_file}...")
        res = transcribe(audio_file)
        print(res.get("text", res) if isinstance(res, dict) else res)


if __name__ == "__main__":
    main()
