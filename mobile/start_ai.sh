#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/SenseVoice.cpp/build/lib:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Partial WakeLock
termux-wake-lock 2>/dev/null || true

# 2. Kill old processes cleanly
killall -9 llama-server cloudflared python3 2>/dev/null || true
pkill -f start_ai.sh 2>/dev/null || true
sleep 1

# 3. Start Llama.cpp Qwen 2.5 SLM on Port 8001 (Chat Completions)
(
  while true; do
    if ! pgrep -f "8001" > /dev/null; then
      echo "$(date): Starting Llama-Server (Qwen 2.5 Chat on :8001)..." >> $HOME/llama_chat.log
      $HOME/llama.cpp/build/bin/llama-server \
        -m $HOME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
        --port 8001 \
        --host 127.0.0.1 \
        -t 4 \
        -c 2048 \
        -ngl 0 >> $HOME/llama_chat.log 2>&1
    fi
    sleep 5
  done
) &

sleep 1

# 4. Start BAAI BGE-Small-en-v1.5 on Port 8002 (Dedicated Isotropic Embeddings with CLS Pooling)
(
  while true; do
    if ! pgrep -f "8002" > /dev/null; then
      echo "$(date): Starting BGE-Small-en-v1.5 (Embeddings on :8002)..." >> $HOME/llama_embed.log
      $HOME/llama.cpp/build/bin/llama-server \
        -m $HOME/models/bge-small-en-v1.5-q8_0.gguf \
        --port 8002 \
        --host 127.0.0.1 \
        -t 4 \
        -c 512 \
        --embedding \
        --pooling cls \
        -ngl 0 >> $HOME/llama_embed.log 2>&1
    fi
    sleep 5
  done
) &

sleep 1

# 5. Start Multi-Modal Gateway with SenseVoice-Small STT + Qwen + BGE on Port 8080
(
  while true; do
    if ! pgrep -f "gateway.py" > /dev/null; then
      echo "$(date): Starting Multi-Modal gateway.py..." >> $HOME/gateway.log
      python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1
    fi
    sleep 5
  done
) &

sleep 1

# 6. Persistent Cloudflare Tunnel (Starts ONCE and NEVER killed by watchdog)
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting persistent cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    fi
    sleep 10
  done
) &

# 7. Broadcaster (Pushes URL to GitHub ONLY ONCE when URL changes)
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
echo "🚀 24/7 Multi-Modal AI Datacenter Active (SenseVoice STT + Qwen Chat + BGE Embeddings + TTS)"
echo "=================================================="
