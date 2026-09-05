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
