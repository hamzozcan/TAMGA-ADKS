#!/bin/bash
# TAMGA-ADKS Orange Pi Zero Captive Portal Kurulum Scripti
# Geliştiren: Antigravity AI
# © 2026

echo "--------------------------------------------------"
echo "TAMGA-ADKS Sunucu Kurulumu Baslatiliyor..."
echo "--------------------------------------------------"

# 1. Gerekli paketleri yukle
echo "[1/6] Paketler guncelleniyor..."
sudo apt-get update
sudo apt-get install -y hostapd dnsmasq iptables python3-flask python3-pip python3-requests python3-serial

# 2. Servisleri durdur
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# 3. Hostapd yapılandırması (Wi-Fi AP)
echo "[2/6] Wi-Fi Yayin Yapılandırılıyor (SSID: TAMGA)..."
sudo bash -c "cat << EOF > /etc/hostapd/hostapd.conf
interface=wlan0
ssid=TAMGA
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
driver=nl80211
EOF"

sudo sed -i 's/#DAEMON_CONF=""/DAEMON_CONF="\/etc\/hostapd\/hostapd.conf"/' /etc/default/hostapd

# 4. Dnsmasq yapılandırması (DHCP + DNS Redirection)
echo "[3/6] IP Atama ve Yönlendirme Yapılandırılıyor..."
sudo bash -c "cat << EOF > /etc/dnsmasq.conf
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
# Tüm DNS isteklerini kendine yonelt (Captive Portal)
address=/#/192.168.4.1
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
EOF"

# 5. Interface Ayarları
echo "[4/6] Ag Arayüzü Hazırlanıyor..."
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sudo ip addr add 192.168.4.1/24 dev wlan0
sudo ip link set wlan0 up

# 6. IPTables ve Yönlendirme (Port 80 -> 8080)
echo "[5/6] Firewall ve Yönlendirme Kuralları Uygulanıyor..."
sudo bash -c "echo 1 > /proc/sys/net/ipv4/ip_forward"
sudo iptables -F
sudo iptables -t nat -F
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 192.168.4.1:8080
sudo iptables -t nat -A POSTROUTING -j MASQUERADE
sudo sh -c "iptables-save > /etc/iptables.ipv4.nat"

# 7. Servisleri Baslat
echo "[6/6] Servisler Baslatiliyor..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq

echo "--------------------------------------------------"
echo "KURULUM TAMAMLANDI!"
echo "--------------------------------------------------"
echo "WiFi Adi: TAMGA (Sifresiz)"
echo "Sunucu Adresi: http://192.168.4.1:8080"
echo "--------------------------------------------------"
echo "Simdi sunucu yazılımını baslatabilirsiniz:"
echo "python3 /home/$(whoami)/orange_pi_search_server.py"
echo "--------------------------------------------------"
