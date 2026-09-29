#!/usr/bin/env bash
# ==============================================================================
# 🚀 1-LINER AUTONOMOUS PHONE SERVER RESTORER & EDGE SYNC
# Usage: ./recover_server.sh
# ==============================================================================
set -e

PHONE_IP="${PHONE_IP:-192.168.29.2:5555}"
PAGES_DOMAIN="https://phone-whisper-server.pages.dev"
SECRET="mobile_ai_nuclear_key"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚡ [1/5] Connecting to phone via ADB ($PHONE_IP)..."
adb connect "$PHONE_IP" >/dev/null 2>&1 || true

# Auto-detect target device (prefer USB if connected, else Wi-Fi)
USB_DEV=$(adb devices | grep -v "$PHONE_IP" | grep -v "List of" | grep "device$" | awk '{print $1}' | head -n 1 || echo "")
if [ -n "$USB_DEV" ]; then
  TARGET_DEV="$USB_DEV"
elif adb devices | grep -q "$PHONE_IP.*device"; then
  TARGET_DEV="$PHONE_IP"
else
  echo "❌ Could not reach phone at $PHONE_IP or via USB. Make sure phone is powered on."
  exit 1
fi

ADB_CMD="adb -s $TARGET_DEV"
echo "   Target ADB device: $TARGET_DEV"

# MIUI & Android background execution hardening
$ADB_CMD shell "dumpsys deviceidle whitelist +com.termux >/dev/null 2>&1 || true"
$ADB_CMD shell "dumpsys deviceidle disable all >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux SYSTEM_ALERT_WINDOW allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux RUN_IN_BACKGROUND allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux RUN_ANY_IN_BACKGROUND allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux WAKE_LOCK allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux START_FOREGROUND allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux 10008 allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux 10020 allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.termux 10021 allow >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.miui.powerkeeper WRITE_SETTINGS deny >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.miui.powerkeeper GET_USAGE_STATS deny >/dev/null 2>&1 || true"
$ADB_CMD shell "appops set com.miui.powerkeeper RUN_IN_BACKGROUND deny >/dev/null 2>&1 || true"
$ADB_CMD shell "pm disable-user --user 0 com.xiaomi.powerchecker >/dev/null 2>&1 || true"

echo "🔋 [2/5] Checking hardware & daemon status..."
RUNNING=$($ADB_CMD shell "run-as com.termux sh -c 'pgrep -f gateway.py >/dev/null && pgrep -f cloudflared >/dev/null && echo 1 || echo 0'" 2>/dev/null | tr -d '\r\n')

if [ "$RUNNING" != "1" ]; then
  echo "⚠️ Phone server or tunnel not detected running. Starting autonomous supervisor..."
  $ADB_CMD shell "run-as com.termux sh -c 'export PATH=/data/data/com.termux/files/usr/bin:\$PATH; export HOME=/data/data/com.termux/files/home; nohup bash \$HOME/start_ai.sh >/dev/null 2>&1 &'"
  echo "⏳ Waiting 6s for cloudflared tunnel to negotiate..."
  sleep 6
fi

echo "🌐 [3/5] Resolving active Cloudflare Quick Tunnel..."
TUNNEL_URL=$($ADB_CMD shell "run-as com.termux cat /data/data/com.termux/files/home/current_url.txt 2>/dev/null" 2>/dev/null | tr -d '\r\n')

if [ -z "$TUNNEL_URL" ] || ! echo "$TUNNEL_URL" | grep -qE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com"; then
  TUNNEL_URL=$($ADB_CMD shell "run-as com.termux grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' /data/data/com.termux/files/home/cf_tunnel.log 2>/dev/null | tail -n 1" 2>/dev/null | tr -d '\r\n')
fi

if [ -z "$TUNNEL_URL" ]; then
  echo "❌ Failed to detect active tunnel URL on phone."
  exit 1
fi

echo "   Found live origin: $TUNNEL_URL"

echo "📡 [4/5] Syncing Edge Gateway ($PAGES_DOMAIN)..."
REG_RESP=$(curl -s -m 6 -X POST "$PAGES_DOMAIN/register_tunnel" \
  -H "Content-Type: application/json" \
  -d "{\"endpoint\":\"$TUNNEL_URL\",\"secret\":\"$SECRET\"}" 2>/dev/null || echo "")

if echo "$REG_RESP" | grep -q "registered"; then
  echo "   Edge registration: ACTIVE"
else
  echo "⚠️ Edge registration warning: $REG_RESP"
fi

# Sync local repository files if origin changed
cd "$REPO_DIR"
CURRENT_LOCAL_EP=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" endpoint.json 2>/dev/null | head -n 1 || echo "")
if [ "$CURRENT_LOCAL_EP" != "$TUNNEL_URL" ]; then
  echo "📝 Updating local endpoint.json & functions/_proxy.js..."
  cat << JSON_EOF > endpoint.json
{
  "endpoint": "$TUNNEL_URL",
  "inference": "$TUNNEL_URL/inference",
  "telemetry": "$TUNNEL_URL/telemetry",
  "phone_lan_ip": "http://192.168.29.2:8080",
  "mode": "dual_worldwide_and_local",
  "port": 8080,
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON_EOF
  sed -i "s|const DEFAULT_FALLBACK_ORIGIN = \".*\";|const DEFAULT_FALLBACK_ORIGIN = \"$TUNNEL_URL\";|" functions/_proxy.js
  git add endpoint.json functions/_proxy.js 2>/dev/null || true
  git commit -m "fix(tunnel): recover & sync active tunnel to $TUNNEL_URL" 2>/dev/null || true
  git push origin main 2>/dev/null || true
fi

echo "🔍 [5/5] Verifying live server health..."
sleep 1
TEL_CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$PAGES_DOMAIN/telemetry" 2>/dev/null || echo "000")
HLT_CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$PAGES_DOMAIN/v1/health" 2>/dev/null || echo "000")

echo ""
if [ "$TEL_CODE" = "200" ] && [ "$HLT_CODE" = "200" ]; then
  echo "=========================================================="
  echo "✅ PHONE AI DATACENTER IS 100% ONLINE & HEALTHY"
  echo "   Domain:   $PAGES_DOMAIN"
  echo "   Tunnel:   $TUNNEL_URL"
  echo "   Telemetry: HTTP $TEL_CODE OK"
  echo "   Health:    HTTP $HLT_CODE OK"
  echo "=========================================================="
else
  echo "⚠️ Warning: Health check returned Telemetry=$TEL_CODE, Health=$HLT_CODE."
  echo "   Give Cloudflare Pages edge 5-10s to propagate."
fi
