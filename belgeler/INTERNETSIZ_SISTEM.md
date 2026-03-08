# İnternetsiz TAMGA-ADKS Sistemi - Tam Kurulum Rehberi

## 🎯 Sistem Tanıtımı

TAMGA-ADKS tamamen internet bağlantısı olmadan çalışan offline sistem. WiFi hotspot üzerinden kullanıcıları doğrudan arayüze yönlendirir ve tüm harita verileri yerel olarak çalışır.

### **Özellikler:**
- 🌐 **Offline WiFi Hotspot:** İnternet gerektirmeyen ağ
- 🗺️ **Yerel Harita:** OpenStreetMap tile'ları offline
- 📡 **GPS Takip:** Arduino ile gerçek zamanlı konum
- 🔍 **Arama Sistemi:** Kişi ve veri arama
- 📱 **Responsive:** Tüm cihazlarda çalışır
- 🌙 **Koyu Tema:** Modern arayüz

---

## 📋 Donanım Gereksinimleri

### **Temel Donanım:**
- Raspberry Pi 4B (4GB RAM önerilir)
- Arduino Uno/Nano/Mega
- GPS Modülü (NEO-6M)
- WiFi adaptörü (dahili veya USB)
- USB depolama (32GB+)
- Jumper kablolar
- Breadboard

### **Opsiyonel:**
- Ekran (HDMI)
- Klavye ve mouse
- Güç adaptörleri

---

## 🗺️ Offline Harita Kurulumu

### **Adım 1: Harita Tile'larını İndirme**
```bash
# Harita tile'ları için dizin oluştur
sudo mkdir -p /var/www/html/maps
sudo mkdir -p /var/www/html/maps/{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18}

# İzinleri ver
sudo chown -R pi:pi /var/www/html/maps
sudo chmod -R 755 /var/www/html/maps
```

### **Adım 2: Tile İndirme Script'i**
```bash
# Tile indirme script'i oluştur
nano /home/pi/download_tiles.py
```

**Script içeriği:**
```python
import os
import requests
import time
from math import log, tan, pi, exp

def latlon_to_tile(lat, lon, zoom):
    x = (lon + 180) / 360 * 2**zoom
    y = (1 - log(tan(lat * pi / 180) + 1 / cos(lat * pi / 180)) / pi) / 2 * 2**zoom
    return int(x), int(y)

def download_tile(x, y, zoom, output_dir):
    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    output_path = f"{output_dir}/{zoom}/{x}/{y}.png"
    
    # Dizin oluştur
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"Tile indirildi: {zoom}/{x}/{y}.png")
            return True
        else:
            print(f"Hata: {url} - {response.status_code}")
            return False
    except Exception as e:
        print(f"İndirme hatası {zoom}/{x}/{y}: {e}")
        return False

def download_area_tiles(lat_min, lat_max, lon_min, lon_max, min_zoom, max_zoom, output_dir):
    for zoom in range(min_zoom, max_zoom + 1):
        print(f"Zoom seviyesi {zoom} indiriliyor...")
        
        x_min, y_max = latlon_to_tile(lat_max, lon_min, zoom)
        x_max, y_min = latlon_to_tile(lat_min, lon_max, zoom)
        
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                if download_tile(x, y, zoom, output_dir):
                    time.sleep(0.1)  # Sunucuyu yormamak için

# Türkiye haritası için (Ankara merkezli)
if __name__ == "__main__":
    # Türkiye sınırları (yaklaşık)
    lat_min, lat_max = 35.0, 42.0
    lon_min, lon_max = 25.0, 45.0
    min_zoom, max_zoom = 5, 12  # Detay seviyesi
    
    output_dir = "/var/www/html/maps"
    
    print("Harita tile'ları indiriliyor...")
    download_area_tiles(lat_min, lat_max, lon_min, lon_max, min_zoom, max_zoom, output_dir)
    print("İndirme tamamlandı!")
```

### **Adım 3: Tile'ları İndirme**
```bash
# Script'i çalıştır (internet bağlantısı gerektirir)
cd /home/pi
python3 download_tiles.py

# Alternatif: Önceden hazırlanmış tile'ları kopyala
# USB'den tile'ları kopyala:
sudo cp -r /path/to/tiles/* /var/www/html/maps/
```

---

## 🌐 Offline Harita Sunucusu

### **Adım 1: Nginx Kurulumu**
```bash
# Nginx kurulumu
sudo apt update
sudo apt install nginx -y

# Nginx'i başlat
sudo systemctl start nginx
sudo systemctl enable nginx
```

### **Adım 2: Nginx Konfigürasyonu**
```bash
# Nginx yapılandırması
sudo nano /etc/nginx/sites-available/tamga-maps
```

**Konfigürasyon içeriği:**
```nginx
server {
    listen 8081;
    server_name localhost;
    
    # Harita tile'ları için
    location /maps/ {
        alias /var/www/html/maps/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Tile bulunamazsa varsayılan resim
        try_files $uri $uri/ /maps/blank.png;
    }
    
    # Varsayılan resim
    location = /maps/blank.png {
        empty_gif;
    }
    
    # Gzip sıkıştırma
    gzip on;
    gzip_types image/png image/jpeg image/gif;
    
    # CORS başlıkları
    add_header 'Access-Control-Allow-Origin' '*';
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
    add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
}
```

**Site'ı aktif et:**
```bash
sudo ln -s /etc/nginx/sites-available/tamga-maps /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🗺️ Offline Harita JavaScript

### **Leaflet.js ile Offline Harita**
```javascript
// Offline harita için Leaflet.js konfigürasyonu
function initOfflineMap() {
    // Offline tile URL
    const offlineTileUrl = 'http://ORANGE_PI_IP:8081/maps/{z}/{x}/{y}.png';
    
    // Harita oluştur
    const map = L.map('gps-map').setView([39.925533, 32.866287], 10);
    
    // Tile layer ekle
    const tileLayer = L.tileLayer(offlineTileUrl, {
        attribution: '© TAMGA-ADKS Offline Maps',
        maxZoom: 15,
        minZoom: 5,
        tileSize: 256,
        errorTileUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
    }).addTo(map);
    
    // GPS konum işareti
    const gpsMarker = L.marker([0, 0], {
        icon: L.divIcon({
            className: 'custom-div-icon',
            html: "<div style='background-color: #FF0000; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);'></div>",
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        })
    }).addTo(map);
    
    // Konum güncelleme fonksiyonu
    function updateGPSPosition() {
        fetch('/api/gps_position')
            .then(response => response.json())
            .then(data => {
                if (data.valid && data.latitude && data.longitude) {
                    const lat = parseFloat(data.latitude);
                    const lng = parseFloat(data.longitude);
                    
                    // Konum işaretini güncelle
                    gpsMarker.setLatLng([lat, lng]);
                    
                    // Haritayı konuma merkezle
                    map.setView([lat, lng], 15);
                    
                    // Bilgileri güncelle
                    updateGPSInfo(data);
                }
            })
            .catch(error => console.error('GPS güncelleme hatası:', error));
    }
    
    // Her saniye güncelle
    setInterval(updateGPSPosition, 1000);
    
    // İlk güncelleme
    updateGPSPosition();
    
    return { map, gpsMarker };
}

// Sayfa yüklendiğinde haritayı başlat
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('gps-map')) {
        window.tamgaMap = initOfflineMap();
    }
});
```

---

## 📡 Captive Portal Konfigürasyonu

### **Adım 1: Hostapd Yapılandırması**
```bash
# Hostapd yapılandırması
sudo nano /etc/hostapd/hostapd.conf
```

**İçerik:**
```ini
interface=wlan0
driver=nl80211
ssid=TAMGA-ADKS-OFFLINE
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

# Captive portal için
# auth_server_addr=127.0.0.1
# auth_server_port=80
# auth_server_shared_secret=sharedsecret
```

### **Adım 2: Dnsmasq Yapılandırması**
```bash
# Dnsmasq yapılandırması
sudo nano /etc/dnsmasq.conf
```

**İçerik:**
```ini
# WiFi hotspot için
interface=wlan0
domain=local
dhcp-range=192.168.4.2,192.168.4.20,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1

# Captive portal yönlendirmesi
address=/#/192.168.4.1
address=/google.com/192.168.4.1
address=/facebook.com/192.168.4.1
address=/youtube.com/192.168.4.1
address=/instagram.com/192.168.4.1
address=/twitter.com/192.168.4.1
address=/tiktok.com/192.168.4.1
address=/whatsapp.com/192.168.4.1
address=/telegram.com/192.168.4.1

# Türk siteleri
address=/hepsiburada.com/192.168.4.1
address=/trendyol.com/192.168.4.1
address=/n11.com/192.168.4.1
address=/sahadan.com/192.168.4.1
address=/exxen.com/192.168.4.1
address=/blutv.com.tr/192.168.4.1

# Harita servisleri için
address=/tile.openstreetmap.org/192.168.4.1:8081
address=/maps.tamga.local/192.168.4.1:8081
```

---

## 🐧 Tam Sunucu Kodu

### **orange_pi_server.py (Offline Versiyon)**
```python
from flask import Flask, jsonify, render_template_string, send_from_directory
import serial
import threading
import json
import time
import os
from datetime import datetime

app = Flask(__name__)

# GPS veri okuyucu
class GPSReader:
    def __init__(self, port='/dev/ttyS0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.gps_data = {
            'latitude': None,
            'longitude': None,
            'altitude': None,
            'speed': None,
            'satellites': None,
            'timestamp': None,
            'valid': False
        }
        self.running = False
        
    def connect(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"GPS bağlantısı kuruldu: {self.port}")
            return True
        except Exception as e:
            print(f"GPS bağlantı hatası: {e}")
            return False
    
    def start_reading(self):
        if not self.connect():
            return False
            
        self.running = True
        self.thread = threading.Thread(target=self._read_loop)
        self.thread.daemon = True
        self.thread.start()
        return True
    
    def _read_loop(self):
        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    self._parse_gps_data(line)
            except Exception as e:
                print(f"GPS okuma hatası: {e}")
                time.sleep(1)
                self.connect()
    
    def _parse_gps_data(self, data):
        if data.startswith("GPS_DATA:"):
            parts = data.replace("GPS_DATA:", "").split(",")
            if len(parts) >= 6:
                self.gps_data = {
                    'latitude': float(parts[0]),
                    'longitude': float(parts[1]),
                    'altitude': float(parts[2]),
                    'speed': float(parts[3]),
                    'satellites': int(parts[4]),
                    'timestamp': parts[5],
                    'valid': True
                }
                print(f"GPS Güncellendi: {self.gps_data}")
        elif data == "GPS_BEKLENIYOR":
            self.gps_data['valid'] = False
            print("GPS sinyali bekleniyor...")
    
    def get_current_position(self):
        return self.gps_data

# GPS okuyucuyu başlat
gps_reader = GPSReader()

# Veri depolama
DATA_FILE = "/mnt/usb_storage/tamga_records.json"

def ensure_data_file():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({"records": []}, f)

def load_records():
    ensure_data_file()
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"records": []}

def save_record(record):
    data = load_records()
    record['timestamp'] = datetime.now().isoformat()
    data['records'].append(record)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    return record

# Rotalar
@app.route('/')
def index():
    return render_template_string(open('tum_sayfalar.html').read())

@app.route('/admin')
def admin():
    return render_template_string(open('tum_sayfalar.html').read())

@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "mode": "offline",
        "gps_connected": gps_reader.serial_conn is not None,
        "data_file": os.path.exists(DATA_FILE),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        record = request.get_json()
        if record:
            saved = save_record(record)
            return jsonify({"status": "success", "record": saved})
        else:
            return jsonify({"status": "error", "message": "Veri bulunamadı"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/records')
def get_records():
    data = load_records()
    return jsonify(data)

@app.route('/api/gps_position')
def get_gps_position():
    position = gps_reader.get_current_position()
    return jsonify(position)

@app.route('/maps/<path:filename>')
def serve_map_tiles(filename):
    return send_from_directory('/var/www/html/maps', filename)

@app.route('/search', methods=['POST'])
def search_records():
    try:
        search_data = request.get_json()
        kimlik_no = search_data.get('kimlik_no', '').strip()
        ad_soyad = search_data.get('ad_soyad', '').strip()
        
        data = load_records()
        records = data.get('records', [])
        
        matched_records = []
        
        if kimlik_no and ad_soyad:
            matched_records = [r for r in records if 
                             r.get('KİMLİK NO') == kimlik_no and 
                             r.get('AD SOYAD', '').lower().find(ad_soyad.lower()) != -1]
        elif kimlik_no:
            matched_records = [r for r in records if r.get('KİMLİK NO') == kimlik_no]
        elif ad_soyad:
            matched_records = [r for r in records if 
                             r.get('AD SOYAD', '').lower().find(ad_soyad.lower()) != -1]
        
        return jsonify({"records": matched_records})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # GPS okumayı başlat
    gps_reader.start_reading()
    
    # Sunucuyu başlat
    app.run(host='0.0.0.0', port=80, debug=False)
```

---

## 📱 Offline Web Arayüzü

### **HTML Güncellemeleri**
```html
<!-- tum_sayfalar.html'e ekle -->
<div class="offline-indicator" style="position: fixed; top: 10px; right: 10px; background: #28a745; color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px;">
    🌐 OFFLINE MOD
</div>

<script>
// Offline mod kontrolü
function checkOfflineMode() {
    return !navigator.onLine;
}

// Harita tile'ları için offline kontrol
function getTileUrl(x, y, z) {
    const offlineUrl = `http://192.168.4.1:8081/maps/${z}/${x}/${y}.png`;
    const onlineUrl = `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
    
    return checkOfflineMode() ? offlineUrl : onlineUrl;
}

// Servis worker için offline cache
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(console.error);
}
</script>
```

---

## 🔧 Servis Worker (Offline Cache)

### **sw.js dosyası**
```javascript
const CACHE_NAME = 'tamga-adks-v1';
const urlsToCache = [
    '/',
    '/static/logo.png',
    '/maps/blank.png'
];

self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function(cache) {
                return cache.addAll(urlsToCache);
            })
    );
});

self.addEventListener('fetch', function(event) {
    event.respondWith(
        caches.match(event.request)
            .then(function(response) {
                // Cache'de varsa oradan al
                if (response) {
                    return response;
                }
                
                // Harita tile'ları için özel kontrol
                if (event.request.url.includes('/maps/')) {
                    return fetch(event.request).catch(() => {
                        // Tile bulunamazsa boş resim döndür
                        return new Response('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');
                    });
                }
                
                return fetch(event.request);
            })
    );
});
```

---

## 🚀 Kurulum Script'i

### **Otomatik Kurulum Script'i**
```bash
#!/bin/bash
# install_offline_system.sh

echo "🚀 TAMGA-ADKS Offline Sistemi Kuruluyor..."

# 1. Sistem güncelleme
echo "📦 Sistem güncelleniyor..."
sudo apt update && sudo apt upgrade -y

# 2. Gerekli paketler
echo "📦 Gerekli paketler kuruluyor..."
sudo apt install nginx hostapd dnsmasq python3-pip python3-serial -y

# 3. Python kütüphaneleri
echo "🐍 Python kütüphaneleri kuruluyor..."
pip3 install flask requests

# 4. Dizinler oluştur
echo "📁 Dizinler oluşturuluyor..."
sudo mkdir -p /var/www/html/maps
sudo mkdir -p /mnt/usb_storage
sudo chown -R pi:pi /var/www/html/maps
sudo chown -R pi:pi /mnt/usb_storage

# 5. Nginx konfigürasyonu
echo "🌐 Nginx yapılandırılıyor..."
sudo tee /etc/nginx/sites-available/tamga-maps > /dev/null << 'EOF'
server {
    listen 8081;
    server_name localhost;
    
    location /maps/ {
        alias /var/www/html/maps/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri $uri/ /maps/blank.png;
    }
    
    location = /maps/blank.png {
        empty_gif;
    }
    
    gzip on;
    gzip_types image/png image/jpeg image/gif;
    
    add_header 'Access-Control-Allow-Origin' '*';
}
EOF

sudo ln -s /etc/nginx/sites-available/tamga-maps /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 6. Hostapd konfigürasyonu
echo "📡 WiFi hotspot yapılandırılıyor..."
sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
interface=wlan0
driver=nl80211
ssid=TAMGA-ADKS-OFFLINE
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
EOF

# 7. Dnsmasq konfigürasyonu
echo "🌐 DNS yapılandırılıyor..."
sudo tee /etc/dnsmasq.conf > /dev/null << 'EOF'
interface=wlan0
domain=local
dhcp-range=192.168.4.2,192.168.4.20,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
address=/#/192.168.4.1
address=/tile.openstreetmap.org/192.168.4.1:8081
EOF

# 8. Servisleri başlat
echo "🔄 Servisler başlatılıyor..."
sudo systemctl enable hostapd dnsmasq nginx
sudo systemctl restart hostapd dnsmasq nginx

# 9. Servis dosyası oluştur
echo "🔧 TAMGA-ADKS servisi oluşturuluyor..."
sudo tee /etc/systemd/system/tamga-adks.service > /dev/null << 'EOF'
[Unit]
Description=TAMGA-ADKS Offline Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/TAMGA-ADKS/orange_pi_server.py
WorkingDirectory=/home/pi/TAMGA-ADKS
User=pi
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tamga-adks.service

echo "✅ Kurulum tamamlandı!"
echo "🌐 WiFi: TAMGA-ADKS-OFFLINE"
echo "🔑 Şifre: 12345678"
echo "🌍 IP: http://192.168.4.1"
echo "🗺️ Harita: http://192.168.4.1:8081/maps/"
echo ""
echo "🔄 Sistemi yeniden başlatmak için: sudo reboot"
```

---

## ✅ Test ve Doğrulama

### **Test Komutları:**
```bash
# 1. Kurulum script'ini çalıştır
chmod +x install_offline_system.sh
./install_offline_system.sh

# 2. Servisleri kontrol et
sudo systemctl status hostapd dnsmasq nginx tamga-adks

# 3. WiFi ağını kontrol et
sudo iwlist wlan0 scan

# 4. GPS bağlantısını test et
python3 -c "
import serial
ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
print('GPS bağlantısı başarılı')
ser.close()
"

# 5. Web arayüzünü test et
curl http://localhost/api/health
curl http://localhost/api/gps_position
```

### **Mobil Test:**
1. **WiFi'ye bağlan:** `TAMGA-ADKS-OFFLINE`
2. **Şifre gir:** `12345678`
3. **Tarayıcı aç:** Otomatik yönlendirme
4. **GPS konumunu izle:** Kırmızı nokta hareket ediyor mu?
5. **Harita kontrol:** Offline tile'lar yükleniyor mu?

---

## 🎯 Sonuç

**Tamamen İnternetsiz TAMGA-ADKS Sistemi!** 🎉

### **Özellikler:**
- 🌐 **Offline WiFi:** İnternet gerektirmeyen hotspot
- 🗺️ **Yerel Harita:** OpenStreetMap tile'ları
- 📡 **GPS Takip:** Arduino ile gerçek zamanlı konum
- 🔍 **Arama:** Kişi ve veri arama
- 📱 **Responsive:** Tüm cihazlarda çalışır
- 🌙 **Koyu Tema:** Modern arayüz

### **Kullanım:**
1. **Sistemi başlat:** `sudo systemctl start tamga-adks`
2. **WiFi'ye bağlan:** `TAMGA-ADKS-OFFLINE`
3. **Arayüzü kullan:** `http://192.168.4.1`
4. **GPS'i izle:** Gerçek zamanlı konum takibi

**Artık sisteminiz tamamen internet bağlantısı olmadan çalışıyor!** 🚀

---
*TAMGA-ADKS Offline Systems Team*  
*© 2026 Tüm Hakları Saklıdır*
