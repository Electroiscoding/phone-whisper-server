#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# PhoneWhisper AI - Graceful Shutdown Script
# ==============================================================================

export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home

echo "Stopping all PhoneWhisper AI and Cloudflare Tunnel services..."
killall -9 whisper-server cloudflared 2>/dev/null || true
pkill -f "start_ai.sh" 2>/dev/null || true
pkill -f "whisper-server" 2>/dev/null || true
pkill -f "cloudflared" 2>/dev/null || true
rm -f $HOME/current_url.txt
echo "✅ All services stopped."
