#!/usr/bin/env python3
"""
⚡ INDESTRUCTIBLE PHONE AI DATACENTER AUTO-HEALING TUNNEL SUPERVISOR
Monitors:
1. gateway.py on 127.0.0.1:8080
2. cloudflared quick tunnel
3. Real-time edge registration with Cloudflare Pages Worker (POST /register_tunnel)
4. GitHub endpoint.json sync
"""
import os
import sys
import time
import json
import re
import subprocess
import urllib.request
import urllib.error

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BIN_DIR = os.path.join(PREFIX, "bin")
PAGES_REG_URL = "https://phone-whisper-server.pages.dev/register_tunnel"
SHARED_SECRET = "mobile_ai_nuclear_key"
CURRENT_URL_FILE = os.path.join(HOME, "current_url.txt")
CF_LOG_FILE = os.path.join(HOME, "cf_tunnel.log")
LOG_FILE = os.path.join(HOME, "tunnel_supervisor.log")

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def is_gateway_running():
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

def ensure_gateway():
    if not is_gateway_running():
        log("Gateway not responding! Restarting gateway.py...")
        subprocess.run(["pkill", "-f", "python.*gateway.py"], stderr=subprocess.DEVNULL)
        time.sleep(1)
        subprocess.Popen(["python3", os.path.join(HOME, "gateway.py")],
                         stdout=open(os.path.join(HOME, "gateway.log"), "a"),
                         stderr=subprocess.STDOUT)
        time.sleep(2)

def get_current_url():
    try:
        if os.path.exists(CURRENT_URL_FILE):
            with open(CURRENT_URL_FILE) as f:
                return f.read().strip()
    except Exception:
        pass
    return None

def probe_tunnel(url):
    if not url:
        return False
    try:
        req = urllib.request.Request(f"{url}/telemetry", headers={"User-Agent": "TunnelSupervisor/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status == 200
    except Exception:
        return False

def register_with_pages(url):
    try:
        payload = json.dumps({"endpoint": url, "secret": SHARED_SECRET}).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(PAGES_REG_URL, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            log(f"Edge registration status: {data.get('status')} (origin: {data.get('active_origin')})")
            return True
    except Exception as e:
        log(f"Edge registration warning: {e}")
        return False

def spawn_fresh_tunnel():
    log("Killing stale cloudflared instances...")
    subprocess.run(["killall", "-9", "cloudflared"], stderr=subprocess.DEVNULL)
    time.sleep(1)

    try:
        with open(CF_LOG_FILE, "w") as f:
            f.truncate(0)
    except Exception:
        pass

    cloudflared_bin = os.path.join(BIN_DIR, "cloudflared")
    if not os.path.exists(cloudflared_bin):
        cloudflared_bin = "cloudflared"

    log("Spawning fresh cloudflared tunnel...")
    cf_out = open(CF_LOG_FILE, "a")
    subprocess.Popen([
        cloudflared_bin, "tunnel",
        "--url", "http://127.0.0.1:8080",
        "--protocol", "http2",
        "--edge-ip-version", "4",
        "--no-autoupdate"
    ], stdout=cf_out, stderr=subprocess.STDOUT)

    new_url = None
    for _ in range(12):
        time.sleep(1)
        if os.path.exists(CF_LOG_FILE):
            try:
                with open(CF_LOG_FILE) as f:
                    content = f.read()
                matches = re.findall(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", content)
                if matches:
                    new_url = matches[-1]
                    break
            except Exception:
                pass

    if new_url:
        log(f"New cloudflared tunnel active: {new_url}")
        with open(CURRENT_URL_FILE, "w") as f:
            f.write(new_url)
        register_with_pages(new_url)
        repo_dir = os.path.join(HOME, "phone-whisper-server")
        if os.path.exists(repo_dir):
            try:
                ep_file = os.path.join(repo_dir, "endpoint.json")
                with open(ep_file, "w") as f:
                    json.dump({
                        "endpoint": new_url,
                        "inference": f"{new_url}/inference",
                        "telemetry": f"{new_url}/telemetry",
                        "phone_lan_ip": "http://192.168.29.2:8080",
                        "mode": "dual_worldwide_and_local",
                        "port": 8080,
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }, f, indent=2)
                subprocess.Popen("git add endpoint.json && git commit -m 'chore(tunnel): Auto-sync fresh tunnel' && git push origin main",
                                 shell=True, cwd=repo_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                log(f"Git sync notice: {e}")
        return new_url
    else:
        log("Failed to extract fresh tunnel URL within 12s!")
        return None

def main():
    log("Starting Phone AI Tunnel Supervisor Daemon...")
    fail_count = 0

    while True:
        try:
            ensure_gateway()
            url = get_current_url()

            if url and probe_tunnel(url):
                fail_count = 0
            else:
                fail_count += 1
                log(f"Tunnel probe failed (fail_count={fail_count}) for {url}")

            if fail_count >= 2:
                log("Tunnel is DEAD! Triggering self-healing recreation...")
                new_url = spawn_fresh_tunnel()
                if new_url:
                    fail_count = 0
                else:
                    time.sleep(3)

            time.sleep(5)
        except Exception as e:
            log(f"Supervisor loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
