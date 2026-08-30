#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Partial WakeLock (Keeps CPU alive even when screen is locked)
termux-wake-lock 2>/dev/null || true

# 2. Kill old processes cleanly
killall -9 whisper-server llama-server cloudflared python3 2>/dev/null || true
pkill -f start_ai.sh 2>/dev/null || true
sleep 1

# 3. Autonomous System Battery & Hardware Daemon
(
  while true; do
    if ! pgrep -f "update_hardware.sh" > /dev/null && ! pgrep -f "battery_daemon.sh" > /dev/null; then
      /system/bin/sh /data/local/tmp/battery_daemon.sh > /dev/null 2>&1 &
    fi
    sleep 5
  done
) &

# 4. Multi-Modal Gateway with Elastic Memory Governor (Port 8080)
(
  while true; do
    if ! pgrep -f "gateway.py" > /dev/null; then
      echo "$(date): Starting Multi-Modal Gateway & Elastic Memory Governor..." >> $HOME/gateway.log
      python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1
    fi
    sleep 4
  done
) &

sleep 1

# 5. Persistent Cloudflare Tunnel with Automatic Exponential Backoff & Reconnection
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting persistent cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    fi
    sleep 8
  done
) &

# 6. Autonomous URL Broadcaster (Auto-reconnects & syncs to GitHub with retry)
(
  SYNCED_URL=""
  while true; do
    URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
    if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
      echo "$URL" > $HOME/current_url.txt
      if [ -d "$HOME/phone-whisper-server" ]; then
        cd $HOME/phone-whisper-server
        git pull --rebase origin main 2>/dev/null || true
        cat << JSON_EOF > $HOME/phone-whisper-server/endpoint.json
{
  "endpoint": "$URL",
  "inference": "$URL/inference",
  "telemetry": "$URL/telemetry"
}
JSON_EOF
        git add endpoint.json 2>/dev/null || true
        git commit -m "chore(tunnel): Auto-sync live endpoint [$URL]" 2>/dev/null || true
        if git push origin main 2>/dev/null; then
          SYNCED_URL="$URL"
          echo "$(date): Successfully synced stable tunnel to GitHub: $URL" >> $HOME/tunnel_watchdog.log
        else
          echo "$(date): Network offline or git push failed; retrying in 5s..." >> $HOME/tunnel_watchdog.log
        fi
      fi
    fi
    sleep 6
  done
) &

echo "=================================================="
echo "🚀 Autonomous Mobile AI Server Active"
echo "🔋 Self-Healing Reconnection & WakeLock Online"
echo "=================================================="
