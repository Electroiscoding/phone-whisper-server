#!/usr/bin/env python3
"""
🏠 PHONEWHISPER 100% SOVEREIGN SELF-HOSTED SUPERVISOR & DAEMON GUARDIAN
1. Monitors and guarantees gateway.py uptime on port 8080 (0.0.0.0)
2. Monitors and guarantees battery_daemon.sh uptime
3. Auto-detects local LAN IP (e.g. 192.168.29.2) and syncs local endpoint
4. 100% Offline, Zero Cloudflare, Zero External Dependencies
"""

import os
import time
import subprocess
import json
import socket
import urllib.request

HOME = "/data/data/com.termux/files/home"

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

def get_local_ip():
    """Detects active phone Wi-Fi / LAN IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to private subnet broadcast or router IP to determine default route
        s.connect(('192.168.29.1', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.29.2"

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
        log("Starting gateway.py on 0.0.0.0:8080...")
        try:
            subprocess.run(["killall", "-9", "python3"], stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            log_f = open(f"{HOME}/gateway.log", "a")
            env = os.environ.copy()
            env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
            subprocess.Popen(["python3", f"{HOME}/gateway.py"], stdout=log_f, stderr=log_f, env=env, start_new_session=True)
            log("gateway.py spawned in detached session.")
        except Exception as e:
            log(f"Error starting gateway.py: {e}")

def sync_local_endpoint():
    ip = get_local_ip()
    local_url = f"http://{ip}:8080"
    repo_dir = f"{HOME}/phone-whisper-server"
    try:
        data = {
            "endpoint": local_url,
            "inference": f"{local_url}/inference",
            "telemetry": f"{local_url}/telemetry",
            "mode": "self_hosted_local_lan",
            "phone_lan_ip": ip,
            "port": 8080
        }
        with open(f"{HOME}/current_url.txt", "w") as f:
            f.write(local_url)
        if os.path.exists(repo_dir):
            with open(f"{repo_dir}/endpoint.json", "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
    except Exception as e:
        log(f"Error syncing local endpoint: {e}")

def main():
    log("🏠 PhoneWhisper 100% Sovereign Local Supervisor Initialized")
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    start_battery_daemon()
    start_gateway()
    sync_local_endpoint()

    while True:
        try:
            start_battery_daemon()
            start_gateway()
            sync_local_endpoint()
        except Exception as e:
            log(f"Supervisor loop error: {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
