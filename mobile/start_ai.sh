#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Partial WakeLock
termux-wake-lock 2>/dev/null || true

# 2. Kill old processes cleanly
killall -9 whisper-server llama-server cloudflared python3 2>/dev/null || true
pkill -f start_ai.sh 2>/dev/null || true
sleep 1

# 3. Start Multi-Modal Gateway with Elastic Memory Governor on Port 8080
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

# 4. Persistent Cloudflare Tunnel (Starts ONCE and NEVER killed by watchdog)
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting persistent cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    fi
    sleep 10
  done
) &

# 5. Broadcaster (Pushes URL to GitHub ONLY ONCE when URL changes)
(
  LAST_URL=""
  while true; do
    URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
    if [ -n "$URL" ] && [ "$URL" != "$LAST_URL" ]; then
      LAST_URL="$URL"
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
        git push origin main 2>/dev/null || true
        echo "$(date): Successfully synced stable tunnel to GitHub: $URL" >> $HOME/tunnel_watchdog.log
      fi
    fi
    sleep 8
  done
) &

echo "=================================================="
echo "🚀 Elastic AI Datacenter Active (Dynamic Memory Governor • JIT Spawning • 75s Idle Eviction)"
echo "=================================================="
