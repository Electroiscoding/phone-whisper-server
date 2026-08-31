#!/usr/bin/env python3
"""
🏠 PHONEWHISPER 100% SOVEREIGN SELF-HOSTED SUPERVISOR & DAEMON GUARDIAN
1. Monitors and guarantees gateway.py uptime on port 8080 (0.0.0.0)
2. Serves full Web UI + API on http://192.168.29.2:8080/
3. 100% Offline, Zero Cloudflare, Zero External Dependencies
"""

import os
import time
import subprocess
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

def probe_local_gateway():
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/telemetry")
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
            subprocess.run(["pkill", "-9", "-f", "gateway.py"], stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            log_f = open(f"{HOME}/gateway.log", "a")
            env = os.environ.copy()
            env["PATH"] = f"/data/data/com.termux/files/usr/bin:{env.get('PATH', '')}"
            subprocess.Popen(["python3", f"{HOME}/gateway.py"], stdout=log_f, stderr=log_f, env=env, start_new_session=True)
            log("gateway.py spawned in detached session.")
        except Exception as e:
            log(f"Error starting gateway.py: {e}")

def main():
    log("🏠 PhoneWhisper 100% Sovereign Local Supervisor Active (No Cloudflare)")
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    start_battery_daemon()
    start_gateway()

    while True:
        try:
            start_battery_daemon()
            start_gateway()
        except Exception as e:
            log(f"Supervisor loop error: {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
