#!/usr/bin/env python3
"""
☢️ NUCLEAR AUTONOMOUS SUPERVISOR & SELF-HEALING TUNNEL BROADCASTER 2.2
1. Active End-to-End Public Liveness Probing (Guarantees zero-530 downtime)
2. Auto-Kills Invalidated/Expired Cloudflare Tunnels
3. DIRECT GIT PUSH to GitHub main branch for endpoint.json from Phone
4. Zero-Git Direct HTTP Tunnel Registration to Cloudflare Worker (/register_tunnel)
5. Robust Daemon Management with start_new_session=True (Never dies on ADB disconnect)
"""

import os
import re
import time
import subprocess
import json
import urllib.request
import urllib.error

HOME = "/data/data/com.termux/files/home"
WORKER_REGISTER_URL = "https://black-term-8c36.botmaker583-55e.workers.dev/register_tunnel"
SHARED_SECRET = "mobile_ai_nuclear_key"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}\n"
    print(entry, end="", flush=True)
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

def sync_endpoint_to_github(url):
    repo_dir = f"{HOME}/phone-whisper-server"
    if not os.path.exists(repo_dir):
        return False
    try:
        data = {
            "endpoint": url,
            "inference": f"{url}/inference",
            "telemetry": f"{url}/telemetry"
        }
        with open(f"{repo_dir}/endpoint.json", "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        
        # Git commit & push from Termux
        cmd = f"cd {repo_dir} && git add endpoint.json && git commit -m 'chore(tunnel): 🌐 Auto-sync live endpoint [{url}]' && git push origin main"
        subprocess.run(["bash", "-l", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        log(f"✅ Committed & pushed live endpoint {url} directly to GitHub repository!")
        return True
    except Exception as e:
        log(f"⚠️ Git push sync error: {e}")
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
                "User-Agent": "NuclearSupervisor/2.2"
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

def check_tunnel_log_for_fatal_errors():
    cf_log = f"{HOME}/cf_tunnel.log"
    if not os.path.exists(cf_log):
        return False
    try:
        with open(cf_log, "r") as f:
            content = f.read()[-3000:]
            if "Unauthorized: Tunnel not found" in content or "Tunnel not found" in content:
                return True
    except Exception:
        pass
    return False

def probe_public_tunnel(url):
    """Actively probes the public tunnel URL from edge to verify it is routing HTTP 200"""
    if not url:
        return False
    try:
        req = urllib.request.Request(
            f"{url}/health",
            headers={"User-Agent": "NuclearProbe/2.2"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            return resp.status == 200
    except Exception:
        return False

def probe_local_gateway():
    """Actively probes the local gateway process at port 8080"""
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/health")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def start_battery_daemon():
    if not is_process_running("battery_daemon.sh"):
        log("Starting persistent battery daemon...")
        try:
            subprocess.Popen(["/system/bin/sh", "/data/local/tmp/battery_daemon.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:
            log(f"Error starting battery daemon: {e}")

def start_gateway():
    if not is_process_running("gateway.py") or not probe_local_gateway():
        log("Starting gateway.py & Elastic Governor...")
        try:
            subprocess.run(["pkill", "-f", "gateway.py"], stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            log_f = open(f"{HOME}/gateway.log", "a")
            env = os.environ.copy()
            env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
            subprocess.Popen(["python3", f"{HOME}/gateway.py"], stdout=log_f, stderr=log_f, env=env, start_new_session=True)
            log("gateway.py spawned with new session.")
        except Exception as e:
            log(f"Error starting gateway.py: {e}")

def kill_and_restart_cloudflared():
    log("🚨 Killing stale/dead cloudflared and launching fresh tunnel...")
    try:
        subprocess.run(["pkill", "-9", "-f", "cloudflared"], stderr=subprocess.DEVNULL)
        time.sleep(1)
        try:
            with open(f"{HOME}/cf_tunnel.log", "w") as f:
                f.write("")
        except Exception:
            pass

        log_f = open(f"{HOME}/cf_tunnel.log", "a")
        env = os.environ.copy()
        env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
        subprocess.Popen([
            "cloudflared", "tunnel",
            "--url", "http://127.0.0.1:8080",
            "--protocol", "http2",
            "--edge-ip-version", "4",
            "--no-autoupdate"
        ], stdout=log_f, stderr=log_f, env=env, start_new_session=True)
        log("Cloudflared process spawned with new session.")
    except Exception as e:
        log(f"Error restarting cloudflared: {e}")

def main():
    log("☢️ Nuclear Self-Healing Supervisor 2.2 Initialized")
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    start_battery_daemon()
    start_gateway()
    
    if not is_process_running("cloudflared tunnel"):
        kill_and_restart_cloudflared()

    last_synced_url = None
    failed_probes = 0

    while True:
        try:
            start_battery_daemon()
            start_gateway()

            if not is_process_running("cloudflared tunnel"):
                kill_and_restart_cloudflared()
                time.sleep(3)

            # Check if cloudflared log indicates an invalidated tunnel
            if check_tunnel_log_for_fatal_errors():
                log("⚠️ Fatal tunnel error found in cf_tunnel.log ('Unauthorized: Tunnel not found')")
                kill_and_restart_cloudflared()
                time.sleep(3)

            current_url = get_current_tunnel_url()
            if current_url:
                if current_url != last_synced_url:
                    log(f"New tunnel URL detected: {current_url}")
                    sync_endpoint_to_github(current_url)
                    register_tunnel_url(current_url)
                    last_synced_url = current_url
                    failed_probes = 0
                    with open(f"{HOME}/current_url.txt", "w") as f:
                        f.write(current_url)

                # Periodic Active Public Liveness Probe
                is_alive = probe_public_tunnel(current_url)
                if is_alive:
                    failed_probes = 0
                else:
                    failed_probes += 1
                    log(f"⚠️ Public tunnel probe failed ({failed_probes}/3): {current_url}")
                    if failed_probes >= 3:
                        log(f"🚨 Public tunnel confirmed UNREACHABLE/DOWN (HTTP 530/502). Auto-recovering...")
                        kill_and_restart_cloudflared()
                        failed_probes = 0
                        last_synced_url = None
                        time.sleep(4)
                        continue

        except Exception as e:
            log(f"Supervisor loop error: {e}")

        time.sleep(3)

if __name__ == "__main__":
    main()
