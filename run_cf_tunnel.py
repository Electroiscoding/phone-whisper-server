import subprocess
import time
import re
import json
import os

def update_workers_and_push(new_url):
    try:
        # 1. Update endpoint.json
        data = {
            "endpoint": new_url,
            "inference": f"{new_url}/inference",
            "telemetry": f"{new_url}/telemetry",
            "phone_lan_ip": "http://192.168.29.2:8080",
            "mode": "dual_worldwide_and_local",
            "port": 8080,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with open("endpoint.json", "w") as f:
            json.dump(data, f, indent=2)

        # 2. Update _worker.js and cloudflare_worker.js cachedOrigin
        for wfile in ["_worker.js", "cloudflare_worker.js"]:
            if os.path.exists(wfile):
                with open(wfile, "r") as f:
                    content = f.read()
                updated_content = re.sub(
                    r'let cachedOrigin = "https://[a-zA-Z0-9-]+\.trycloudflare\.com";',
                    f'let cachedOrigin = "{new_url}";',
                    content
                )
                with open(wfile, "w") as f:
                    f.write(updated_content)

        # 3. Git commit & push
        cmd = 'git add endpoint.json _worker.js cloudflare_worker.js && git commit -m "auto: sync live cloudflare tunnel endpoint" && git push origin main'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"[AUTO-SYNC] Git Push Result: {res.stdout.strip()}", flush=True)
    except Exception as e:
        print(f"[AUTO-SYNC ERROR] {e}", flush=True)

def main():
    print("Starting Self-Healing Cloudflare Tunnel Watchdog...", flush=True)
    while True:
        try:
            proc = subprocess.Popen(
                ['/tmp/cloudflared', 'tunnel', '--url', 'http://192.168.29.2:8080'],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            url_found = False
            for line in iter(proc.stderr.readline, ''):
                print(line, end='', flush=True)
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match and not url_found:
                    url = match.group(0)
                    url_found = True
                    print(f"\n[SUCCESS] LIVE TUNNEL ACQUIRED: {url}\n", flush=True)
                    update_workers_and_push(url)

            proc.wait()
            print("[WARNING] Tunnel process exited. Restarting in 3 seconds...", flush=True)
            time.sleep(3)
        except Exception as e:
            print(f"[TUNNEL ERROR] {e}", flush=True)
            time.sleep(5)

if __name__ == '__main__':
    main()
