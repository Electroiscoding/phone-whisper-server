#!/system/bin/sh
# 📶 PHONEWHISPER AUTONOMOUS WI-FI AUTO-RECONNECT GUARDIAN
# Ensures continuous Wi-Fi connection to saved ideal network (e.g. 'Soham')

LOG_FILE="/data/local/tmp/wifi_daemon.log"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log "📶 Autonomous Wi-Fi Guardian Started"

while true; do
  # 1. Check if wlan0 has an active IPv4 address
  WLAN_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oE "inet [0-9.]+" | awk '{print $2}')
  
  if [ -z "$WLAN_IP" ]; then
    log "⚠️ Wi-Fi Disconnected or No IP detected on wlan0. Triggering auto-reconnect..."
    /system/bin/svc wifi enable
    sleep 3
    # Try re-enabling if still no IP
    WLAN_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oE "inet [0-9.]+" | awk '{print $2}')
    if [ -z "$WLAN_IP" ]; then
      /system/bin/svc wifi disable
      sleep 1
      /system/bin/svc wifi enable
      log "🔄 Cycled Wi-Fi interface. Auto-associating with saved network..."
    fi
  else
    # 2. Check ping to local router / gateway
    GATEWAY_IP=$(ip route show dev wlan0 2>/dev/null | grep default | awk '{print $3}')
    if [ -n "$GATEWAY_IP" ]; then
      ping -c 1 -W 2 "$GATEWAY_IP" >/dev/null 2>&1
      if [ $? -ne 0 ]; then
        log "⚠️ Gateway $GATEWAY_IP unreachable. Enforcing Wi-Fi wakeup..."
        /system/bin/svc wifi enable
      fi
    fi
  fi

  sleep 5
done
