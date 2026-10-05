#!/data/data/com.termux/files/usr/bin/bash
export PREFIX=/data/data/com.termux/files/usr
export PATH=$PREFIX/bin:$PATH
export HOME=/data/data/com.termux/files/home
export LD_LIBRARY_PATH=$HOME/whisper.cpp/build/bin:$HOME/llama.cpp/build/bin:$PREFIX/lib
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no"

termux-wake-lock 2>/dev/null || true

echo "$(date): [STARTUP] Nuclear AI Supervisor starting..." >> $HOME/nuclear_supervisor.log

dumpsys battery reset 2>/dev/null || true

REPO="$HOME/phone-whisper-server"
SYNCED_URL=""
LAST_PROBE_TIME=$(date +%s)
LAST_LOG_TRIM=$(date +%s)
LAST_PAGES_HEARTBEAT=0
LAST_GIT_PULL=$(date +%s)
FAIL_COUNT=0
GW_FAIL_COUNT=0

pull_latest_code() {
  if [ -d "$REPO/.git" ]; then
    cd "$REPO"
    git fetch origin main 2>/dev/null || true
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)
    if [ "$LOCAL" != "$REMOTE" ]; then
      git reset --hard origin/main 2>/dev/null && \
        echo "$(date): [GIT-PULL] Updated to latest code: $REMOTE" >> $HOME/nuclear_supervisor.log
    fi
    cp -f "$REPO/mobile/gateway.py" "$HOME/gateway.py" 2>/dev/null || true
    cp -f "$REPO/mobile/gridlock.py" "$HOME/gridlock.py" 2>/dev/null || true
    cp -f "$REPO/mobile/start_ai.sh" "$HOME/start_ai.sh" 2>/dev/null || true
    cp -f "$REPO/mobile/slm_self_heal.py" "$HOME/slm_self_heal.py" 2>/dev/null || true
    cp -f "$REPO/monopoly.html" "$HOME/monopoly.html" 2>/dev/null || true
    cp -f "$REPO/maker.md" "$HOME/maker.md" 2>/dev/null || true
    cp -f "$REPO/docs.html" "$HOME/docs.html" 2>/dev/null || true
    cp -f "$REPO/swades.py" "$HOME/swades.py" 2>/dev/null || true
    cp -f "$REPO/swades.js" "$HOME/swades.js" 2>/dev/null || true
  fi
}

start_gateway() {
  pull_latest_code
  python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
  echo "$(date): [START] Launched gateway.py (PID $!)" >> $HOME/nuclear_supervisor.log
}

start_tunnel() {
  cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2 --edge-ip-version 4 --no-autoupdate > $HOME/cf_tunnel.log 2>&1 &
  echo $! > $HOME/cloudflared.pid
  echo "$(date): [TUNNEL] Launched cloudflared (PID $!)" >> $HOME/nuclear_supervisor.log
}

if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
  /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
fi

if ! pgrep -f "gateway.py" > /dev/null; then
  start_gateway
fi

TUNNEL_START_TIME=$(date +%s)
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  start_tunnel
fi

while true; do
  NOW=$(date +%s)

  if ! pgrep -f "battery_daemon.sh" > /dev/null && ! pgrep -f "update_hardware.sh" > /dev/null; then
    /system/bin/sh /data/local/tmp/battery_daemon.sh >/dev/null 2>&1 &
  fi

  if [ $((NOW - LAST_GIT_PULL)) -ge 300 ]; then
    LAST_GIT_PULL=$NOW
    if [ -d "$REPO/.git" ]; then
      cd "$REPO"
      git fetch origin main 2>/dev/null || true
      LOCAL=$(git rev-parse HEAD 2>/dev/null)
      REMOTE=$(git rev-parse origin/main 2>/dev/null)
      if [ "$LOCAL" != "$REMOTE" ]; then
        echo "$(date): [GIT-UPDATE] New code detected, hot-reloading gateway..." >> $HOME/nuclear_supervisor.log
        git reset --hard origin/main 2>/dev/null
        cp -f "$REPO/mobile/gateway.py" "$HOME/gateway.py" 2>/dev/null || true
        cp -f "$REPO/mobile/gridlock.py" "$HOME/gridlock.py" 2>/dev/null || true
        cp -f "$REPO/monopoly.html" "$HOME/monopoly.html" 2>/dev/null || true
        cp -f "$REPO/docs.html" "$HOME/docs.html" 2>/dev/null || true
        cp -f "$REPO/swades.py" "$HOME/swades.py" 2>/dev/null || true
        cp -f "$REPO/swades.js" "$HOME/swades.js" 2>/dev/null || true
        pkill -9 -f "gateway.py" 2>/dev/null || true
        sleep 1
        python3 $HOME/gateway.py >> $HOME/gateway.log 2>&1 &
        echo "$(date): [GIT-RELOAD] Gateway restarted with new code" >> $HOME/nuclear_supervisor.log
        GW_FAIL_COUNT=0
      fi
    fi
  fi

  GW_ALIVE=1
  if ! pgrep -f "gateway.py" > /dev/null; then
    GW_ALIVE=0
  else
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
    echo "$(date): [CRITICAL] gateway.py dead/unresponsive! Re-spawning with latest code..." >> $HOME/nuclear_supervisor.log
    pkill -9 -f "gateway.py" 2>/dev/null || true
    sleep 1
    start_gateway
    sleep 3
  fi

  IS_TUNNEL_DEAD=0
  if ! pgrep -f "cloudflared" > /dev/null; then
    IS_TUNNEL_DEAD=1
  fi

  CURRENT_ACTIVE_URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)
  if [ -n "$CURRENT_ACTIVE_URL" ] && [ $((NOW - TUNNEL_START_TIME)) -ge 90 ] && [ $((NOW - LAST_PROBE_TIME)) -ge 30 ]; then
    LAST_PROBE_TIME=$NOW
    PROBE_STATUS=$(curl -s -4 -m 10 -o /dev/null -w "%{http_code}" "$CURRENT_ACTIVE_URL/telemetry" 2>/dev/null || echo "000")
    if [ "$PROBE_STATUS" = "200" ]; then
      FAIL_COUNT=0
    else
      FAIL_COUNT=$((FAIL_COUNT + 1))
      echo "$(date): [PROBE WARN] Status $PROBE_STATUS on $CURRENT_ACTIVE_URL (fail $FAIL_COUNT/8)" >> $HOME/nuclear_supervisor.log
      if [ "$FAIL_COUNT" -ge 8 ]; then
        IS_TUNNEL_DEAD=1
        FAIL_COUNT=0
      fi
    fi
  fi

  if [ "$IS_TUNNEL_DEAD" -eq 1 ]; then
    echo "$(date): [RECOVERY] Re-spawning cloudflared tunnel..." >> $HOME/nuclear_supervisor.log
    if [ -f "$HOME/slm_self_heal.py" ]; then
      python3 $HOME/slm_self_heal.py >> $HOME/slm_self_heal.log 2>&1 || true
    fi
    pkill -9 -x "cloudflared" 2>/dev/null || true
    sleep 1
    start_tunnel
    TUNNEL_START_TIME=$(date +%s)
    LAST_PROBE_TIME=$(date +%s)
    FAIL_COUNT=0
    sleep 5
  fi

  URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $HOME/cf_tunnel.log 2>/dev/null | grep -v "api.trycloudflare.com" | tail -n 1)

  if [ -n "$URL" ] && [ $((NOW - LAST_PAGES_HEARTBEAT)) -ge 45 ]; then
    LAST_PAGES_HEARTBEAT=$NOW
    curl -s -m 4 -X POST https://phone-whisper-server.pages.dev/register_tunnel \
      -H "Content-Type: application/json" \
      -d '{"endpoint": "'"$URL"'", "secret": "mobile_ai_nuclear_key"}' >/dev/null 2>&1 &
  fi

  if [ -n "$URL" ] && [ "$URL" != "$SYNCED_URL" ]; then
    echo "$URL" > $HOME/current_url.txt

    for RETRY in 1 2 3 4 5; do
      REG_RESP=$(curl -s -m 5 -X POST https://phone-whisper-server.pages.dev/register_tunnel \
        -H "Content-Type: application/json" \
        -d '{"endpoint": "'"$URL"'", "secret": "mobile_ai_nuclear_key"}' 2>/dev/null || echo "")
      if echo "$REG_RESP" | grep -q "registered"; then
        echo "$(date): [EDGE-SYNC] Registered tunnel with Cloudflare Edge (attempt $RETRY)" >> $HOME/nuclear_supervisor.log
        break
      fi
      sleep 1
    done

    GIT_OK=0
    if [ -d "$REPO/.git" ]; then
      cd "$REPO"
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
      git commit -m "chore(tunnel): Auto-sync live endpoint [$URL]" 2>/dev/null || true
      if git push origin main 2>/dev/null; then
        echo "$(date): [SUCCESS] Synced URL to GitHub: $URL" >> $HOME/nuclear_supervisor.log
        GIT_OK=1
      else
        echo "$(date): [GIT-WARN] git push failed from phone, will retry" >> $HOME/nuclear_supervisor.log
      fi
    fi

    if [ "$GIT_OK" -eq 1 ]; then
      SYNCED_URL="$URL"
    fi
  fi

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
