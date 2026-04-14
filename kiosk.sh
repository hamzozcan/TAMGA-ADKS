#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# TAMGA-ADKS Kiosk Session
# Raspberry Pi'de tam ekran Chromium kiosk modu başlatır.
# Tek ekran: ana TAMGA arayüzü
# Çift ekran: ana TAMGA + GPS ekranı
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

TAMGA_PORT="${TAMGA_PORT:-8000}"
TAMGA_START_PATH="${TAMGA_START_PATH:-/}"
TAMGA_GPS_SCREEN_PATH="${TAMGA_GPS_SCREEN_PATH:-/gps-screen}"
TAMGA_BASE_URL="http://127.0.0.1:${TAMGA_PORT}"
TAMGA_URL="${TAMGA_BASE_URL}${TAMGA_START_PATH}"
TAMGA_GPS_URL="${TAMGA_BASE_URL}${TAMGA_GPS_SCREEN_PATH}"
DISPLAY_ENV="${DISPLAY:-:0}"
export DISPLAY="$DISPLAY_ENV"
export HOME="${HOME:-/home/tamga}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/tamga-runtime}"

mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true

log() { echo "[$(date '+%H:%M:%S')] [KIOSK] $*"; }

# ── X sunucusu yoksa başlat ───────────────────────────────────────
x_started_here=false
if ! xset q &>/dev/null; then
    if [ -f /tmp/.X0-lock ] && ! pgrep -f 'Xorg :0|Xwayland .*:0' >/dev/null 2>&1; then
        rm -f /tmp/.X0-lock /tmp/.X11-unix/X0 2>/dev/null || true
    fi
    log "X sunucusu başlatılıyor (Xorg :0)..."
    Xorg :0 -nocursor -nolisten tcp -novtswitch -ac vt1 &
    XPID=$!
    x_started_here=true
    for i in $(seq 1 30); do
        DISPLAY=:0 xset q &>/dev/null && break
        sleep 0.5
    done
    log "X sunucusu hazır (PID: $XPID)"
fi

# ── Ekran koruyucuyu kapat ───────────────────────────────────────
DISPLAY=:0 xset s off || true
DISPLAY=:0 xset -dpms || true
DISPLAY=:0 xset s noblank || true
DISPLAY=:0 xsetroot -solid "#0a0a0f" || true
if command -v setxkbmap &>/dev/null; then
    DISPLAY=:0 setxkbmap -option terminate:none -option altwin:none || true
fi

if command -v openbox >/dev/null 2>&1 && ! pgrep -u "$(id -u)" -x openbox >/dev/null 2>&1; then
    openbox >/dev/null 2>&1 &
fi

if command -v unclutter &>/dev/null; then
    unclutter -idle 1 -root &
fi

if command -v feh &>/dev/null; then
    feh --bg-fill /opt/tamga-adks/static/splash.png 2>/dev/null || DISPLAY=:0 xsetroot -solid "#0a0a0f"
fi

log "Backend bekleniyor ($TAMGA_URL)..."
for i in $(seq 1 60); do
    curl -sf "$TAMGA_BASE_URL/api/health" >/dev/null 2>&1 && break
    sleep 1
done

BACKEND_STATUS=$(curl -sf "$TAMGA_BASE_URL/api/health" 2>/dev/null || true)
if [ -z "$BACKEND_STATUS" ]; then
    log "HATA: Backend $TAMGA_URL adresinde yanıt vermiyor!"
    exit 1
fi

if command -v chromium-browser &>/dev/null; then CHROME=chromium-browser
elif command -v chromium &>/dev/null; then CHROME=chromium
elif command -v google-chrome &>/dev/null; then CHROME=google-chrome
else
    log "HATA: Chromium bulunamadı!"
    exit 1
fi

MAIN_PROFILE="$HOME/.config/tamga-chromium-main"
GPS_PROFILE="$HOME/.config/tamga-chromium-gps"
mkdir -p "$MAIN_PROFILE/Default" "$GPS_PROFILE/Default"
for p in "$MAIN_PROFILE" "$GPS_PROFILE"; do
    echo '{"exit_type":"Normal","exited_cleanly":true}' > "$p/Default/Preferences" 2>/dev/null || true
done

get_monitor_geometry() {
    local selector="$1"
    local mode="${2:-index}"
    local line
    if [ "$mode" = "name" ]; then
        line=$(DISPLAY=:0 xrandr --listmonitors 2>/dev/null | awk -v target="$selector" 'NR>1 && $NF == target {print $0; exit}')
    else
        line=$(DISPLAY=:0 xrandr --listmonitors 2>/dev/null | awk -v target="$selector" 'NR>1 && $1 ~ (target ":") {print $0}')
    fi
    if [ -z "$line" ]; then
        return 1
    fi
    python3 - "$line" <<'PY'
import re, sys
line = sys.argv[1]
m = re.search(r'(\d+)/(?:\d+)x(\d+)/(?:\d+)\+(\d+)\+(\d+)', line)
if not m:
    raise SystemExit(1)
print(' '.join(m.groups()))
PY
}

map_touch_to_output() {
    local device_name="$1"
    local output_name="$2"
    local device_id=""
    device_id=$(DISPLAY=:0 xinput --list --id-only "$device_name" 2>/dev/null | head -n1 || true)
    if [ -n "$device_id" ]; then
        DISPLAY=:0 xinput map-to-output "$device_id" "$output_name" >/dev/null 2>&1 || true
        log "Dokunmatik eşlendi: $device_name -> $output_name"
    fi
}

launch_window() {
    local profile="$1"
    local url="$2"
    local x="$3"
    local y="$4"
    local w="$5"
    local h="$6"
    local label="$7"

    log "$label ekranı açılıyor: $url @ ${x},${y} ${w}x${h}"
    local log_file="$XDG_RUNTIME_DIR/$(basename "$profile").log"
    nohup env DISPLAY=:0 "$CHROME" \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --no-first-run \
        --no-default-browser-check \
        --disable-session-crashed-bubble \
        --disable-restore-session-state \
        --disable-translate \
        --disable-features=TranslateUI,Translate,MediaRouter,GlobalMediaControls,AutofillServerCommunication \
        --disable-sync \
        --disable-component-update \
        --disable-background-networking \
        --disable-dev-shm-usage \
        --kiosk-printing \
        --incognito \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --disable-context-menu \
        --remote-debugging-port=0 \
        --user-data-dir="$profile" \
        --app="$url" \
        --window-position="$x,$y" \
        --window-size="$w,$h" \
        --start-fullscreen \
        </dev/null >"$log_file" 2>&1 &
    LAUNCH_PID=$!
}

monitor_count=$(DISPLAY=:0 xrandr --listmonitors 2>/dev/null | awk 'NR==1 {print $2}' || echo 1)
if [ -z "$monitor_count" ]; then
    monitor_count=1
fi
log "Monitor sayısı: $monitor_count"

MAIN_GEOM=""
for output_name in HDMI-A-1 HDMI-1 HDMI-A-2 HDMI-2; do
    MAIN_GEOM=$(get_monitor_geometry "$output_name" name 2>/dev/null || true)
    [ -n "$MAIN_GEOM" ] && break
done
if [ -z "$MAIN_GEOM" ]; then
    MAIN_GEOM=$(get_monitor_geometry 0 2>/dev/null || echo "1920 1080 0 0")
fi
read -r MAIN_W MAIN_H MAIN_X MAIN_Y <<<"$MAIN_GEOM"

GPS_GEOM=""
if [ "$monitor_count" -ge 2 ]; then
    for output_name in DSI-1 DSI-0; do
        GPS_GEOM=$(get_monitor_geometry "$output_name" name 2>/dev/null || true)
        [ -n "$GPS_GEOM" ] && break
    done
    if [ -z "$GPS_GEOM" ]; then
        GPS_GEOM=$(get_monitor_geometry 1 2>/dev/null || true)
    fi
fi

log "Ana ekran geometri: $MAIN_W x $MAIN_H @ $MAIN_X,$MAIN_Y"
if [ -n "$GPS_GEOM" ]; then
    read -r GPS_W GPS_H GPS_X GPS_Y <<<"$GPS_GEOM"
    log "GPS ekran geometri: $GPS_W x $GPS_H @ $GPS_X,$GPS_Y"
fi

for output_name in HDMI-A-1 HDMI-1 HDMI-A-2 HDMI-2; do
    if DISPLAY=:0 xrandr --listmonitors 2>/dev/null | awk -v target="$output_name" 'NR>1 && $NF == target {found=1} END {exit(found?0:1)}'; then
        map_touch_to_output "WaveShare WS170120" "$output_name"
        break
    fi
done

for output_name in DSI-1 DSI-0; do
    if DISPLAY=:0 xrandr --listmonitors 2>/dev/null | awk -v target="$output_name" 'NR>1 && $NF == target {found=1} END {exit(found?0:1)}'; then
        map_touch_to_output "10-0038 generic ft5x06 (79)" "$output_name"
        break
    fi
done

while true; do
    launch_window "$MAIN_PROFILE" "$TAMGA_URL" "$MAIN_X" "$MAIN_Y" "$MAIN_W" "$MAIN_H" "Ana"
    MAIN_PID="$LAUNCH_PID"
    GPS_PID=""

    if [ -n "$GPS_GEOM" ]; then
        launch_window "$GPS_PROFILE" "$TAMGA_GPS_URL" "$GPS_X" "$GPS_Y" "$GPS_W" "$GPS_H" "GPS"
        GPS_PID="$LAUNCH_PID"
    fi

    while true; do
        sleep 2
        if ! kill -0 "$MAIN_PID" >/dev/null 2>&1; then
            log "Ana ekran kapandi, ikisi de yeniden acilacak"
            break
        fi
        if [ -n "$GPS_PID" ] && ! kill -0 "$GPS_PID" >/dev/null 2>&1; then
            log "GPS ekran kapandi, ikisi de yeniden acilacak"
            break
        fi
    done

    kill "$MAIN_PID" >/dev/null 2>&1 || true
    if [ -n "$GPS_PID" ]; then
        kill "$GPS_PID" >/dev/null 2>&1 || true
    fi
    pkill -f "$MAIN_PROFILE" >/dev/null 2>&1 || true
    pkill -f "$GPS_PROFILE" >/dev/null 2>&1 || true
    sleep 3
done
