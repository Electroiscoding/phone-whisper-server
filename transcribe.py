#!/usr/bin/env python3
"""
Universal Python Client for Mobile Whisper AI Server
Works on: Windows, Linux, macOS, Google Colab, Jupyter Notebook, Cloud Servers
"""

import sys
import os
import argparse
import json
from typing import Union

try:
    import requests
except ImportError:
    print("Error: 'requests' library is not installed. Install it with: pip install requests", file=sys.stderr)
    sys.exit(1)

# Default public endpoint (can be overridden via argument or env var WHISPER_API_URL)
DEFAULT_ENDPOINT = os.getenv(
    "WHISPER_API_URL",
    "https://consumer-capacity-replies-adams.trycloudflare.com/inference"
)


def transcribe(
    audio_source: Union[str, bytes],
    endpoint: str = DEFAULT_ENDPOINT,
    response_format: str = "json",
    temperature: float = 0.0,
    temperature_inc: float = 0.2,
    timeout: int = 120
) -> Union[dict, str]:
    """
    Transcribes audio using the remote Whisper server.

    :param audio_source: Path to an audio file (str) or raw audio bytes.
    :param endpoint: Full HTTPS URL to /inference endpoint.
    :param response_format: 'json', 'text', 'verbose_json', 'srt', or 'vtt'.
    :param temperature: Sampling temperature (default 0.0 for deterministic).
    :param temperature_inc: Temperature fallback increment.
    :param timeout: Request timeout in seconds.
    :return: Parsed JSON dict or raw string depending on response_format.
    """
    if not endpoint.endswith("/inference"):
        endpoint = endpoint.rstrip("/") + "/inference"

    data = {
        "temperature": str(temperature),
        "temperature_inc": str(temperature_inc),
        "response_format": response_format
    }

    if isinstance(audio_source, str):
        if not os.path.exists(audio_source):
            raise FileNotFoundError(f"Audio file not found: {audio_source}")
        with open(audio_source, "rb") as f:
            files = {"file": (os.path.basename(audio_source), f)}
            response = requests.post(endpoint, files=files, data=data, timeout=timeout)
    elif isinstance(audio_source, (bytes, bytearray)):
        files = {"file": ("audio.wav", audio_source)}
        response = requests.post(endpoint, files=files, data=data, timeout=timeout)
    else:
        raise ValueError("audio_source must be a file path (str) or audio bytes.")

    response.raise_for_status()

    if response_format in ["json", "verbose_json"]:
        return response.json()
    return response.text


def main():
    parser = argparse.ArgumentParser(
        description="Universal Whisper Client - Transcribe audio files from anywhere"
    )
    parser.add_argument("audio_file", help="Path to the audio file (WAV, MP3, OGG, M4A, etc.)")
    parser.add_argument(
        "--endpoint",
        "-e",
        default=DEFAULT_ENDPOINT,
        help=f"Whisper inference endpoint URL (default: {DEFAULT_ENDPOINT})"
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "text", "verbose_json", "srt", "vtt"],
        default="json",
        help="Response format (default: json)"
    )
    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0)"
    )

    args = parser.parse_args()

    try:
        print(f"Connecting to: {args.endpoint}")
        print(f"Transcribing: {args.audio_file} ...")
        result = transcribe(
            args.audio_file,
            endpoint=args.endpoint,
            response_format=args.format,
            temperature=args.temperature
        )

        if isinstance(result, dict):
            print("\n--- Transcription Result ---")
            print(result.get("text", json.dumps(result, indent=2)).strip())
        else:
            print("\n--- Transcription Result ---")
            print(result.strip())

    except Exception as err:
        print(f"\n[ERROR] Transcription failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
