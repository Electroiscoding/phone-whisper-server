import subprocess
import time
import re
import json

def main():
    print("Starting Cloudflare Tunnel Daemon...")
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
            print(f"\n[SUCCESS] CLOUDFLARE TUNNEL CREATED: {url}\n", flush=True)
            
            data = {
                "endpoint": url,
                "inference": f"{url}/inference",
                "telemetry": f"{url}/telemetry",
                "phone_lan_ip": "http://192.168.29.2:8080",
                "mode": "dual_worldwide_and_local",
                "port": 8080,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            with open('endpoint.json', 'w') as f:
                json.dump(data, f, indent=2)
            print("[SUCCESS] endpoint.json updated.", flush=True)

    proc.wait()

if __name__ == '__main__':
    main()
