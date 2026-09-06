"""
⚡ Swades Cloud Python SDK — Hyper-Fast Sovereign Firebase Alternative
1-line CRUD, S3 Object Storage with instant CDN, Auth & Scoped Keys.
"""
import requests
import json
import os
import time
import hashlib
import urllib.parse

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
        self._tts_cache = {}
        self._cache_dir = os.path.expanduser("~/.swades/tts_cache")
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
        except Exception:
            pass

    def _req(self, method, path, **kwargs):
        """Auto-recovering request helper with exponential backoff on edge tunnel reconnection"""
        url = f"{self.endpoint}{path}" if path.startswith("/") else f"{self.endpoint}/{path}"
        timeout = kwargs.pop("timeout", 30)
        for attempt in range(3):
            try:
                res = requests.request(method, url, timeout=timeout, **kwargs)
                if res.status_code == 503 and "reconnecting" in res.text and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return res
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise e

    # 1-line SQL query
    def query(self, sql_query, **kwargs):
        res = self._req(
            "POST",
            "/v1/dashboard/db/sql",
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

    # 1-line Speech Synthesis (Kokoro-82M Multi-Voice TTS with Hyper-Speed Caching)
    def tts(self, text, voice="af_heart", speed=1.0, quality="auto", response_format="wav", use_cache=True):
        """Synthesizes text into speech audio bytes (Tier 0 Local Cache -> Tier 1 Cloudflare Edge -> Tier 2 Hot Vault)"""
        norm_voice = (voice or "af_heart").strip().lower()
        norm_speed = float(speed or 1.0)
        norm_text = " ".join(str(text).strip().lower().split())
        cache_key = hashlib.sha256(f"{norm_voice}_{norm_speed:.2f}_{norm_text}".encode("utf-8")).hexdigest()

        # Tier 0A: In-Memory Cache (<0.01ms)
        if use_cache and cache_key in self._tts_cache:
            return self._tts_cache[cache_key]

        # Tier 0B: Local Disk Cache (<1ms)
        disk_path = os.path.join(self._cache_dir, f"{cache_key}.{response_format}")
        if use_cache and os.path.exists(disk_path) and os.path.getsize(disk_path) > 0:
            try:
                with open(disk_path, "rb") as f:
                    data = f.read()
                self._tts_cache[cache_key] = data
                return data
            except Exception:
                pass

        # Network Request (Edge Cache <5ms -> Hot Vault <15ms -> Native <40ms)
        res = self._req(
            "POST",
            "/v1/audio/speech",
            headers=self.headers,
            json={
                "input": text,
                "voice": norm_voice,
                "speed": norm_speed,
                "quality": quality,
                "response_format": response_format
            },
            timeout=120
        )
        if not res.ok:
            raise RuntimeError(f"Speech synthesis failed: HTTP {res.status_code} - {res.text}")

        audio_bytes = res.content

        # Populate Tier 0 Caches
        if use_cache and audio_bytes:
            self._tts_cache[cache_key] = audio_bytes
            try:
                with open(disk_path, "wb") as f:
                    f.write(audio_bytes)
            except Exception:
                pass

        return audio_bytes

    def speak(self, text, voice="af_heart", speed=1.0, quality="auto", response_format="wav", use_cache=True):
        """Convenience alias for tts()"""
        return self.tts(text, voice=voice, speed=speed, quality=quality, response_format=response_format, use_cache=use_cache)

    def tts_to_file(self, text, output_path, voice="af_heart", speed=1.0, use_cache=True):
        """Synthesizes speech and writes directly to audio file (.wav)"""
        audio_bytes = self.tts(text, voice=voice, speed=speed, use_cache=use_cache)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return output_path

    def get_audio_url(self, text, voice="af_heart", speed=1.0, response_format="wav"):
        """Generates an edge-cacheable GET URL for direct streaming or embedding in web apps"""
        q = urllib.parse.urlencode({
            "input": text,
            "voice": (voice or "af_heart").strip().lower(),
            "speed": f"{float(speed or 1.0):.2f}",
            "response_format": response_format
        })
        return f"{self.endpoint}/v1/audio/speech?{q}"

    def clear_tts_cache(self):
        """Clears local memory and disk TTS caches"""
        self._tts_cache.clear()
        if os.path.exists(self._cache_dir):
            for fname in os.listdir(self._cache_dir):
                try:
                    os.remove(os.path.join(self._cache_dir, fname))
                except Exception:
                    pass

    # List all supported Kokoro neural voices
    def voices(self):
        """Returns the full catalogue of supported Kokoro-82M neural voices"""
        res = self._req("GET", "/v1/audio/voices", timeout=10)
        return res.json().get("voices", [])
