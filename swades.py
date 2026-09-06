"""
⚡ Swades Cloud Python SDK — Hyper-Fast Sovereign Firebase Alternative
1-line CRUD, S3 Object Storage with instant CDN, Auth & Scoped Keys.
"""
import requests
import json
import os

class Swades:
    def __init__(self, api_key="", project_id="default", endpoint="https://phone-whisper-server.pages.dev"):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.project_id = project_id
        self.headers = {
            "x-api-key": self.api_key,
            "x-project-id": self.project_id,
            "Content-Type": "application/json"
        }

    # 1-line SQL query
    def query(self, sql_query, **kwargs):
        res = requests.post(
            f"{self.endpoint}/v1/dashboard/db/sql",
            headers=self.headers,
            json={"query": sql_query, "project_id": self.project_id, **kwargs}
        )
        data = res.json()
        if not res.ok or data.get("status") == "error":
            raise RuntimeError(data.get("error", "SQL Query Failed"))
        return data.get("result", {}).get("rows", [])

    # Insert row
    def insert(self, table, record_dict):
        res = requests.post(
            f"{self.endpoint}/v1/dashboard/db/query",
            headers=self.headers,
            json={
                "action": "insert_row",
                "table": table,
                "data": record_dict,
                "project_id": self.project_id
            }
        )
        return res.json()

    # Upload file
    def upload(self, file_path, custom_key=None):
        filename = os.path.basename(file_path)
        key = custom_key or f"uploads/{filename}"
        with open(file_path, "rb") as f:
            content = f.read()
        headers = {
            "x-api-key": self.api_key,
            "x-project-id": self.project_id,
            "Content-Type": "application/octet-stream"
        }
        res = requests.put(f"{self.endpoint}/v1/storage/objects/{key}", headers=headers, data=content)
        data = res.json()
        return data.get("object", {}).get("url", f"{self.endpoint}/s/{self.project_id}/{key}")

    # 1-line Speech Synthesis (Kokoro-82M Multi-Voice TTS)
    def tts(self, text, voice="af_heart", speed=1.0, quality="auto", response_format="wav"):
        """Synthesizes text into speech audio bytes (Hot Latent Vault or Realtime Native)"""
        res = requests.post(
            f"{self.endpoint}/v1/audio/speech",
            headers=self.headers,
            json={
                "input": text,
                "voice": voice,
                "speed": speed,
                "quality": quality,
                "response_format": response_format
            },
            timeout=120
        )
        if not res.ok:
            raise RuntimeError(f"Speech synthesis failed: HTTP {res.status_code} - {res.text}")
        return res.content

    def tts_to_file(self, text, output_path, voice="af_heart", speed=1.0):
        """Synthesizes speech and writes directly to audio file (.wav)"""
        audio_bytes = self.tts(text, voice=voice, speed=speed)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return output_path

    # List all supported Kokoro neural voices
    def voices(self):
        """Returns the full catalogue of supported Kokoro-82M neural voices"""
        res = requests.get(f"{self.endpoint}/v1/audio/voices", timeout=10)
        return res.json().get("voices", [])
