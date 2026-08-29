#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# PhoneWhisper AI - Service Health & Endpoint Status Checker
# ==============================================================================

export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home

echo "=================================================="
echo "📱 PHONE AI HOST STATUS"
echo "=================================================="

if pgrep -f "whisper-server" > /dev/null; then
  echo "Whisper Server : RUNNING (Port 8000)"
else
  echo "Whisper Server : STOPPED"
fi

if pgrep -f "cloudflared" > /dev/null; then
  echo "Cloudflare     : RUNNING"
  URL=$(cat $HOME/current_url.txt 2>/dev/null)
  echo "Public URL     : ${URL:-'Acquiring...'} "
  if [ -n "$URL" ]; then
    echo "Inference API  : $URL/inference"
  fi
else
  echo "Cloudflare     : STOPPED"
fi

echo "--------------------------------------------------"
echo "Active Process Details:"
ps -ef | grep -E "whisper-server|cloudflared" | grep -v grep
echo "=================================================="
