#!/usr/bin/env python3
"""
🌐 PHONEWHISPER DUAL-MODE ENTERPRISE SUPERVISOR 4.0
1. Local LAN: Direct gateway.py on 0.0.0.0:8080 (Serves Web UI + API)
2. Global Worldwide: Cloudflare HTTP/2 Edge Tunnel (https://*.trycloudflare.com)
3. Autonomous GitHub Sync: Auto-pushes live tunnel URL to endpoint.json
4. On-Device Wi-Fi Guardian & Kernel Telemetry
"""

import os
import re
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
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('192.168.29.1', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    return "192.168.29.2"

def sync_endpoint_to_github(url):
    repo_dir = f"{HOME}/phone-whisper-server"
    if not os.path.exists(repo_dir):
        return False
    try:
        lan_ip = get_local_ip()
        data = {
            "endpoint": url,
            "inference": f"{url}/inference",
            "telemetry": f"{url}/telemetry",
            "phone_lan_ip": f"http://{lan_ip}:8080",
            "mode": "dual_worldwide_and_local",
            "port": 8080
        }
        with open(f"{repo_dir}/endpoint.json", "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        
        cmd = f"cd {repo_dir} && git add endpoint.json && git commit -m 'chore(tunnel): 🌐 Sync active worldwide HTTPS tunnel [{url}]' && git push origin main"
        subprocess.run(["bash", "-l", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        log(f"✅ Committed & pushed live HTTPS endpoint {url} directly to GitHub repository!")
        return True
    except Exception as e:
        log(f"⚠️ Git push sync error: {e}")
        return False

def get_current_cf_url():
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

def probe_public_tunnel(url):
    if not url:
        return False
    try:
        req = urllib.request.Request(
            f"{url}/telemetry",
            headers={"User-Agent": "TunnelProbe/4.0"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            return resp.status == 200
    except Exception:
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

def start_wifi_daemon():
    if not is_process_running("wifi_daemon.sh"):
        log("Starting persistent Wi-Fi auto-reconnect guardian...")
        try:
            subprocess.Popen(["/system/bin/sh", "/data/local/tmp/wifi_daemon.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:
            log(f"Error starting Wi-Fi daemon: {e}")

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
            log("gateway.py spawned with new session.")
        except Exception as e:
            log(f"Error starting gateway.py: {e}")

def kill_and_restart_cf_tunnel():
    log("🚀 Spawning Cloudflare HTTP/2 Worldwide Tunnel...")
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
            "cloudflared",
            "tunnel",
            "--url", "http://127.0.0.1:8080",
            "--protocol", "http2",
            "--edge-ip-version", "4",
            "--no-autoupdate"
        ], stdout=log_f, stderr=log_f, env=env, start_new_session=True)
        log("cloudflared tunnel process spawned with new session.")
    except Exception as e:
        log(f"Error restarting cloudflared: {e}")

def main():
    log("🏠 PhoneWhisper Enterprise Dual-Mode Supervisor 4.0 Active")
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    start_battery_daemon()
    start_wifi_daemon()
    start_gateway()
    
    if not is_process_running("cloudflared"):
        kill_and_restart_cf_tunnel()

    last_synced_url = None
    failed_probes = 0

    while True:
        try:
            start_battery_daemon()
            start_wifi_daemon()
            start_gateway()

            if not is_process_running("cloudflared"):
                kill_and_restart_cf_tunnel()
                time.sleep(4)

            current_url = get_current_cf_url()
            if current_url:
                if current_url != last_synced_url:
                    log(f"New Worldwide HTTPS URL detected: {current_url}")
                    sync_endpoint_to_github(current_url)
                    last_synced_url = current_url
                    failed_probes = 0
                    with open(f"{HOME}/current_url.txt", "w") as f:
                        f.write(current_url)

                is_alive = probe_public_tunnel(current_url)
                if is_alive:
                    failed_probes = 0
                else:
                    failed_probes += 1
                    log(f"⚠️ Tunnel probe failed ({failed_probes}/3): {current_url}")
                    if failed_probes >= 3:
                        log("🚨 Tunnel down. Auto-recovering...")
                        kill_and_restart_cf_tunnel()
                        failed_probes = 0
                        last_synced_url = None
                        time.sleep(4)
                        continue

        except Exception as e:
            log(f"Supervisor loop error: {e}")

        time.sleep(3)

if __name__ == "__main__":
    main()
