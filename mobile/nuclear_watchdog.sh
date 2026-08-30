#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ☢️ NUCLEAR MOBILE AI AUTONOMOUS SELF-HEALING SUPERVISOR
# ==============================================================================
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# Acquire Partial WakeLock (Keeps ARM CPU active even in deep Android Doze)
termux-wake-lock 2>/dev/null || true

echo "$(date): Starting Nuclear AI Supervisor..." >> $HOME/nuclear_supervisor.log

# 1. Start Persistent Android Kernel Battery Daemon
if ! pgrep -f "battery_daemon.sh" > /dev/null; then
  /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
fi

# 2. Start Gateway & Elastic Governor
if ! pgrep -f "gateway.py" > /dev/null; then
  python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
fi

# 3. Start Cloudflared Tunnel if not alive
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
fi

SYNCED_URL=""

while true; do
  # A. Verify Battery Daemon
  if ! pgrep -f "battery_daemon.sh" > /dev/null; then
    /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
  fi

  # B. Verify Gateway Server (:8080)
  if ! pgrep -f "gateway.py" > /dev/null; then
    echo "$(date): [CRITICAL] gateway.py dead! Restarting immediately..." >> $HOME/nuclear_supervisor.log
    killall -9 python3 2>/dev/null || true
    python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
    sleep 2
  fi

  # C. Verify Tunnel Health & Log Status
  IS_TUNNEL_DEAD=0
  if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    IS_TUNNEL_DEAD=1
  elif tail -n 10 $HOME/cf_tunnel.log 2>/dev/null | grep -qE "Connection terminated|context deadline exceeded|error shutting down"; then
    IS_TUNNEL_DEAD=1
  fi

  if [ "$IS_TUNNEL_DEAD" -eq 1 ]; then
    echo "$(date): [CRITICAL] Cloudflare Tunnel disconnected/stalled! Re-spawning..." >> $HOME/nuclear_supervisor.log
    killall -9 cloudflared 2>/dev/null || true
    cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    sleep 4
  fi

  # D. Sync New Tunnel URL to GitHub endpoint.json Immediately
  URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
  if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
    echo "$URL" > $HOME/current_url.txt
    if [ -d "$HOME/phone-whisper-server" ]; then
      cd $HOME/phone-whisper-server
      cat << EOF > endpoint.json
{
  "endpoint": "$URL",
  "inference": "$URL/inference",
  "telemetry": "$URL/telemetry"
}
EOF
      git add endpoint.json 2>/dev/null || true
      git commit -m "chore(tunnel): Nuclear auto-sync live endpoint [$URL]" 2>/dev/null || true
      if git push origin main 2>/dev/null; then
        SYNCED_URL="$URL"
        echo "$(date): [SUCCESS] Synced fresh tunnel URL: $URL" >> $HOME/nuclear_supervisor.log
      fi
    fi
  fi

  sleep 3
done
