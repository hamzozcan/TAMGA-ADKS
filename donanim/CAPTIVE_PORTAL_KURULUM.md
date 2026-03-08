# Captive Portal Kurulum Rehberi

## 🎯 Captive Portal Nedir?

Captive Portal, WiFi ağına bağlanan kullanıcıların doğrudan belirli bir web sayfasına yönlendirildiği bir sistemdir. Kullanıcılar internete erişmeden önce giriş yapmaları veya belirli bilgileri girmeleri gerekebilir.

### **TAMGA-ADKS Captive Portal Özellikleri:**
- 🌐 **WiFi Hotspot:** Kendi WiFi ağınızı oluşturur
- 📱 **Otomatik Yönlendirme:** Bağlanan kullanıcıları doğrudan arayüze yönlendirir
- 🔍 **Kişi Arama:** Kayıtlı kişileri arama imkanı
- 📊 **Veri Yönetimi:** Admin paneli ile tüm verileri yönetme
- 🚫 **İnternet Gerektirmez:** Tamamen offline çalışır

---

## 📋 Gereksinimler

### **Donanım:**
- Orange Pi Zero v1.4 veya Raspberry Pi 4B
- WiFi adaptörü (Orange Pi Zero için dahili)
- USB depolama alanı (opsiyonel)

### **Yazılım:**
- Raspbian veya Armbian OS
- Python 3.7+
- Hostapd (WiFi hotspot için)
- Dnsmasq (DNS ve DHCP için)

---

## 🚀 Kurulum Adımları

### **Adım 1: Sistem Güncelleme**
```bash
# Sistemi güncelle
sudo apt update && sudo apt upgrade -y

# Gerekli paketleri yükle
sudo apt install hostapd dnsmasq -y
```

### **Adım 2: WiFi Arayüzünü Yapılandırma**
```bash
# WiFi arayüzünü kontrol et
iwconfig
# veya
ip link show

# wlan0 arayüzünü durdur (yapılandırma için)
sudo ip link set wlan0 down
```

### **Adım 3: Statik IP Adresi Ayarlama**
```bash
# Network yapılandırma dosyasını düzenle
sudo nano /etc/dhcpcd.conf
```

**Dosya sonuna ekle:**
```ini
# WiFi hotspot için statik IP
interface wlan0
static ip_address=192.168.4.1/24
nohook wpa_supplicant
```

### **Adım 4: Hostapd Yapılandırması**
```bash
# Hostapd yapılandırma dosyası oluştur
sudo nano /etc/hostapd/hostapd.conf
```

**Yapılandırma içeriği:**
```ini
interface=wlan0
driver=nl80211
ssid=TAMGA-ADKS
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=12345678
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
```

### **Adım 5: Hostapd Varsayılan Dosyasını Yapılandırma**
```bash
# Hostapd varsayılan dosyasını düzenle
sudo nano /etc/default/hostapd
```

**Aşağıdaki satırı bul ve düzenle:**
```bash
DAEMON_CONF="/etc/hostapd/hostapd.conf"
```

### **Adım 6: Dnsmasq Yapılandırması**
```bash
# Orijinal dnsmasq dosyasını yedekle
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig

# Yeni dnsmasq yapılandırması oluştur
sudo nano /etc/dnsmasq.conf
```

**Yapılandırma içeriği:**
```ini
# DNS ve DHCP ayarları
interface=wlan0
domain=local
dhcp-range=192.168.4.2,192.168.4.20,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
server=8.8.8.8

# Captive portal yönlendirmesi
address=/#/192.168.4.1
```

### **Adım 7: IP Yönlendirme ve Maskeleme**
```bash
# IP yönlendirmeyi aktif et
sudo nano /etc/sysctl.conf
```

**Aşağıdaki satırın başındaki # kaldır:**
```ini
net.ipv4.ip_forward=1
```

**Değişikliği uygula:**
```bash
sudo sysctl -p
```

### **Adım 8: NAT Maskeleme**
```bash
# NAT kurallarını ekle
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sudo iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT

# Kuralları kaydet
sudo sh -c "iptables-save > /etc/iptables.ipv4.nat"
```

**Otomatik yüklemek için:**
```bash
# RC.local dosyasını düzenle
sudo nano /etc/rc.local
```

**exit 0 satırından önce ekle:**
```bash
iptables-restore < /etc/iptables.ipv4.nat
```

### **Adım 9: Servisleri Yeniden Başlatma**
```bash
# Servisleri yeniden başlat
sudo systemctl restart dhcpcd
sudo systemctl restart dnsmasq
sudo systemctl restart hostapd

# Servisleri aktif et (açılışta başlasın)
sudo systemctl enable dhcpcd
sudo systemctl enable dnsmasq
sudo systemctl enable hostapd
```

---

## 🌐 Captive Portal DNS Yönlendirmesi

### **Tüm İstekleri Yönlendirme**
```bash
# Dnsmasq yapılandırmasını güncelle
sudo nano /etc/dnsmasq.conf
```

**Aşağıdaki satırları ekle:**
```ini
# Captive portal için DNS yönlendirmesi
address=/#/192.168.4.1
address=/google.com/192.168.4.1
address=/facebook.com/192.168.4.1
address=/instagram.com/192.168.4.1
address=/twitter.com/192.168.4.1
address=/youtube.com/192.168.4.1

# HTTPS siteleri için
address=/https://*/192.168.4.1
```

### **Daha Kapsamlı Yönlendirme**
```bash
# Geniş DNS yönlendirme dosyası oluştur
sudo nano /etc/dnsmasq.d/01-captive-portal.conf
```

**İçerik:**
```ini
# Captive portal DNS yönlendirmeleri
server=/#/192.168.4.1
address=/#/192.168.4.1

# Popüler siteler
address=/google.com/192.168.4.1
address=/facebook.com/192.168.4.1
address=/youtube.com/192.168.4.1
address=/instagram.com/192.168.4.1
address=/twitter.com/192.168.4.1
address=/whatsapp.com/192.168.4.1
address=/telegram.com/192.168.4.1
address=/tiktok.com/192.168.4.1
address=/netflix.com/192.168.4.1

# Türk siteleri
address=/google.com.tr/192.168.4.1
address=/yandex.com.tr/192.168.4.1
address=/yandex.ru/192.168.4.1
address=/haberturk.com/192.168.4.1
address=/ntv.com.tr/192.168.4.1
address=/trt.net.tr/192.168.4.1
address=/milliyet.com.tr/192.168.4.1
address=/sabah.com.tr/192.168.4.1
address=/hurriyet.com.tr/192.168.4.1
address=/posta.com.tr/192.168.4.1
address=/takvim.com.tr/192.168.4.1
address=/fotomac.com.tr/192.168.4.1
address=/fanatik.com.tr/192.168.4.1
address=/amkspor.com/192.168.4.1
address=/ajansspor.com/192.168.4.1
address=/ntvspor.net/192.168.4.1
address=/beinsports.com.tr/192.168.4.1
address=/sahadan.com/192.168.4.1
address=/exxen.com/192.168.4.1
address=/blutv.com.tr/192.168.4.1
address=/tvplus.com.tr/192.168.4.1
address=/digiturk.com.tr/192.168.4.1
address=/tivibu.com.tr/192.168.4.1

# Sosyal medya
address=/linkedin.com/192.168.4.1
address=/snapchat.com/192.168.4.1
address=/pinterest.com/192.168.4.1
address=/reddit.com/192.168.4.1
address=/tumblr.com/192.168.4.1
address=/discord.com/192.168.4.1
address=/skype.com/192.168.4.1
address=/zoom.us/192.168.4.1
address=/teams.microsoft.com/192.168.4.1

# E-ticaret
address=/hepsiburada.com/192.168.4.1
address=/trendyol.com/192.168.4.1
address=/n11.com/192.168.4.1
address=/gittigidiyor.com/192.168.4.1
address=/amazon.com/192.168.4.1
address=/amazon.com.tr/192.168.4.1
address=/hepsiburada.com/192.168.4.1
address=/trendyol.com/192.168.4.1
address=/n11.com/192.168.4.1
address=/gittigidiyor.com/192.168.4.1

# Haber ve medya
address=/bbc.com/192.168.4.1
address=/cnn.com/192.168.4.1
address=/reuters.com/192.168.4.1
address=/apnews.com/192.168.4.1
address=/aljazeera.com/192.168.4.1
address=/dw.com/192.168.4.1
address=/rfi.fr/192.168.4.1
address=/voa.com/192.168.4.1
address=/euronews.com/192.168.4.1
```

---

## 🔧 TAMGA-ADKS Sunucu Entegrasyonu

### **Sunucu Portunu Yapılandırma**
```bash
# TAMGA-ADKS sunucusunu 80 portunda çalıştır
cd /home/pi/TAMGA-ADKS

# Port değişikliği (80 portunda çalışması için)
sudo nano orange_pi_server.py
```

**Port değişikliği:**
```python
# app.run(host='0.0.0.0', port=8080, debug=True)
app.run(host='0.0.0.0', port=80, debug=False)
```

### **Nginx Kurulumu (Opsiyonel)**
```bash
# Nginx kurulumu
sudo apt install nginx -y

# Nginx yapılandırması
sudo nano /etc/nginx/sites-available/tamga-adks
```

**Nginx yapılandırması:**
```nginx
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Site'ı aktif et:**
```bash
sudo ln -s /etc/nginx/sites-available/tamga-adks /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

## 📱 Mobil Cihazlarda Captive Portal

### **iOS Cihazlar için:**
iOS cihazlar captive portal'ı otomatik olarak algılar ve giriş ekranını gösterir.

### **Android Cihazlar için:**
Android cihazlar da captive portal'ı otomatik olarak algılar.

### **Windows/Mac için:**
Tarayıcıda otomatik olarak açılır veya manuel olarak `http://192.168.4.1` adresine gidilir.

---

## 🔍 Test ve Doğrulama

### **WiFi Ağının Testi**
```bash
# WiFi durumunu kontrol et
sudo systemctl status hostapd
sudo systemctl status dnsmasq

# WiFi ağını tara
sudo iwlist wlan0 scan

# Bağlı cihazları gör
sudo iw wlan0 station dump
```

### **DNS Yönlendirme Testi**
```bash
# DNS sorgusu testi
nslookup google.com 192.168.4.1
dig @192.168.4.1 facebook.com
host youtube.com 192.168.4.1
```

### **Captive Portal Testi**
```bash
# Web sunucusu testi
curl -I http://192.168.4.1
wget http://192.168.4.1

# Port kontrolü
netstat -tulpn | grep :80
ss -tulpn | grep :80
```

### **Mobil Test**
1. **Telefonunuzdan WiFi'ye bağlanın:** `TAMGA-ADKS` ağı
2. **Şifre girin:** `12345678`
3. **Otomatik açılan sayfayı kontrol edin**
4. **Arama yapmayı test edin**

---

## 🛠️ Sorun Giderme

### **Yaygın Hatalar ve Çözümleri:**

#### **1. WiFi Ağı Görünmüyor**
```bash
# Hostapd durumunu kontrol et
sudo systemctl status hostapd

# WiFi arayüzünü kontrol et
iwconfig
ip link show

# Hostapd'yi yeniden başlat
sudo systemctl restart hostapd
```

#### **2. Bağlanamıyor**
```bash
# DHCP durumunu kontrol et
sudo systemctl status dnsmasq

# IP adresini kontrol et
ip addr show wlan0

# Dnsmasq'yu yeniden başlat
sudo systemctl restart dnsmasq
```

#### **3. DNS Yönlendirmesi Çalışmıyor**
```bash
# Dnsmasq yapılandırmasını kontrol et
sudo dnsmasq --test

# DNS sorgusu test et
nslookup google.com 192.168.4.1

# Dnsmasq'yu yeniden başlat
sudo systemctl restart dnsmasq
```

#### **4. Captive Portal Açılmıyor**
```bash
# Web sunucusu durumunu kontrol et
sudo systemctl status tamga-adks
# veya
ps aux | grep python

# Port kontrolü
sudo netstat -tulpn | grep :80

# Firewall kontrolü
sudo ufw status
sudo ufw allow 80
```

#### **5. İnternet Erişimi Yok**
```bash
# IP yönlendirme kontrolü
cat /proc/sys/net/ipv4/ip_forward

# NAT kuralları kontrolü
sudo iptables -t nat -L
sudo iptables -L

# İnternet bağlantısı testi
ping 8.8.8.8
```

---

## 📊 Log Dosyaları

### **Servis Logları**
```bash
# Hostapd logları
sudo journalctl -u hostapd -f

# Dnsmasq logları
sudo journalctl -u dnsmasq -f

# TAMGA-ADKS logları
sudo journalctl -u tamga-adks -f

# Sistem logları
tail -f /var/log/syslog
```

### **Ağ Logları**
```bash
# DHCP logları
tail -f /var/log/dnsmasq.log

# Bağlantı logları
sudo tcpdump -i wlan0
```

---

## 🔒 Güvenlik Ayarları

### **WiFi Şifreleme**
```bash
# WiFi şifresini değiştir
sudo nano /etc/hostapd/hostapd.conf

# Şifre satırını güncelle
wpa_passphrase=YENI_SIFRE
```

### **MAC Filtreleme**
```bash
# MAC adresi filtresi ekle
sudo nano /etc/hostapd/hostapd.conf

# Aşağıdaki satırları ekle
macaddr_acl=1
accept_mac_file=/etc/hostapd/accept
deny_mac_file=/etc/hostapd/deny
```

### **Kablosuz Güvenlik**
```bash
# WPA3 desteği (donanım destekliyorsa)
wpa=3
wpa_pairwise=GCMP-256
rsn_pairwise=GCMP-256
```

---

## 📈 Performans Optimizasyonu

### **WiFi Optimizasyonu**
```bash
# Kanal optimizasyonu
sudo iw dev wlan0 set channel 6

# Güç optimizasyonu
sudo iw dev wlan0 set txpower fixed 20
```

### **Sistem Optimizasyonu**
```bash
# Servisleri optimize et
sudo systemctl disable bluetooth
sudo systemctl disable cups

# Bellek optimizasyonu
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

---

## 🔄 Otomasyon ve Bakım

### **Otomatik Yeniden Başlatma**
```bash
# Servis yeniden başlatma betiği
sudo nano /usr/local/bin/restart-captive-portal.sh
```

**Betiğin içeriği:**
```bash
#!/bin/bash
# Captive portal yeniden başlatma betiği

echo "Captive Portal yeniden başlatılıyor..."

sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
sudo systemctl restart tamga-adks

echo "Servisler yeniden başlatıldı!"
```

**Çalıştırma izni:**
```bash
sudo chmod +x /usr/local/bin/restart-captive-portal.sh
```

### **Cron Job ile Otomasyon**
```bash
# Cron job ekle
sudo crontab -e
```

**Eklenecek satırlar:**
```bash
# Her gün saat 03:00'da yeniden başlat
0 3 * * * /usr/local/bin/restart-captive-portal.sh

# Her saat logları temizle
0 * * * * find /var/log -name "*.log" -mtime +7 -delete
```

---

## ✅ Kurulum Kontrol Listesi

### **Kurulum Sonrası Kontrol:**
- [ ] WiFi ağı "TAMGA-ADKS" görünüyor
- [ ] WiFi'ye bağlanılabiliyor (şifre: 12345678)
- [ ] IP adresi alınıyor (192.168.4.x)
- [ ] DNS yönlendirmesi çalışıyor
- [ ] Captive portal sayfası açılıyor
- [ ] TAMGA-ADKS arayüzü çalışıyor
- [ ] Arama fonksiyonu çalışıyor
- [ ] Admin paneli erişilebiliyor
- [ ] Veri kaydetme çalışıyor
- [ ] Mobil cihazlarda test edildi

---

## 🎯 Sonuç

**Başarılı Kurulum!** 🎉

Artık Orange Pi'niz tam fonksiyonel bir Captive Portal olarak çalışıyor:

- 🌐 **WiFi Ağı:** `TAMGA-ADKS`
- 🔑 **Şifre:** `12345678`
- 📱 **Otomatik Yönlendirme:** `http://192.168.4.1`
- 🔍 **Arama Sistemi:** Kişi arama ve veri yönetimi
- 📊 **Admin Paneli:** `hamza` / `ozcann`

**Kullanıcılar WiFi'ye bağlandığında doğrudan TAMGA-ADKS arayüzünü görecekler!** 🚀

---
*TAMGA-ADKS Captive Portal Team*  
*© 2026 Tüm Hakları Saklıdır*
