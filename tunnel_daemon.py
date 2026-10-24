import subprocess
import time
import re
import json
import os
import urllib.request
import urllib.error

PHONE_LAN_URL = "http://127.0.0.1:8081"
GATEWAY_URL = "http://127.0.0.1:8000"
PAGES_REG_URL = "https://phone-whisper-server.pages.dev/register_tunnel"
SHARED_SECRET = "mobile_ai_nuclear_key"
CLOUDFLARED_BIN = "/home/soham/.local/bin/cloudflared"
REPO_DIR = "/home/soham/Documents/antigravity/cool-bohr"

def ensure_gateway():
    try:
        with urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=1) as r:
            if r.status == 200:
                return
    except Exception:
        pass
    print("[SUPERVISOR] Starting Unified Nikolinus + Phone Gateway (port 8000)...", flush=True)
    subprocess.Popen(
        ["/home/soham/.bun/bin/bun", os.path.join(REPO_DIR, "gateway.ts")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1)

def register_with_pages(url):
    try:
        payload = json.dumps({"endpoint": url, "secret": SHARED_SECRET}).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "AutonomousWatchdog/1.0"}
        req = urllib.request.Request(PAGES_REG_URL, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"[EDGE-REG] status: {data.get('status')} active: {data.get('active_origin')}", flush=True)
            return True
    except Exception as e:
        print(f"[EDGE-REG ERROR] {e}", flush=True)
        return False

def sync_repo(url):
    try:
        ep_file = os.path.join(REPO_DIR, "endpoint.json")
        proxy_file = os.path.join(REPO_DIR, "functions/_proxy.js")
        
        with open(ep_file, "r") as f:
            data = json.load(f)
        
        data["endpoint"] = url
        data["inference"] = f"{url}/inference"
        data["telemetry"] = f"{url}/telemetry"
        data["phone_lan_ip"] = PHONE_LAN_URL
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(ep_file, "w") as f:
            json.dump(data, f, indent=2)
            
        with open(proxy_file, "r") as f:
            content = f.read()
        content = re.sub(r'const DEFAULT_FALLBACK_ORIGIN = ".*?";', f'const DEFAULT_FALLBACK_ORIGIN = "{url}";', content)
        with open(proxy_file, "w") as f:
            f.write(content)
            
        subprocess.run(
            f'git -C "{REPO_DIR}" add endpoint.json functions/_proxy.js && git -C "{REPO_DIR}" commit -m "chore(tunnel): Auto-sync live endpoint [{url}]" && git -C "{REPO_DIR}" push origin main',
            shell=True, capture_output=True, text=True
        )
        print(f"[REPO-SYNC] Pushed {url} to repo", flush=True)
    except Exception as e:
        print(f"[REPO-SYNC ERROR] {e}", flush=True)

def check_phone_lan():
    try:
        with urllib.request.urlopen(f"{PHONE_LAN_URL}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False

def main():
    print("[SUPERVISOR] Starting resilient phone tunnel watchdog...", flush=True)
    while True:
        if not check_phone_lan():
            print("[SUPERVISOR] Phone not responding on LAN 192.168.29.2:8080, waiting 5s...", flush=True)
            time.sleep(5)
            continue
            
        print("[SUPERVISOR] Phone LAN is online! Ensuring gateway and launching tunnel...", flush=True)
        ensure_gateway()
        try:
            proc = subprocess.Popen(
                [CLOUDFLARED_BIN, 'tunnel', '--url', PHONE_LAN_URL, '--protocol', 'http2', '--edge-ip-version', '4', '--no-autoupdate'],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            registered = False
            for line in iter(proc.stderr.readline, ''):
                print(line, end='', flush=True)
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match and not registered:
                    url = match.group(0)
                    registered = True
                    print(f"\n[SUPERVISOR] Acquired tunnel: {url}\n", flush=True)
                    register_with_pages(url)
                    sync_repo(url)
                    
            proc.wait()
            print("[SUPERVISOR] cloudflared process ended, resurrecting in 3s...", flush=True)
            time.sleep(3)
        except Exception as e:
            print(f"[SUPERVISOR ERROR] {e}", flush=True)
            time.sleep(5)

if __name__ == '__main__':
    main()
