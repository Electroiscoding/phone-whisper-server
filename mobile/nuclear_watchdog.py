#!/usr/bin/env python3
"""
☢️ NUCLEAR AUTONOMOUS SUPERVISOR & TUNNEL BROADCASTER
1. Continuous Daemon Monitoring (gateway.py, cloudflared, battery_daemon)
2. Instant Tunnel Auto-Recovery
3. Zero-Git Direct HTTP Tunnel Registration to Cloudflare Worker (/register_tunnel)
"""

import os
import re
import time
import subprocess
import json
import urllib.request

HOME = "/data/data/com.termux/files/home"
WORKER_REGISTER_URL = "https://black-term-8c36.botmaker583-55e.workers.dev/register_tunnel"
SHARED_SECRET = "mobile_ai_nuclear_key"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}\n"
    print(entry, end="")
    try:
        with open(f"{HOME}/nuclear_supervisor.log", "a") as f:
            f.write(entry)
    except Exception:
        pass

def is_process_running(pattern):
    try:
        out = subprocess.check_output(["ps", "-ef"], stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            if pattern in line and "grep" not in line and "nuclear_watchdog" not in line:
                return True
    except Exception:
        pass
    return False

def register_tunnel_url(url):
    try:
        payload = json.dumps({
            "secret": SHARED_SECRET,
            "endpoint": url
        }).encode()
        req = urllib.request.Request(
            WORKER_REGISTER_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NuclearSupervisor/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            log(f"✅ Registered tunnel directly to Cloudflare Worker: {url} -> {data}")
            return True
    except Exception as e:
        log(f"⚠️ Failed to register tunnel to worker: {e}")
        return False

def get_current_tunnel_url():
    cf_log = f"{HOME}/cf_tunnel.log"
    if not os.path.exists(cf_log):
        return None
    try:
        with open(cf_log, "r") as f:
            matches = re.findall(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", f.read())
            if matches:
                return matches[-1]
    except Exception:
        pass
    return None

def start_battery_daemon():
    if not is_process_running("battery_daemon.sh"):
        log("Starting persistent battery daemon...")
        try:
            subprocess.Popen(["/system/bin/sh", "/data/local/tmp/battery_daemon.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log(f"Error starting battery daemon: {e}")

def start_gateway():
    if not is_process_running("gateway.py"):
        log("Starting gateway.py & Elastic Governor...")
        try:
            log_f = open(f"{HOME}/gateway.log", "a")
            env = os.environ.copy()
            env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
            subprocess.Popen(["python3", f"{HOME}/gateway.py"], stdout=log_f, stderr=log_f, env=env)
        except Exception as e:
            log(f"Error starting gateway.py: {e}")

def start_cloudflared():
    if not is_process_running("cloudflared tunnel"):
        log("Starting cloudflared tunnel...")
        try:
            log_f = open(f"{HOME}/cf_tunnel.log", "a")
            env = os.environ.copy()
            env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
            subprocess.Popen([
                "cloudflared", "tunnel",
                "--url", "http://127.0.0.1:8080",
                "--protocol", "http2",
                "--edge-ip-version", "4",
                "--no-autoupdate"
            ], stdout=log_f, stderr=log_f, env=env)
        except Exception as e:
            log(f"Error starting cloudflared: {e}")

def main():
    log("☢️ Nuclear Autonomous Supervisor Initialized")
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    start_battery_daemon()
    start_gateway()
    start_cloudflared()

    last_synced_url = None

    while True:
        try:
            start_battery_daemon()
            start_gateway()
            start_cloudflared()

            # Check tunnel health
            current_url = get_current_tunnel_url()
            if current_url and current_url != last_synced_url:
                log(f"New tunnel URL detected: {current_url}")
                if register_tunnel_url(current_url):
                    last_synced_url = current_url
                    with open(f"{HOME}/current_url.txt", "w") as f:
                        f.write(current_url)

        except Exception as e:
            log(f"Supervisor loop error: {e}")

        time.sleep(3)

if __name__ == "__main__":
    main()
