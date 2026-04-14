#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TAMGA-ADKS — Raspberry Pi Kurulum Scripti
# ═══════════════════════════════════════════════════════════════════
# Desteklenen platformlar:
#   Raspberry Pi OS (Bookworm / Bullseye) — 32/64-bit
#   Debian tabanlı diğer dağıtımlar
#
# Çalıştırma:
#   sudo bash install_rpi.sh
#
# Ne yapar:
#   1. Sistem bağımlılıklarını kurar (X11, Chromium, Python3)
#   2. /opt/tamga-adks altına projeyi kopyalar
#   3. Python sanal ortamı + pip paketlerini kurar
#   4. 'tamga' sistem kullanıcısı oluşturur
#   5. Systemd servislerini kurar (backend + kiosk)
#   6. Otomatik login + X boot zinciri yapılandırır
#   7. Sistem boot'ta TAMGA-ADKS açılır
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Renkler ─────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[•]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }
title()   { echo -e "\n${BOLD}${CYAN}══ $* ══${NC}"; }

# ── Root kontrolü ───────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Bu script root olarak çalıştırılmalıdır: sudo bash install_rpi.sh"
fi

# ── Değişkenler ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/tamga-adks"
APP_USER="tamga"
GUI_USER="${SUDO_USER:-adks}"
APP_PORT="8000"
PYTHON_MIN="3.9"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║     TAMGA-ADKS Raspberry Pi Kurulumu         ║"
echo "║     Acil Durum Kimlik Sistemi v2.0           ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Platform kontrolü ───────────────────────────────────────────
ARCH=$(uname -m)
DEB_ARCH=$(dpkg --print-architecture 2>/dev/null || echo "")
OS_ID=$(grep '^ID=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
info "Platform: $ARCH | Debian Arch: $DEB_ARCH | OS: $OS_ID"

IS_RPI=false
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "")
    if echo "$MODEL" | grep -qi "raspberry"; then
        IS_RPI=true
        info "Raspberry Pi tespit edildi: $MODEL"
    fi
fi

USE_SYSTEM_PYTHON=false
if [ "${DEB_ARCH:-}" = "armhf" ]; then
    USE_SYSTEM_PYTHON=true
    warn "armhf tespit edildi; Python bagimliliklari Debian paketleri ile kurulacak"
fi

# ── Python sürüm kontrolü ───────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    error "Python3 bulunamadı. 'sudo apt install python3' çalıştırın."
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python: $PY_VER"

# ── Bağımlılıkları kur ──────────────────────────────────────────
title "Sistem Paketleri Kuruluyor"
apt-get update -qq

PKGS=(
    # Python
    python3-pip python3-venv python3-dev build-essential python3-serial

    # X11 minimum
    xorg xinit openbox x11-xserver-utils xterm

    # Kiosk tarayıcı
    chromium-browser

    # Yardımcı araçlar
    unclutter feh curl wget git bluez bluez-tools rfkill

    # RPi donanım araçları (GPIO, SPI, I2C)
    raspi-config
)

# Mimari bazlı ek paketler
if $IS_RPI; then
    PKGS+=(python3-rpi.gpio python3-spidev python3-gpiozero python3-lgpio i2c-tools)
fi

apt-get install -y --no-install-recommends "${PKGS[@]}" 2>&1 \
    | grep -E "^(Setting up|Installing|E:)" || true
success "Sistem paketleri kuruldu"

# chromium-browser yoksa chromium dene
if ! command -v chromium-browser &>/dev/null && command -v chromium &>/dev/null; then
    ln -sf "$(command -v chromium)" /usr/local/bin/chromium-browser
    success "chromium → chromium-browser sembolik bağlantısı oluşturuldu"
fi

# ── Kullanıcı oluştur ───────────────────────────────────────────
title "Sistem Kullanıcısı Ayarlanıyor"
if ! id -u "$APP_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash \
        -c "TAMGA-ADKS Servis Kullanıcısı" "$APP_USER"
    success "Kullanıcı oluşturuldu: $APP_USER"
else
    info "Kullanıcı zaten var: $APP_USER"
fi

# Donanım gruplarına ekle
for GRP in gpio spi i2c dialout video audio input tty; do
    if getent group "$GRP" &>/dev/null; then
        usermod -aG "$GRP" "$APP_USER" 2>/dev/null || true
    fi
done
success "Donanım grupları atandı"

# ── Proje dosyalarını kopyala ────────────────────────────────────
title "Proje Dosyaları Kuruluyor: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Gerekli dosya ve dizinleri kopyala
rsync -av --exclude='venv' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.git' \
    --exclude='recordings' --exclude='map_cache' \
    --exclude='tts_cache' --exclude='_arsiv' \
    --exclude='logs' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/" \
    2>&1 | grep -v "/$" || \
cp -r "$SCRIPT_DIR"/{tamga_backend.py,tamga_config.json,requirements.txt,templates,static,kiosk.sh} \
    "$INSTALL_DIR/" 2>/dev/null || {
    warn "rsync/cp kısmen başarısız, alternatif yöntem..."
    for f in tamga_backend.py tamga_config.json requirements.txt kiosk.sh; do
        [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/"
    done
    for d in templates static; do
        [ -d "$SCRIPT_DIR/$d" ] && cp -r "$SCRIPT_DIR/$d" "$INSTALL_DIR/"
    done
}

# Veri dizinleri
mkdir -p "$INSTALL_DIR"/{data,logs,recordings,tts_cache,map_cache,_arsiv,belgeler}

# İzinler
chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/kiosk.sh"
success "Proje dosyaları kopyalandı"

# ── Python ortamı ───────────────────────────────────────────────
VENV_DIR="$INSTALL_DIR/venv"
PYTHON_CMD="/usr/bin/python3"
if $USE_SYSTEM_PYTHON; then
    title "Python Sistem Paketleri Kuruluyor"
    apt-get install -y --no-install-recommends \
        python3-fastapi python3-uvicorn python3-pydantic python3-pydantic-core \
        python3-folium python3-qrcode python3-requests python3-websockets \
        python3-serial python3-gpiozero python3-lgpio 2>&1 | grep -E "^(Setting up|Installing|E:)" || true
    success "Python sistem paketleri hazır"
else
    title "Python Sanal Ortamı Kuruluyor"
    if [ ! -d "$VENV_DIR" ]; then
        sudo -u "$APP_USER" python3 -m venv "$VENV_DIR"
        success "Sanal ortam oluşturuldu: $VENV_DIR"
    fi

    info "Paketler kuruluyor (bu işlem birkaç dakika sürebilir)..."
    sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --quiet --no-cache-dir --upgrade pip wheel
    sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --quiet --no-cache-dir -r "$INSTALL_DIR/requirements.txt"

    # RPi'de donanım paketlerini kur
    if $IS_RPI; then
        sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --quiet --no-cache-dir \
            RPi.GPIO mfrc522 pyserial PyBluez gpiozero lgpio 2>/dev/null || \
        warn "Donanım paketleri kısmen kurulamadı (normal - eski RPi OS'larda sistem paketi kullanılır)"
    fi
    PYTHON_CMD="${VENV_DIR}/bin/python"
    success "Python ortamı hazır"
fi

# ── .env dosyası ────────────────────────────────────────────────
title "Ortam Değişkenleri"
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
# TAMGA-ADKS Ortam Değişkenleri
# Bu dosyayi duzenleyerek uretim donanim parametrelerini ayarlayin.

# AI anahtari (istege bagli)
GEMINI_API_KEY=

# Uretim profili
TAMGA_SIMULATE=0
TAMGA_FAKE_HARDWARE=0
TAMGA_PORT=8000
TAMGA_START_PATH=/
TAMGA_GPS_SCREEN_PATH=/gps-screen
TAMGA_AUTO_PREFETCH=0

# LCD durum ekrani
TAMGA_LCD_CLOCK_ENABLED=1
TAMGA_LCD_I2C_ADDRESS=0x27
TAMGA_LCD_I2C_BUS=1
TAMGA_LCD_CLOCK_12H=0
TAMGA_LCD_CLOCK_BLINK=1

# GPS / Arduino SIM808 bridge
TAMGA_GPS_PORT=/dev/ttyUSB0,/dev/ttyACM0,/dev/serial0
TAMGA_GPS_BAUD=115200

# ESP32-CAM biyometrik düğüm
TAMGA_FP_MODE=push
TAMGA_FP_CAPTURE_TIMEOUT=20
TAMGA_DEVICE_SHARED_KEY=
TAMGA_ESP32CAM_DEVICE_NAME=TAMGA-ESP32CAM
TAMGA_ESP32CAM_PUSH_TRANSPORT=wifi-push

# 112 / SIM808 acil cagri akisi
TAMGA_EMERGENCY_CALL_ENABLED=1
TAMGA_EMERGENCY_CALL_MODE=live
TAMGA_EMERGENCY_CALL_TARGET=112
TAMGA_EMERGENCY_BUTTON_ENABLED=1
TAMGA_EMERGENCY_BUTTON_PIN=23
TAMGA_EMERGENCY_BUTTON_HOLD_SECONDS=1.2
TAMGA_AUTOPILOT_AUDIO_ENABLED=1
TAMGA_SIM808_AUDIO_ENABLED=1

# İsteğe bağlı Bluetooth fallback (RFCOMM)
TAMGA_FP_SERIAL_PORT=/dev/rfcomm0
TAMGA_FP_SERIAL_BAUD=115200
TAMGA_FP_BT_ADDRESS=
TAMGA_FP_BT_CHANNEL=1
TAMGA_FP_DEVICE_NAME=TAMGA-ESP32CAM

# Geriye dönük Deneyap değişkenleri (legacy)
TAMGA_DENEYAP_SERIAL_PORT=/dev/rfcomm0
TAMGA_DENEYAP_SERIAL_BAUD=115200
TAMGA_DENEYAP_BT_ADDRESS=
TAMGA_DENEYAP_BT_CHANNEL=1
TAMGA_DENEYAP_DEVICE_NAME=TAMGA-DENEYAP
TAMGA_DENEYAP_CAPTURE_TIMEOUT=8
EOF
    chown "$APP_USER:$APP_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    success ".env dosyası oluşturuldu: $ENV_FILE"
    warn "AI sorgularını kullanmak için GEMINI_API_KEY değerini ayarlayın: nano $ENV_FILE"
fi

# ── Systemd servisleri ───────────────────────────────────────────
title "Systemd Servisleri Kuruluyor"
SYSTEMD_DIR="/etc/systemd/system"

# Backend servisi
cat > "$SYSTEMD_DIR/tamga-adks.service" <<EOF
[Unit]
Description=TAMGA-ADKS Backend v2.0
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_CMD} tamga_launcher.py --headless --port ${APP_PORT}
Restart=always
RestartSec=5s
SupplementaryGroups=gpio spi i2c dialout
EnvironmentFile=-${INSTALL_DIR}/.env
LimitNOFILE=65536
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tamga-adks

[Install]
WantedBy=multi-user.target
EOF

# Kiosk servisi
cat > "$SYSTEMD_DIR/tamga-adks-kiosk.service" <<EOF
[Unit]
Description=TAMGA-ADKS Kiosk Display
After=tamga-adks.service
Requires=tamga-adks.service

[Service]
Type=simple
User=${GUI_USER}
Group=${GUI_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${GUI_USER}/.Xauthority
Environment=HOME=/home/${GUI_USER}
Environment=XDG_RUNTIME_DIR=/tmp/tamga-runtime
ExecStartPre=/bin/mkdir -p /tmp/tamga-runtime
ExecStartPre=/bin/chown ${GUI_USER}:${GUI_USER} /tmp/tamga-runtime
ExecStartPre=/bin/chmod 700 /tmp/tamga-runtime
ExecStartPre=/bin/sh -c "until curl -sf http://127.0.0.1:${APP_PORT}/api/health >/dev/null 2>&1; do sleep 1; done"
ExecStart=${INSTALL_DIR}/kiosk.sh
Restart=always
RestartSec=3s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tamga-kiosk

[Install]
WantedBy=multi-user.target
EOF

cat > "$SYSTEMD_DIR/tamga-deneyap-rfcomm.service" <<EOF
[Unit]
Description=TAMGA Biometric RFCOMM Fallback Binding
After=bluetooth.target
Wants=bluetooth.target

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/donanim/tamga_rfcomm_bind.sh start
ExecStop=${INSTALL_DIR}/donanim/tamga_rfcomm_bind.sh stop

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tamga-adks.service
systemctl enable tamga-adks-kiosk.service
systemctl enable bluetooth 2>/dev/null || true
systemctl enable lightdm 2>/dev/null || true

mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-tamga-x11.conf <<'EOF'
[Seat:*]
user-session=rpd-x
autologin-session=rpd-x
EOF
success "Systemd servisleri etkinleştirildi"

# ── Otomatik X11 boot zinciri ────────────────────────────────────
title "Kiosk Boot Zinciri Yapılandırılıyor"

# tamga kullanıcısı için .xinitrc
XINITRC="/home/$APP_USER/.xinitrc"
cat > "$XINITRC" <<'XINITRC_EOF'
#!/bin/bash
# Kiosk systemd servisi ile başlatılır.
exit 0
XINITRC_EOF
chown "$APP_USER:$APP_USER" "$XINITRC"
chmod +x "$XINITRC"

# .bash_profile: tty1'de otomatik startx kapalı
BASH_PROFILE="/home/$APP_USER/.bash_profile"
cat > "$BASH_PROFILE" <<'PROFILE_EOF'
# Kiosk systemd servisi ile başlatılır.
PROFILE_EOF
chown "$APP_USER:$APP_USER" "$BASH_PROFILE"

# tty1 için otomatik login (autologin.conf)
AUTOLOGIN_DIR="$SYSTEMD_DIR/getty@tty1.service.d"
mkdir -p "$AUTOLOGIN_DIR"
cat > "$AUTOLOGIN_DIR/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${APP_USER} --noclear %I \$TERM
EOF
success "Otomatik login yapılandırıldı (tty1 → $APP_USER)"

mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/10-tamga-kiosk.conf <<'EOF'
Section "ServerFlags"
    Option "DontVTSwitch" "true"
    Option "DontZap" "true"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
EOF
success "Xorg kiosk kilitleme ayarlari yazildi"

# systemd default.target → graphical.target
systemctl set-default graphical.target
systemctl daemon-reload
success "Boot hedefi: graphical.target"

# ── RPi'ye özel SPI/I2C/Kamera etkinleştirme ───────────────────
if $IS_RPI; then
    title "Raspberry Pi Donanım Arayüzleri"

    # /boot/config.txt veya /boot/firmware/config.txt
    BOOT_CONFIG=""
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && BOOT_CONFIG="$f" && break
    done

    if [ -n "$BOOT_CONFIG" ]; then
        # SPI (RFID RC522 için)
        grep -q "^dtparam=spi=on" "$BOOT_CONFIG" \
            || echo "dtparam=spi=on" >> "$BOOT_CONFIG"
        # I2C
        grep -q "^dtparam=i2c_arm=on" "$BOOT_CONFIG" \
            || echo "dtparam=i2c_arm=on" >> "$BOOT_CONFIG"
        # UART (GPS için)
        grep -q "^enable_uart=1" "$BOOT_CONFIG" \
            || echo "enable_uart=1" >> "$BOOT_CONFIG"
        # GPU belleği kiosk için biraz artır
        if ! grep -q "^gpu_mem=" "$BOOT_CONFIG"; then
            echo "gpu_mem=128" >> "$BOOT_CONFIG"
        fi
        success "RPi donanım arayüzleri yapılandırıldı ($BOOT_CONFIG)"
    fi

    raspi-config nonint do_spi 0 2>/dev/null || true
    raspi-config nonint do_i2c 0 2>/dev/null || true
    raspi-config nonint do_serial_hw 0 2>/dev/null || true
    raspi-config nonint do_serial_cons 1 2>/dev/null || true
fi

# ── Servis durumunu kontrol et ───────────────────────────────────
title "Servisler Başlatılıyor"
systemctl start tamga-adks.service
sleep 3

if systemctl is-active --quiet tamga-adks.service; then
    success "tamga-adks.service ÇALIŞIYOR"
    HEALTH=$(curl -sf "http://127.0.0.1:$APP_PORT/api/health" 2>/dev/null)
    if echo "$HEALTH" | grep -q '"status":"ok"'; then
        success "Backend sağlık kontrolü: OK"
    fi
else
    warn "Backend servisi henüz başlatılamadı. Log: journalctl -u tamga-adks -n 20"
fi

# ── Özet ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║          TAMGA-ADKS Kurulumu Tamamlandı!             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${CYAN}Kurulum dizini :${NC} $INSTALL_DIR"
echo -e "  ${CYAN}Servis kullanıcı:${NC} $APP_USER"
echo -e "  ${CYAN}Kiosk kullanıcı :${NC} $GUI_USER"
echo -e "  ${CYAN}Backend adres  :${NC} http://127.0.0.1:$APP_PORT"
echo -e "  ${CYAN}Backend servisi:${NC} systemctl status tamga-adks"
echo -e "  ${CYAN}Kiosk servisi  :${NC} systemctl status tamga-adks-kiosk"
echo -e "  ${CYAN}ESP32-CAM ingest:${NC} POST /api/device/esp32cam/ingest"
echo -e "  ${CYAN}RFCOMM fallback:${NC} systemctl status tamga-deneyap-rfcomm"
echo -e "  ${CYAN}Log görüntüle  :${NC} journalctl -fu tamga-adks"
echo -e "  ${CYAN}.env düzenle   :${NC} nano $INSTALL_DIR/.env"
echo ""
echo -e "${YELLOW}Kiosk modu için sistemi yeniden başlatın:${NC}"
echo -e "  ${BOLD}sudo reboot${NC}"
echo ""
echo -e "${YELLOW}Manuel kiosk testi (şimdi):${NC}"
echo -e "  ${BOLD}sudo -u tamga DISPLAY=:0 /opt/tamga-adks/kiosk.sh${NC}"
echo ""
