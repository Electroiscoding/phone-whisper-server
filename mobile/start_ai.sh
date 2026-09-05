#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ☢️ AUTONOMOUS MOBILE AI HARDWARE SUPERVISOR & TUNNEL WATCHDOG
# ==============================================================================
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Partial WakeLock (Keeps ARM CPU alive even when screen is locked)
termux-wake-lock 2>/dev/null || true

echo "$(date): Starting Autonomous AI Supervisor..." >> $HOME/nuclear_supervisor.log
dumpsys battery reset 2>/dev/null || true

# 2. Start Persistent Android Kernel Battery Daemon
if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
  /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
fi

# 3. Start Multi-Modal Gateway Server (:8080)
if ! pgrep -f "gateway.py" > /dev/null; then
  python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
fi

# 4. Start Cloudflared Tunnel
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
fi

SYNCED_URL=""
LAST_PROBE_TIME=0

while true; do
  NOW=$(date +%s)

  # A. Verify Battery Daemon
  if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
    /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
  fi

  # B. Verify Gateway Server (:8080)
  if ! pgrep -f "gateway.py" > /dev/null; then
    echo "$(date): [CRITICAL] gateway.py dead! Restarting immediately..." >> $HOME/nuclear_supervisor.log
    killall -9 python3 2>/dev/null || true
    python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
    sleep 2
  fi

  # C. Verify Cloudflared Process & Check for Hung/Stalled Tunnel
  IS_TUNNEL_DEAD=0
  if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    IS_TUNNEL_DEAD=1
  elif tail -n 10 $HOME/cf_tunnel.log 2>/dev/null | grep -qE "Connection terminated|context deadline exceeded|error shutting down|dial tcp.*connection refused"; then
    IS_TUNNEL_DEAD=1
  fi

  # D. Active Tunnel Health Probe (Runs every 20 seconds on current URL)
  CURRENT_ACTIVE_URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
  if [ -n "$CURRENT_ACTIVE_URL" ] && [ $((NOW - LAST_PROBE_TIME)) -ge 20 ]; then
    LAST_PROBE_TIME=$NOW
    PROBE_STATUS=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$CURRENT_ACTIVE_URL/telemetry" 2>/dev/null || echo "000")
    if [ "$PROBE_STATUS" != "200" ]; then
      echo "$(date): [HEALTH PROBE FAILED] Status $PROBE_STATUS on $CURRENT_ACTIVE_URL. Re-spawning tunnel..." >> $HOME/nuclear_supervisor.log
      IS_TUNNEL_DEAD=1
    fi
  fi

  if [ "$IS_TUNNEL_DEAD" -eq 1 ]; then
    echo "$(date): [CRITICAL] Tunnel dead/stalled. Re-spawning cloudflared..." >> $HOME/nuclear_supervisor.log
    killall -9 cloudflared 2>/dev/null || true
    cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    sleep 4
  fi

  # E. Broadcaster: Sync New Tunnel URL to Cloudflare Pages and GitHub
  URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
  if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
    echo "$URL" > $HOME/current_url.txt

    # 1. Direct Edge Registration (Zero DNS Delay)
    curl -s -m 5 -X POST https://phone-whisper-server.pages.dev/register_tunnel \
      -H "Content-Type: application/json" \
      -d '{"endpoint": "'"$URL"'", "secret": "mobile_ai_nuclear_key"}' >/dev/null 2>&1 || true

    # 2. Push to GitHub Repo
    if [ -d "$HOME/phone-whisper-server" ]; then
      cd $HOME/phone-whisper-server
      git pull --rebase origin main 2>/dev/null || true
      cat << JSON_EOF > endpoint.json
{
  "endpoint": "$URL",
  "inference": "$URL/inference",
  "telemetry": "$URL/telemetry",
  "phone_lan_ip": "http://192.168.29.2:8080",
  "mode": "dual_worldwide_and_local",
  "port": 8080,
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON_EOF
      git add endpoint.json 2>/dev/null || true
      git commit -m "chore(tunnel): Nuclear auto-sync live endpoint [$URL]" 2>/dev/null || true
      if git push origin main 2>/dev/null; then
        SYNCED_URL="$URL"
        echo "$(date): [SUCCESS] Synced fresh tunnel URL to GitHub: $URL" >> $HOME/nuclear_supervisor.log
      fi
    fi
  fi

  sleep 3
done
