#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# PhoneWhisper AI - 24/7 Supervisor & Auto-Healing Watchdog
# ==============================================================================

export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build:$HOME/whisper.cpp/build/bin:$PREFIX/lib

# 1. Acquire Android Partial WakeLock to keep CPU active during screen off
termux-wake-lock 2>/dev/null || true

# 2. Stop old instances
killall -9 whisper-server cloudflared 2>/dev/null || true
sleep 1

# 3. Start whisper-server in an auto-restart supervisor loop
(
  while true; do
    if ! pgrep -f "whisper-server" > /dev/null; then
      echo "$(date): Launching whisper-server..." >> $HOME/whisper.log
      $HOME/whisper.cpp/build/bin/whisper-server \
        -m $HOME/whisper.cpp/models/ggml-tiny.en.bin \
        --port 8000 \
        --host 127.0.0.1 \
        -t 4 >> $HOME/whisper.log 2>&1
    fi
    sleep 3
  done
) &

sleep 2

# 4. Start Cloudflare Tunnel in an auto-restart supervisor loop
rm -f $HOME/cf_tunnel.log $HOME/current_url.txt
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Launching cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate > $HOME/cf_tunnel.log 2>&1
    fi
    sleep 3
  done
) &

# 5. Extract and persist active public HTTPS URL
(
  while true; do
    URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
    if [ -n "$URL" ]; then
      echo "$URL" > $HOME/current_url.txt
    fi
    sleep 5
  done
) &

echo "=================================================="
echo "🚀 24/7 AI Whisper Server & Cloudflare Tunnel Initialized"
echo "Waiting for Cloudflare Global URL..."

for i in $(seq 1 25); do
  URL=$(cat $HOME/current_url.txt 2>/dev/null)
  if [ -n "$URL" ]; then
    echo "=================================================="
    echo "🌐 WORLDWIDE HTTPS ENDPOINT:"
    echo "   $URL/inference"
    echo "=================================================="
    break
  fi
  sleep 1
done
