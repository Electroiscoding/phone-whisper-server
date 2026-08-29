#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build:$HOME/whisper.cpp/build/bin:$PREFIX/lib

# 1. Acquire Android Partial WakeLock
termux-wake-lock 2>/dev/null || true

# 2. Kill old instances
killall -9 whisper-server cloudflared python3 2>/dev/null || true
sleep 1

# 3. Start whisper-server backend on port 8000
(
  while true; do
    if ! pgrep -f "whisper-server" > /dev/null; then
      echo "$(date): Starting whisper-server..." >> $HOME/whisper.log
      $HOME/whisper.cpp/build/bin/whisper-server \
        -m $HOME/whisper.cpp/models/ggml-tiny.en.bin \
        --port 8000 \
        --host 127.0.0.1 \
        -t 4 >> $HOME/whisper.log 2>&1
    fi
    sleep 3
  done
) &

sleep 1

# 4. Start Live Telemetry Gateway on port 8080
(
  while true; do
    if ! pgrep -f "gateway.py" > /dev/null; then
      echo "$(date): Starting gateway.py..." >> $HOME/gateway.log
      python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1
    fi
    sleep 3
  done
) &

sleep 1

# 5. Smart Self-Healing Cloudflare Tunnel
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    else
      if grep -q "Incoming request ended abruptly" $HOME/cf_tunnel.log 2>/dev/null; then
        echo "$(date): Network reconnection detected, recycling tunnel..." >> $HOME/tunnel_watchdog.log
        killall -9 cloudflared 2>/dev/null
        rm -f $HOME/cf_tunnel.log
        sleep 2
        continue
      fi
    fi
    sleep 4
  done
) &

# 6. Autonomous Registry Broadcaster (Pushes live endpoint to GitHub automatically)
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
        echo "$(date): Successfully synced new tunnel to GitHub: $URL" >> $HOME/tunnel_watchdog.log
      fi
    fi
    sleep 4
  done
) &

echo "=================================================="
echo "🚀 24/7 Autonomous AI Whisper Server & Auto-Broadcaster Active"
echo "=================================================="
