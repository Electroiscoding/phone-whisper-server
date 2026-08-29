#!/usr/bin/env python3
"""
Universal Python Client for Mobile Whisper AI Server
Works in: Google Colab, Jupyter Notebooks, Local Terminals, AWS Lambda, FastAPI, Flask
Features: Zero-config Dynamic Endpoint Discovery, Permanent Global Routing.
"""

import os
import sys
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Union

REGISTRY_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json"
FALLBACK_ENDPOINT = "https://black-term-8c36.botmaker583-55e.workers.dev/inference"

_cached_endpoint: Optional[str] = None
_cached_endpoint_ts: float = 0.0


def resolve_endpoint() -> str:
    """
    Dynamically resolves the active global Whisper inference endpoint.
    Checks environment variable -> Local Cache -> Dynamic GitHub Registry -> Fallback.
    """
    global _cached_endpoint, _cached_endpoint_ts

    env_url = os.getenv("WHISPER_API_URL")
    if env_url:
        return env_url if env_url.endswith("/inference") else f"{env_url.rstrip('/')}/inference"

    now = time.time()
    if _cached_endpoint and (now - _cached_endpoint_ts) < 60:
        return _cached_endpoint

    try:
        res = requests.get(REGISTRY_URL, timeout=4)
        if res.ok:
            data = res.json()
            inference_url = data.get("inference")
            if inference_url:
                _cached_endpoint = inference_url
                _cached_endpoint_ts = now
                return _cached_endpoint
    except Exception:
        pass

    return _cached_endpoint or FALLBACK_ENDPOINT


def transcribe(
    audio_source: Union[str, Path, bytes],
    endpoint: Optional[str] = None,
    response_format: str = "json",
    temperature: float = 0.0,
    temperature_inc: float = 0.2,
    no_speech_thold: float = 0.6,
    timeout: int = 120
) -> Union[Dict[str, Any], str]:
    """
    Transcribes audio by calling the remote mobile AI server.
    """
    target_url = endpoint or resolve_endpoint()
    if not target_url.endswith("/inference"):
        target_url = f"{target_url.rstrip('/')}/inference"

    payload_data = {
        "temperature": str(temperature),
        "temperature_inc": str(temperature_inc),
        "no_speech_thold": str(no_speech_thold),
        "response_format": response_format
    }

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
        response = requests.post(
            target_url,
            files=files,
            data=payload_data,
            timeout=timeout
        )
        response.raise_for_status()

        if response_format in ["json", "verbose_json"]:
            return response.json()
        return response.text
    finally:
        if close_file and "file" in files:
            files["file"][1].close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <path_to_audio_file> [response_format]")
        print("Example: python transcribe.py sample.wav json")
        sys.exit(1)

    file_path = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else "json"

    print(f"🎙️ Resolving autonomous global endpoint...")
    endpoint = resolve_endpoint()
    print(f"🔗 Target Endpoint: {endpoint}")
    print(f"⏳ Sending {file_path} for on-device inference...")

    start_time = time.time()
    result = transcribe(file_path, response_format=fmt)
    elapsed = time.time() - start_time

    print(f"✅ Transcribed in {elapsed:.2f}s:\n")
    if isinstance(result, dict):
        print(result.get("text", result))
    else:
        print(result)


if __name__ == "__main__":
    main()
