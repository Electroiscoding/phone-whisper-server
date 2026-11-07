import os
import sys
import time
import json
import threading
import http.server
import socketserver
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SIM_DIR = BASE_DIR / "village_sim"
sys.path.insert(0, str(SIM_DIR))

import ai_models_village
from db import VillageDB

# Configure paths for laptop execution
ai_models_village.SIM_DIR = SIM_DIR
ai_models_village.LOG_FILE = SIM_DIR / "village.log"
ai_models_village.STATE_FILE = SIM_DIR / "world_state.json"
ai_models_village.GROQ_KEY_FILE = Path.home() / ".groq_key"

DURATION = 600 # strictly 10 minutes (600 seconds)
PORT = 8888

class VillageHTTPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # silent web logging

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ["", "/village", "/village.html"]:
            html_p = BASE_DIR / "village.html"
            if html_p.exists():
                data = html_p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
        elif path in ["/v1/village/state", "/village/state"]:
            st_p = SIM_DIR / "world_state.json"
            if st_p.exists():
                try:
                    data = st_p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"world":{}, "villagers":[]}')
            return
        elif path in ["/v1/village/logs", "/village/logs"]:
            lg_p = SIM_DIR / "village.log"
            lines = []
            if lg_p.exists():
                lines = [l.strip() for l in lg_p.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
            data = json.dumps({"lines": lines[-50:]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ["/v1/village/interact", "/village/interact"]:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                db = VillageDB(SIM_DIR / "village.db")
                db.add_god_action(data.get("target_villager", "all"), data.get("action_type", "whisper"), data.get("content", ""))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"queued"}')
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                return

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), VillageHTTPHandler) as httpd:
        httpd.serve_forever()

def main():
    print("=" * 65)
    print(f"🏰 STARTING PERSISTENT LAPTOP AI VILLAGE SIMULATION (Port {PORT})")
    print(f"Models: Qwen (qwen3.8-27b), GPT (gpt-oss-20b), Allam (allam-2-7b)")
    print(f"Local Dashboard: http://localhost:{PORT}")
    print("=" * 65)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    engine = ai_models_village.RealAIVillageEngine()
    tick_count = 0

    while True:

        tick_count += 1
        sys.stdout.write(f"\r[TICK {tick_count:04d} | {time.strftime('%H:%M:%S')}] Running simulation loop... ")
        sys.stdout.flush()

        try:
            engine.run_cycle()
        except Exception as e:
            print(f"\n[Cycle Notice] {e}")

        # Tick interval: 7.5 seconds
        time.sleep(7.5)

if __name__ == "__main__":
    main()
