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

# 3. Start Whisper-Server on Port 8000 (OpenAI Whisper Base.en Q5_1 - High Accuracy STT)
(
  while true; do
    if ! pgrep -f "8000" > /dev/null; then
      echo "$(date): Starting Whisper-Server (Base.en Q5_1 on :8000)..." >> $HOME/whisper_server.log
      $HOME/whisper.cpp/build/bin/whisper-server \
        -m $HOME/whisper.cpp/models/ggml-base.en-q5_1.bin \
        --port 8000 \
        --host 127.0.0.1 \
        -t 4 \
        --no-timestamps >> $HOME/whisper_server.log 2>&1
    fi
    sleep 5
  done
) &

sleep 1

# 4. Start Llama.cpp Qwen 2.5 SLM on Port 8001 (Chat Completions)
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

# 5. Start BAAI BGE-Small-en-v1.5 on Port 8002 (Dedicated Isotropic Embeddings)
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

# 6. Start BAAI BGE-Reranker-Base on Port 8003 (Deep Cross-Attention NLI Reranker)
(
  while true; do
    if ! pgrep -f "8003" > /dev/null; then
      echo "$(date): Starting BGE-Reranker-Base (Cross-Encoder on :8003)..." >> $HOME/llama_rerank.log
      $HOME/llama.cpp/build/bin/llama-server \
        -m $HOME/models/bge-reranker-base-q4_k_m.gguf \
        --port 8003 \
        --host 127.0.0.1 \
        -t 4 \
        -c 512 \
        --reranking \
        --pooling rank \
        -ngl 0 >> $HOME/llama_rerank.log 2>&1
    fi
    sleep 5
  done
) &

sleep 1

# 7. Start Multi-Modal Gateway with Whisper STT + Qwen + BGE Embeddings + Reranker + TTS on Port 8080
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

# 8. Persistent Cloudflare Tunnel (Starts ONCE and NEVER killed by watchdog)
(
  while true; do
    if ! pgrep -f "cloudflared tunnel" > /dev/null; then
      echo "$(date): Starting persistent cloudflared tunnel..." >> $HOME/tunnel_watchdog.log
      cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    fi
    sleep 10
  done
) &

# 9. Broadcaster (Pushes URL to GitHub ONLY ONCE when URL changes)
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
echo "🚀 6-in-1 Mobile AI Datacenter Active (OpenAI Whisper Base.en STT + Qwen Chat + BGE Embeddings + Cross-Encoder Reranker + TTS + Telemetry)"
echo "=================================================="
