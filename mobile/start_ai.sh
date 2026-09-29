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

# Allow USB charging so the hardware never runs out of battery
dumpsys battery reset 2>/dev/null || true

# 2. Start Persistent Android Kernel Battery Daemon
if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
  /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
fi

# 3. Start Multi-Modal Gateway Server (:8080)
if [ -f "/sdcard/Download/gateway.py" ]; then
  cp -f /sdcard/Download/gateway.py $HOME/gateway.py 2>/dev/null || true
fi
if ! pgrep -f "gateway.py" > /dev/null; then
  python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
fi

# 4. Start Cloudflared Tunnel
TUNNEL_START_TIME=$(date +%s)
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
  TUNNEL_START_TIME=$(date +%s)
fi

SYNCED_URL=""
LAST_PROBE_TIME=$(date +%s)
LAST_LOG_TRIM=$(date +%s)
LAST_PAGES_HEARTBEAT=0
FAIL_COUNT=0
GW_FAIL_COUNT=0

while true; do
  NOW=$(date +%s)

  # A. Battery check: Ensure device charges properly

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
      if [ "$GW_FAIL_COUNT" -ge 12 ]; then
        GW_ALIVE=0
        GW_FAIL_COUNT=0
      fi
    else
      GW_FAIL_COUNT=0
    fi
  fi

  if [ "$GW_ALIVE" -eq 0 ]; then
    echo "$(date): [CRITICAL] gateway.py dead/unresponsive! Re-spawning..." >> $HOME/nuclear_supervisor.log
    pkill -9 -f "gateway.py" 2>/dev/null || true
    sleep 1
    if [ -f "/sdcard/Download/gateway.py" ]; then
      cp -f /sdcard/Download/gateway.py $HOME/gateway.py 2>/dev/null || true
    fi
    python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
    sleep 3
  fi

  # D. Verify Cloudflared Process (PID check + pgrep fallback)
  IS_TUNNEL_DEAD=0
  CF_ALIVE=0
  if [ -f "$HOME/cloudflared.pid" ]; then
    CF_PID=$(cat "$HOME/cloudflared.pid" 2>/dev/null)
    if [ -n "$CF_PID" ] && kill -0 "$CF_PID" 2>/dev/null; then
      CF_ALIVE=1
    fi
  fi
  if [ "$CF_ALIVE" -eq 0 ] && pgrep -x "cloudflared" > /dev/null; then
    CF_ALIVE=1
  fi

  # Don't restart if tunnel was launched recently (<90 seconds ago)
  if [ "$CF_ALIVE" -eq 0 ] && [ $((NOW - TUNNEL_START_TIME)) -ge 90 ]; then
    IS_TUNNEL_DEAD=1
  fi

  # E. Active Worldwide Tunnel Health Probe (Every 30s with 90s startup grace period)
  CURRENT_ACTIVE_URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)
  if [ -n "$CURRENT_ACTIVE_URL" ] && [ $((NOW - TUNNEL_START_TIME)) -ge 90 ] && [ $((NOW - LAST_PROBE_TIME)) -ge 30 ]; then
    LAST_PROBE_TIME=$NOW
    PROBE_STATUS=$(curl -s -4 -m 10 -o /dev/null -w "%{http_code}" "$CURRENT_ACTIVE_URL/telemetry" 2>/dev/null)
    if [ -z "$PROBE_STATUS" ]; then
      PROBE_STATUS="000"
    fi
    if [ "$PROBE_STATUS" = "200" ]; then
      FAIL_COUNT=0
    else
      FAIL_COUNT=$((FAIL_COUNT + 1))
      echo "$(date): [HEALTH PROBE WARN] Status $PROBE_STATUS on $CURRENT_ACTIVE_URL (fail $FAIL_COUNT/8)" >> $HOME/nuclear_supervisor.log
      if [ "$FAIL_COUNT" -ge 8 ]; then
        echo "$(date): [CRITICAL] 8 consecutive tunnel probe failures. Triggering Qwen 0.5B SLM Self-Healing..." >> $HOME/nuclear_supervisor.log
        IS_TUNNEL_DEAD=1
        FAIL_COUNT=0
      fi
    fi
  fi

  if [ "$IS_TUNNEL_DEAD" -eq 1 ]; then
    echo "$(date): [RECOVERY] Triggering Qwen 0.5B SLM Self-Healing for Cloudflared tunnel..." >> $HOME/nuclear_supervisor.log
    if [ -f "$HOME/slm_self_heal.py" ]; then
      python3 $HOME/slm_self_heal.py >> $HOME/slm_self_heal.log 2>&1 || true
    fi
    pkill -9 -x "cloudflared" 2>/dev/null || true
    sleep 1
    cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
    echo $! > $HOME/cloudflared.pid
    TUNNEL_START_TIME=$(date +%s)
    LAST_PROBE_TIME=$(date +%s)
    FAIL_COUNT=0
    sleep 5
  fi

  # F. Broadcaster: Sync Live Tunnel URL to Cloudflare Pages and GitHub
  URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)

  # 1. Periodic Edge Pulse (Every 45s keeps ephemeral Cloudflare Pages memory hot)
  if [ -n "$URL" ] && [ $((NOW - LAST_PAGES_HEARTBEAT)) -ge 45 ]; then
    LAST_PAGES_HEARTBEAT=$NOW
    curl -s -m 4 -X POST https://phone-whisper-server.pages.dev/register_tunnel \
      -H "Content-Type: application/json" \
      -d '{"endpoint": "'"$URL"'", "secret": "mobile_ai_nuclear_key"}' >/dev/null 2>&1 &
  fi

  if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
    echo "$URL" > $HOME/current_url.txt

    # Immediate Edge Registration with Exponential Retry
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

    # 2. Push to GitHub Repo with Clean Fast-Forward
    GIT_OK=0
    if [ -d "$HOME/phone-whisper-server/.git" ]; then
      cd $HOME/phone-whisper-server
      git fetch origin main 2>/dev/null || true
      git reset --hard origin/main 2>/dev/null || true
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
      sed -i "s|const DEFAULT_FALLBACK_ORIGIN = \".*\";|const DEFAULT_FALLBACK_ORIGIN = \"$URL\";|" functions/_proxy.js 2>/dev/null || true
      git add endpoint.json functions/_proxy.js 2>/dev/null || true
      git commit -m "chore(tunnel): Autonomous sync live endpoint [$URL]" 2>/dev/null || true
      if git push origin main 2>/dev/null; then
        echo "$(date): [SUCCESS] Synced fresh tunnel URL to GitHub: $URL" >> $HOME/nuclear_supervisor.log
        GIT_OK=1
      else
        echo "$(date): [GIT-WARN] Failed git push from phone to origin main" >> $HOME/nuclear_supervisor.log
      fi
    fi

    # ONLY mark as synced if git push succeeded so it retries until GitHub is updated
    if [ "$GIT_OK" -eq 1 ]; then
      SYNCED_URL="$URL"
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
