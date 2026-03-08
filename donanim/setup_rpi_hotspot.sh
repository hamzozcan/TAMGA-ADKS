#!/bin/bash
# TAMGA-ADKS Raspberry Pi Offline Hotspot Kurulum Scripti
# Geliştiren: Antigravity AI
# © 2026

echo "--------------------------------------------------"
echo "TAMGA-ADKS Offline Hotspot Kurulumu Başlatılıyor..."
echo "--------------------------------------------------"

# 1. Gerekli paketleri yükle
echo "[1/7] Paketler güncelleniyor ve gerekli yazılımlar kuruluyor..."
sudo apt-get update
sudo apt-get install -y hostapd dnsmasq iptables python3-flask python3-pip python3-serial

# 2. Servisleri durdur (yapılandırma sırasında çakışma olmaması için)
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# 3. Hostapd yapılandırması (Wi-Fi AP)
echo "[2/7] Wi-Fi Yayını Yapılandırılıyor (SSID: adks)..."
sudo bash -c "cat << EOF > /etc/hostapd/hostapd.conf
interface=wlan0
ssid=adks
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
driver=nl80211
# WPA2 Ayarları (Şifre en az 8 karakter olmalıdır!)
wpa=2
wpa_passphrase=adks1234
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF"

sudo sed -i 's/#DAEMON_CONF=""/DAEMON_CONF="\/etc\/hostapd\/hostapd.conf"/' /etc/default/hostapd

# 4. Dnsmasq yapılandırması (DHCP + DNS Redirection)
echo "[3/7] IP Atama ve Yönlendirme Yapılandırılıyor..."
sudo bash -c "cat << EOF > /etc/dnsmasq.conf
interface=wlan0
dhcp-range=172.16.7.10,172.16.7.50,255.255.255.0,24h
# Tüm DNS isteklerini kendine yönelt
address=/#/172.16.7.169
dhcp-option=3,172.16.7.169
dhcp-option=6,172.16.7.169
EOF"

# 5. wpa_supplicant'ı devre dışı bırak (wlan0 için)
echo "[4/7] wlan0 arayüzü yapılandırılıyor..."
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    sudo bash -c "cat << EOF >> /etc/dhcpcd.conf
interface wlan0
    static ip_address=172.16.7.169/24
    nohook wpa_supplicant
EOF"
fi

# 6. IPTables ve Yönlendirme (Port 80 -> 80) 
# Flask sunucusu 80 portunda çalışacaksa doğrudan yönlendirmeye gerek kalmayabilir
# Ama captive portal için tüm portları 80'e veya sunucunun portuna çekmek gerekebilir.
echo "[5/7] Firewall ve Yönlendirme Kuralları Uygulanıyor..."
sudo bash -c "echo 1 > /proc/sys/net/ipv4/ip_forward"
sudo iptables -F
sudo iptables -t nat -F
# HTTP (80) isteklerini doğrudan işlemek için (opsiyonel)
# sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-port 80

# 7. Servisleri Başlat
echo "[6/7] Servisler Başlatılıyor..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
sudo systemctl restart dhcpcd

# 8. Flask Sunucu Servis Dosyası (Eğer yoksa)
echo "[7/7] TAMGA-ADKS Servisi Yapılandırılıyor..."
S_PATH="/etc/systemd/system/tamga_offline.service"
U_NAME=$(whoami)
P_DIR=$(pwd)

sudo bash -c "cat << EOF > $S_PATH
[Unit]
Description=TAMGA-ADKS Offline Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 $P_DIR/orange_pi_search_server.py
WorkingDirectory=$P_DIR
User=$U_NAME
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable tamga_offline.service

echo "--------------------------------------------------"
echo "KURULUM TAMAMLANDI!"
echo "--------------------------------------------------"
echo "WiFi Adı: TAMGA VERİ YÖNETİM (Şifresiz)"
echo "Sunucu Adresi: http://192.168.4.1"
echo "--------------------------------------------------"
echo "Lütfen sistemi yeniden başlatın: sudo reboot"
echo "--------------------------------------------------"
