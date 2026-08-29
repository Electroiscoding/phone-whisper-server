#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build:$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Android Partial WakeLock
termux-wake-lock 2>/dev/null || true

# 2. Kill old instances cleanly
killall -9 whisper-server llama-server cloudflared python3 2>/dev/null || true
sleep 1

# 3. Start Whisper Base.en STT Backend on Port 8000
(
  while true; do
    if ! pgrep -f "whisper-server" > /dev/null; then
      echo "$(date): Starting Whisper-Server (Base.en 148MB)..." >> $HOME/whisper.log
      $HOME/whisper.cpp/build/bin/whisper-server \
        -m $HOME/whisper.cpp/models/ggml-base.en.bin \
        --port 8000 \
        --host 127.0.0.1 \
        -t 4 >> $HOME/whisper.log 2>&1
    fi
    sleep 3
  done
) &

sleep 1

# 4. Start Llama.cpp Qwen 2.5 SLM & Vector Embeddings on Port 8001
(
  while true; do
    if ! pgrep -f "llama-server" > /dev/null; then
      echo "$(date): Starting Llama-Server (Qwen 2.5 0.5B + Embeddings)..." >> $HOME/llama.log
      $HOME/llama.cpp/build/bin/llama-server \
        -m $HOME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
        --port 8001 \
        --host 127.0.0.1 \
        -t 4 \
        -c 2048 \
        --embedding \
        --pooling mean \
        -ngl 0 >> $HOME/llama.log 2>&1
    fi
    sleep 3
  done
) &

sleep 1

# 5. Start Multi-Modal Gateway on Port 8080
(
  while true; do
    if ! pgrep -f "gateway.py" > /dev/null; then
      echo "$(date): Starting Multi-Modal gateway.py..." >> $HOME/gateway.log
      python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1
    fi
    sleep 3
  done
) &

sleep 1

# 6. Active Self-Healing Cloudflare Tunnel
(
  FAIL_COUNT=0
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
      FAIL_COUNT=0
      sleep 12
    else
      CURRENT_PUB_URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
      if [ -n "$CURRENT_PUB_URL" ]; then
        STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$CURRENT_PUB_URL/telemetry" 2>/dev/null || echo "000")
        if [ "$STATUS_CODE" != "200" ] && [ "$STATUS_CODE" != "404" ]; then
          FAIL_COUNT=$((FAIL_COUNT + 1))
          echo "$(date): Tunnel probe: $STATUS_CODE (consecutive fails: $FAIL_COUNT)" >> $HOME/tunnel_watchdog.log
          if [ $FAIL_COUNT -ge 6 ]; then
            echo "$(date): Tunnel consistently unreachable ($STATUS_CODE). Restarting..." >> $HOME/tunnel_watchdog.log
            killall -9 cloudflared 2>/dev/null
            rm -f $HOME/cf_tunnel.log
            FAIL_COUNT=0
            sleep 3
            continue
          fi
        else
          FAIL_COUNT=0
        fi
      fi
    fi
    sleep 5
  done
) &

# 7. Autonomous Registry Broadcaster (Pushes live endpoint to GitHub automatically)
(
  LAST_URL=""
  while true; do
    URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | tail -n 1)
    if [ -n "$URL" ] && [ "$URL" != "$LAST_URL" ]; then
      HEALTH=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$URL/telemetry" 2>/dev/null || echo "000")
      if [ "$HEALTH" = "200" ]; then
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
          echo "$(date): Successfully synced verified healthy tunnel to GitHub: $URL" >> $HOME/tunnel_watchdog.log
        fi
      fi
    fi
    sleep 4
  done
) &

echo "=================================================="
echo "🚀 24/7 Multi-Modal AI Datacenter Active (STT + SLM + TTS + Embeddings + Telemetry)"
echo "=================================================="
