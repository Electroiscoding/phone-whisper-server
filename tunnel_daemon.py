import subprocess
import time
import re
import json
import os
import urllib.request
import urllib.error
import signal
import threading

PHONE_LAN_URL = "http://127.0.0.1:8081"
LOCAL_GATEWAY_URL = "http://127.0.0.1:8082"
UNIFIED_GATEWAY_URL = "http://127.0.0.1:8000"
PAGES_REG_URL = "https://phone-whisper-server.pages.dev/register_tunnel"
SHARED_SECRET = "mobile_ai_nuclear_key"
CLOUDFLARED_BIN = "/home/soham/.local/bin/cloudflared"
BUN_BIN = "/home/soham/.bun/bin/bun"
REPO_DIR = "/home/soham/Documents/antigravity/cool-bohr"

local_gw_proc = None
unified_gw_proc = None

def check_url_health(url, timeout=1.5):
    try:
        req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "SupervisorHealth/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def ensure_local_gateway():
    global local_gw_proc
    if check_url_health(LOCAL_GATEWAY_URL):
        return True
    print("[SUPERVISOR] Starting Local Sovereign AI Gateway (port 8082)...", flush=True)
    env = os.environ.copy()
    env["GATEWAY_PORT"] = "8082"
    local_gw_proc = subprocess.Popen(
        ["/usr/bin/python3", os.path.join(REPO_DIR, "mobile", "gateway.py")],
        cwd=REPO_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    for _ in range(10):
        time.sleep(0.5)
        if check_url_health(LOCAL_GATEWAY_URL):
            print("[SUPERVISOR] Local Sovereign AI Gateway online on port 8082!", flush=True)
            return True
    return False

def ensure_unified_gateway():
    global unified_gw_proc
    if check_url_health(UNIFIED_GATEWAY_URL):
        return True
    print("[SUPERVISOR] Starting Unified Resilient Gateway (port 8000)...", flush=True)
    unified_gw_proc = subprocess.Popen(
        [BUN_BIN, os.path.join(REPO_DIR, "gateway.ts")],
        cwd=REPO_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    for _ in range(10):
        time.sleep(0.5)
        if check_url_health(UNIFIED_GATEWAY_URL):
            print("[SUPERVISOR] Unified Gateway online on port 8000!", flush=True)
            return True
    return False

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
            
        # Register is done in real-time via register_with_pages(url); avoid spamming git pushes
        print(f"[LOCAL-SYNC] Saved {url} to endpoint.json", flush=True)
    except Exception as e:
        print(f"[REPO-SYNC ERROR] {e}", flush=True)

def launch_pinggy():
    print("[SUPERVISOR] Spawning resilient Pinggy SSH tunnel...", flush=True)
    cmd = ["ssh", "-p", "443", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=15", "-R0:localhost:8000", "a.pinggy.io", "x:true"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    url = None
    for line in iter(proc.stdout.readline, ''):
        print(line, end='', flush=True)
        m = re.search(r'https://[a-zA-Z0-9.-]+\.run\.pinggy-free\.link', line)
        if not m:
            m = re.search(r'https://[a-zA-Z0-9.-]+\.free\.pinggy\.net', line)
        if m and not url:
            url = m.group(0)
            print(f"\n[SUPERVISOR] Acquired Pinggy tunnel: {url}\n", flush=True)
            register_with_pages(url)
            sync_repo(url)
    proc.wait()
    print("[SUPERVISOR] Pinggy tunnel ended.", flush=True)

def main():
    print("[SUPERVISOR] Starting resilient zero-downtime datacenter watchdog...", flush=True)
    
    # 1. Guarantee gateways are alive
    ensure_local_gateway()
    ensure_unified_gateway()
    
    last_cloudflare_attempt = 0
    cloudflare_cooldown = 180 # 3 minutes cooldown if 429
    
    while True:
        ensure_local_gateway()
        ensure_unified_gateway()
        
        target = UNIFIED_GATEWAY_URL
        now = time.time()
        
        # Try Cloudflare first if not in cooldown
        if (now - last_cloudflare_attempt) > cloudflare_cooldown:
            last_cloudflare_attempt = now
            print(f"[SUPERVISOR] Attempting Cloudflare Tunnel towards Unified Gateway: {target}...", flush=True)
            
            try:
                proc = subprocess.Popen(
                    [CLOUDFLARED_BIN, 'tunnel', '--url', target, '--protocol', 'http2', '--edge-ip-version', '4', '--no-autoupdate'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                registered_url = None
                rate_limited = False
                
                for line in iter(proc.stdout.readline, ''):
                    print(line, end='', flush=True)
                    if "429" in line:
                        rate_limited = True
                        break
                    match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                    if match and not registered_url:
                        registered_url = match.group(0)
                        print(f"\n[SUPERVISOR] Acquired Cloudflare tunnel: {registered_url}\n", flush=True)
                        register_with_pages(registered_url)
                        sync_repo(registered_url)
                        
                if rate_limited or not registered_url:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                    print("[SUPERVISOR] Cloudflare Tunnel rate-limited (429) or failed. Switching to Pinggy...", flush=True)
                    launch_pinggy()
                    continue
                else:
                    proc.wait()
                    print("[SUPERVISOR] Cloudflare process ended, resurrecting in 3s...", flush=True)
                    time.sleep(3)
                    continue
            except Exception as e:
                print(f"[SUPERVISOR ERROR] {e}", flush=True)
        
        # In cooldown -> use Pinggy
        launch_pinggy()
        time.sleep(5)

if __name__ == '__main__':
    main()

