#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ☢️ AUTONOMOUS MOBILE AI HARDWARE SUPERVISOR & TUNNEL WATCHDOG (HYPER-STABLE)
# ==============================================================================
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib

# 1. Acquire Partial WakeLock (Keeps ARM CPU alive even when screen is locked)
termux-wake-lock 2>/dev/null || true

echo "$(date): [STARTUP] Starting Autonomous AI Supervisor..." >> $HOME/nuclear_supervisor.log

# Ensure USB charging is isolated to protect battery health and prevent overheating
dumpsys battery set usb 0 2>/dev/null || true

# 2. Start Persistent Android Kernel Battery Daemon
if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
  /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
fi

# 3. Start Multi-Modal Gateway Server (:8080)
if ! pgrep -f "gateway.py" > /dev/null; then
  python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
fi

# 4. Start Cloudflared Tunnel
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
fi

SYNCED_URL=""
LAST_PROBE_TIME=$(date +%s)
LAST_LOG_TRIM=$(date +%s)
FAIL_COUNT=0
GW_FAIL_COUNT=0

while true; do
  NOW=$(date +%s)

  # A. Protect Battery: Keep USB charging disabled
  dumpsys battery set usb 0 2>/dev/null || true

  # B. Verify Battery Daemon
  if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
    /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
  fi

  # C. Verify Gateway Server (:8080) with Active HTTP Probe
  GW_ALIVE=1
  if ! pgrep -f "gateway.py" > /dev/null; then
    GW_ALIVE=0
  else
    # Quick 2-second local probe
    GW_STATUS=$(curl -s -m 2 -o /dev/null -w "%{http_code}" "http://127.0.0.1:8080/health" 2>/dev/null || echo "000")
    if [ "$GW_STATUS" != "200" ]; then
      GW_FAIL_COUNT=$((GW_FAIL_COUNT + 1))
      if [ "$GW_FAIL_COUNT" -ge 3 ]; then
        GW_ALIVE=0
        GW_FAIL_COUNT=0
      fi
    else
      GW_FAIL_COUNT=0
    fi
  fi

  if [ "$GW_ALIVE" -eq 0 ]; then
    echo "$(date): [CRITICAL] gateway.py dead/unresponsive! Re-spawning..." >> $HOME/nuclear_supervisor.log
    killall -9 python3 2>/dev/null || true
    sleep 1
    python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
    sleep 2
  fi

  # D. Verify Cloudflared Process & Check for Hung/Stalled Tunnel
  IS_TUNNEL_DEAD=0
  if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    IS_TUNNEL_DEAD=1
  elif tail -n 15 $HOME/cf_tunnel.log 2>/dev/null | grep -qE "Connection terminated|context deadline exceeded|error shutting down|dial tcp.*connection refused"; then
    IS_TUNNEL_DEAD=1
  fi

  # E. Active Worldwide Tunnel Health Probe (Every 20s)
  CURRENT_ACTIVE_URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)
  if [ -n "$CURRENT_ACTIVE_URL" ] && [ $((NOW - LAST_PROBE_TIME)) -ge 20 ]; then
    LAST_PROBE_TIME=$NOW
    PROBE_STATUS=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "$CURRENT_ACTIVE_URL/telemetry" 2>/dev/null || echo "000")
    if [ "$PROBE_STATUS" = "200" ]; then
      FAIL_COUNT=0
    else
      FAIL_COUNT=$((FAIL_COUNT + 1))
      echo "$(date): [HEALTH PROBE WARN] Status $PROBE_STATUS on $CURRENT_ACTIVE_URL (fail $FAIL_COUNT/3)" >> $HOME/nuclear_supervisor.log
      if [ "$FAIL_COUNT" -ge 3 ]; then
        echo "$(date): [CRITICAL] 3 consecutive tunnel probe failures. Re-spawning cloudflared..." >> $HOME/nuclear_supervisor.log
        IS_TUNNEL_DEAD=1
        FAIL_COUNT=0
      fi
    fi
  fi

  if [ "$IS_TUNNEL_DEAD" -eq 1 ]; then
    echo "$(date): [RECOVERY] Re-spawning cloudflared tunnel..." >> $HOME/nuclear_supervisor.log
    killall -9 cloudflared 2>/dev/null || true
    sleep 1
    cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    LAST_PROBE_TIME=$(date +%s)
    FAIL_COUNT=0
    sleep 3
  fi

  # F. Broadcaster: Sync Live Tunnel URL to Cloudflare Pages and GitHub
  URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)
  if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
    echo "$URL" > $HOME/current_url.txt

    # 1. Direct Edge Registration with Multi-Attempt Exponential Retry
    for RETRY in 1 2 3 4 5; do
      REG_RESP=$(curl -s -m 5 -X POST https://phone-whisper-server.pages.dev/register_tunnel \
        -H "Content-Type: application/json" \
        -d '{"endpoint": "'"$URL"'", "secret": "mobile_ai_nuclear_key"}' 2>/dev/null || echo "")
      if echo "$REG_RESP" | grep -q "registered"; then
        echo "$(date): [EDGE-SYNC] Successfully registered tunnel with Cloudflare Edge (attempt $RETRY)" >> $HOME/nuclear_supervisor.log
        break
      fi
      sleep 1
    done

    # 2. Push to GitHub Repo
    if [ -d "$HOME/phone-whisper-server" ]; then
      cd $HOME/phone-whisper-server
      git pull --rebase origin main 2>/dev/null || true
      cat << JSON_EOF > endpoint.json
{
  "endpoint": "$URL",
  "inference": "$URL/inference",
  "telemetry": "$URL/telemetry",
  "phone_lan_ip": "http://192.168.29.2:8080",
  "mode": "dual_worldwide_and_local",
  "port": 8080,
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON_EOF
      git add endpoint.json 2>/dev/null || true
      git commit -m "chore(tunnel): Nuclear auto-sync live endpoint [$URL]" 2>/dev/null || true
      if git push origin main 2>/dev/null; then
        SYNCED_URL="$URL"
        echo "$(date): [SUCCESS] Synced fresh tunnel URL to GitHub: $URL" >> $HOME/nuclear_supervisor.log
      fi
    fi
  fi

  # G. Periodic Log Truncation (Keep logs under 1000 lines every 30 mins)
  if [ $((NOW - LAST_LOG_TRIM)) -ge 1800 ]; then
    LAST_LOG_TRIM=$NOW
    for LOG_FILE in "$HOME/nuclear_supervisor.log" "$HOME/gateway.log" "$HOME/cf_tunnel.log"; do
      if [ -f "$LOG_FILE" ]; then
        tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
      fi
    done
  fi

  sleep 3
done
