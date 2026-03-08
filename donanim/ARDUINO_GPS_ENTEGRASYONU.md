# Arduino GPS Entegrasyonu - Raspberry Pi Bağlantısı

## 🎯 Sistem Tanıtımı

Arduino GPS modülünden gelen koordinat verilerine göre Raspberry Pi üzerindeki haritadaki kırmızı noktanın yerini dinamik olarak güncelleyen sistem.

### **Özellikler:**
- 📡 **GPS Modülü:** Arduino ile GPS verisi okuma
- 🔌 **Seri İletişim:** Raspberry Pi - Arduino bağlantısı
- 🗺️ **Harita Güncelleme:** Gerçek zamanlı konum takibi
- 📍 **Kırmızı Nokta:** Dinamik konum işareti
- 🌐 **Web Arayüzü:** Captive portal üzerinden izleme

---

## 🔌 Donanım Bağlantıları

### **Gereken Malzemeler:**
- Raspberry Pi 4B veya Orange Pi
- Arduino Uno/Nano/Mega
- GPS Modülü (NEO-6M, VK2828U7G5LF, vb.)
- Jumper kablolar
- Breadboard (opsiyonel)

### **Arduino - GPS Modülü Bağlantısı:**

#### **NEO-6M GPS Modülü için:**
```
GPS Modülü    →    Arduino
VCC           →    5V
GND           →    GND
TX            →    D2 (Software RX)
RX            →    D3 (Software TX)
```

#### **Arduino - Raspberry Pi Bağlantısı:**
```
Arduino       →    Raspberry Pi
GND           →    GND (Pin 6)
TX (D1)       →    GPIO 15 (Pin 10)
RX (D0)       →    GPIO 14 (Pin 8)
5V            →    5V (Pin 2 veya 4)
```

### **Tam Bağlantı Şeması:**
```
GPS Modülü:
┌─────────────┐
│ VCC  GND    │
│ TX   RX     │
└─────┬───────┘
      │
      ├─ Arduino D2 (RX)
      └─ Arduino D3 (TX)

Arduino:
┌─────────────────┐
│ D0   D1   D2 D3 │
│ RX   TX   RX TX │
└─────┬─────┬─────┘
      │     │
      │     └─ GPS TX
      └─ GPS RX

Arduino → Raspberry Pi:
┌─────────────┐    ┌─────────────┐
│ Arduino     │    │ Raspberry Pi│
│ GND         │───▶│ GND (Pin 6) │
│ TX (D1)     │───▶│ GPIO 15     │
│ RX (D0)     │───▶│ GPIO 14     │
│ 5V          │───▶│ 5V (Pin 2)  │
└─────────────┘    └─────────────┘
```

---

## 📝 Arduino Kodu

### **GPS Veri Okuma ve Gönderme:**
```cpp
#include <SoftwareSerial.h>
#include <TinyGPS++.h>

// GPS modülü için seri port
SoftwareSerial gpsSerial(2, 3); // RX, TX
TinyGPSPlus gps;

// Raspberry Pi ile iletişim için
#define BAUD_RATE 9600

void setup() {
  Serial.begin(BAUD_RATE);  // Raspberry Pi iletişim
  gpsSerial.begin(9600);   // GPS modülü iletişim
  
  Serial.println("GPS Sistemi Başlatılıyor...");
  delay(1000);
}

void loop() {
  // GPS verilerini oku
  while (gpsSerial.available() > 0) {
    if (gps.encode(gpsSerial.read())) {
      if (gps.location.isValid()) {
        // Koordinatları Raspberry Pi'ye gönder
        String gpsData = String(gps.location.lat(), 6) + "," + 
                        String(gps.location.lng(), 6) + "," +
                        String(gps.altitude.meters(), 2) + "," +
                        String(gps.speed.kmph(), 2) + "," +
                        String(gps.date.year()) + "-" +
                        String(gps.date.month()) + "-" +
                        String(gps.date.day()) + " " +
                        String(gps.time.hour()) + ":" +
                        String(gps.time.minute()) + ":" +
                        String(gps.time.second());
        
        Serial.println(gpsData);
        delay(1000); // Her saniye gönder
      }
    }
  }
  
  // GPS sinyali yoksa uyarı gönder
  if (millis() > 5000 && gps.charsProcessed() < 10) {
    Serial.println("GPS Sinyali Bulunamadı!");
    delay(2000);
  }
}
```

### **Gelişmiş Arduino Kodu:**
```cpp
#include <SoftwareSerial.h>
#include <TinyGPS++.h>

SoftwareSerial gpsSerial(2, 3);
TinyGPSPlus gps;

struct GPSData {
  double latitude;
  double longitude;
  double altitude;
  double speed;
  int satellites;
  String timestamp;
  bool valid;
};

GPSData currentGPS;

void setup() {
  Serial.begin(9600);
  gpsSerial.begin(9600);
  
  pinMode(LED_BUILTIN, OUTPUT);
  
  Serial.println("TAMGA-ADKS GPS Sistemi");
  Serial.println("Sürüm: 1.0.0");
  delay(1000);
}

void loop() {
  updateGPS();
  
  if (currentGPS.valid) {
    sendGPSData();
    blinkLED(100); // GPS sinyali varsa hızlı blink
  } else {
    Serial.println("GPS_BEKLENIYOR");
    blinkLED(500); // GPS sinyali yoksa yavaş blink
  }
  
  delay(1000);
}

void updateGPS() {
  while (gpsSerial.available() > 0) {
    if (gps.encode(gpsSerial.read())) {
      if (gps.location.isValid()) {
        currentGPS.latitude = gps.location.lat();
        currentGPS.longitude = gps.location.lng();
        currentGPS.altitude = gps.altitude.meters();
        currentGPS.speed = gps.speed.kmph();
        currentGPS.satellites = gps.satellites.value();
        currentGPS.timestamp = getTimestamp();
        currentGPS.valid = true;
      } else {
        currentGPS.valid = false;
      }
    }
  }
}

void sendGPSData() {
  String data = "GPS_DATA:" +
                String(currentGPS.latitude, 6) + "," +
                String(currentGPS.longitude, 6) + "," +
                String(currentGPS.altitude, 2) + "," +
                String(currentGPS.speed, 2) + "," +
                String(currentGPS.satellites) + "," +
                currentGPS.timestamp;
  
  Serial.println(data);
}

String getTimestamp() {
  return String(gps.date.year()) + "-" +
         String(gps.date.month()) + "-" +
         String(gps.date.day()) + " " +
         String(gps.time.hour()) + ":" +
         String(gps.time.minute()) + ":" +
         String(gps.time.second());
}

void blinkLED(int delayTime) {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(delayTime);
  digitalWrite(LED_BUILTIN, LOW);
  delay(delayTime);
}
```

---

## 🐧 Raspberry Pi Python Kodu

### **Seri Port Okuma:**
```python
import serial
import threading
import json
from datetime import datetime

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
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )
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
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    self._parse_gps_data(line)
            except Exception as e:
                print(f"GPS okuma hatası: {e}")
                self.connect()  # Yeniden bağlanmayı dene
    
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
    
    def stop(self):
        self.running = False
        if self.serial_conn:
            self.serial_conn.close()
```

### **Flask Entegrasyonu:**
```python
from flask import Flask, jsonify, render_template_string
import threading
import time

app = Flask(__name__)
gps_reader = GPSReader()

@app.route('/')
def index():
    return render_template_string(open('tum_sayfalar.html').read())

@app.route('/api/gps_position')
def get_gps_position():
    position = gps_reader.get_current_position()
    return jsonify(position)

@app.route('/api/gps_stream')
def gps_stream():
    def generate():
        while True:
            position = gps_reader.get_current_position()
            yield f"data: {json.dumps(position)}\n\n"
            time.sleep(1)
    
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    # GPS okumayı başlat
    gps_reader.start_reading()
    
    # Flask sunucusunu başlat
    app.run(host='0.0.0.0', port=80, debug=False)
```

---

## 🗺️ Harita Güncelleme JavaScript

### **Gerçek Zamanlı Konum Takibi:**
```javascript
// GPS konumunu güncelleme
let gpsMarker = null;
let gpsPosition = {lat: 0, lng: 0};

function initMap() {
    // Haritayı başlat
    const map = new google.maps.Map(document.getElementById('map'), {
        center: {lat: 39.925533, lng: 32.866287}, // Ankara merkez
        zoom: 13
    });
    
    // Kırmızı konum işareti oluştur
    gpsMarker = new google.maps.Marker({
        position: {lat: 0, lng: 0},
        map: map,
        title: 'GPS Konumu',
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: '#FF0000',
            fillOpacity: 0.8,
            strokeColor: '#FFFFFF',
            strokeWeight: 2
        }
    });
    
    // GPS verilerini periyodik olarak güncelle
    setInterval(updateGPSPosition, 1000);
}

function updateGPSPosition() {
    fetch('/api/gps_position')
        .then(response => response.json())
        .then(data => {
            if (data.valid && data.latitude && data.longitude) {
                gpsPosition = {
                    lat: parseFloat(data.latitude),
                    lng: parseFloat(data.longitude)
                };
                
                // Konum işaretini güncelle
                gpsMarker.setPosition(gpsPosition);
                
                // Haritayı konuma merkezle
                map.setCenter(gpsPosition);
                
                // Bilgi panelini güncelle
                updateGPSInfo(data);
            }
        })
        .catch(error => console.error('GPS güncelleme hatası:', error));
}

function updateGPSInfo(data) {
    const infoDiv = document.getElementById('gps-info');
    if (infoDiv) {
        infoDiv.innerHTML = `
            <div style="background: rgba(22, 33, 62, 0.9); padding: 15px; border-radius: 10px; color: white;">
                <h4>📍 GPS Konumu</h4>
                <p><strong>Enlem:</strong> ${data.latitude}</p>
                <p><strong>Boylam:</strong> ${data.longitude}</p>
                <p><strong>Yükseklik:</strong> ${data.altitude} m</p>
                <p><strong>Hız:</strong> ${data.speed} km/s</p>
                <p><strong>Uydu:</strong> ${data.satellites}</p>
                <p><strong>Zaman:</strong> ${data.timestamp}</p>
            </div>
        `;
    }
}
```

### **OpenStreetMap Versiyonu:**
```javascript
let osmMap = null;
let gpsMarker = null;

function initOSMMap() {
    // OpenStreetMap haritası oluştur
    osmMap = L.map('map').setView([39.925533, 32.866287], 13);
    
    // Tile layer ekle
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(osmMap);
    
    // Kırmızı konum işareti oluştur
    gpsMarker = L.marker([0, 0], {
        icon: L.divIcon({
            className: 'custom-div-icon',
            html: "<div style='background-color: red; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white;'></div>",
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        })
    }).addTo(osmMap);
    
    // GPS güncellemelerini başlat
    setInterval(updateOSMGPSPosition, 1000);
}

function updateOSMGPSPosition() {
    fetch('/api/gps_position')
        .then(response => response.json())
        .then(data => {
            if (data.valid && data.latitude && data.longitude) {
                const lat = parseFloat(data.latitude);
                const lng = parseFloat(data.longitude);
                
                // Konum işaretini güncelle
                gpsMarker.setLatLng([lat, lng]);
                
                // Haritayı konuma merkezle
                osmMap.setView([lat, lng], 15);
                
                // Bilgileri güncelle
                updateGPSInfo(data);
            }
        })
        .catch(error => console.error('GPS güncelleme hatası:', error));
}

// HTML'e eklenecek OpenStreetMap CSS/JS
// <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
// <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
```

---

## 🔧 Raspberry Pi Konfigürasyonu

### **Seri Port Aktifleştirme:**
```bash
# 1. Raspberry Pi Konfigürasyon aracını aç
sudo raspi-config

# 2. Interface Options → Serial Port
# 3. "Would you like a login shell to be accessible over serial?" → NO
# 4. "Would you like the serial port hardware to be enabled?" → YES

# 5. Yeniden başlat
sudo reboot
```

### **Seri Port İzinleri:**
```bash
# Kullanıcıyı dialout grubuna ekle
sudo usermod -a -G dialout pi

# İzinleri kontrol et
groups pi

# Servisi yeniden başlat
sudo systemctl reboot
```

### **Seri Port Testi:**
```bash
# Seri portları listele
ls /dev/tty*

# Arduino bağlantısını test et
sudo apt install minicom
minicom -b 9600 -o -D /dev/ttyS0

# Python ile test
python3 -c "
import serial
ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
print('Seri port bağlantısı başarılı!')
ser.close()
"
```

---

## 📱 Web Arayüzü Entegrasyonu

### **Harita Container'ı Ekleme:**
```html
<!-- tum_sayfalar.html'e ekle -->
<div class="map-container">
    <div class="map-title">📍 Gerçek Zamanlı GPS Konumu</div>
    <div id="gps-map" style="height: 400px; border-radius: 10px;"></div>
    <div id="gps-info" style="margin-top: 10px;"></div>
</div>

<style>
#gps-map {
    background: #1a1a2e;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.custom-div-icon {
    background-color: red !important;
    border: 2px solid white !important;
    border-radius: 50% !important;
}
</style>

<script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
```

### **JavaScript Entegrasyonu:**
```javascript
// Sayfa yüklendiğinde haritayı başlat
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('gps-map')) {
        initOSMMap();
    }
});

// GPS verilerini WebSocket ile gerçek zamanlı al
function startGPSWebSocket() {
    const ws = new WebSocket('ws://' + window.location.host + '/ws/gps');
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.valid) {
            updateOSMGPSPosition(data);
        }
    };
    
    ws.onopen = function() {
        console.log('GPS WebSocket bağlantısı kuruldu');
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket hatası:', error);
        setTimeout(startGPSWebSocket, 5000); // 5 saniye sonra tekrar dene
    };
}

// WebSocket'i başlat
startGPSWebSocket();
```

---

## 🛠️ Sorun Giderme

### **Yaygın Hatalar:**

#### **1. Seri Port Bağlantı Hatası:**
```bash
# Port izinlerini kontrol et
ls -l /dev/ttyS0
sudo chmod 666 /dev/ttyS0

# Kullanıcı gruplarını kontrol et
groups pi
sudo usermod -a -G dialout pi
```

#### **2. GPS Sinyali Alınamıyor:**
```cpp
// Arduino kodunda hata ayıklama
void setup() {
  Serial.begin(9600);
  gpsSerial.begin(9600);
  Serial.println("GPS Test Başlatılıyor...");
}

void loop() {
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    Serial.print(c); // Ham GPS verisini göster
    
    if (gps.encode(c)) {
      Serial.println("\nGPS Verisi İşlendi");
    }
  }
}
```

#### **3. Harita Güncellenmiyor:**
```javascript
// Browser konsolunda hata kontrolü
console.log('Harita başlatılıyor...');
console.log('GPS verisi:', data);

// Hata ayıklama için
function debugGPSUpdate() {
    fetch('/api/gps_position')
        .then(response => response.json())
        .then(data => console.log('GPS Response:', data))
        .catch(error => console.error('GPS Error:', error));
}

setInterval(debugGPSUpdate, 2000);
```

#### **4. Arduino Bağlantısı Kopuyor:**
```python
# Python'da yeniden bağlanma mantığı
def connect_with_retry(self, max_retries=5):
    for attempt in range(max_retries):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Bağlantı başarılı (deneme {attempt + 1})")
            return True
        except Exception as e:
            print(f"Bağlantı hatası (deneme {attempt + 1}): {e}")
            time.sleep(2)
    return False
```

---

## 📊 Test ve Doğrulama

### **Test Komutları:**
```bash
# 1. Arduino bağlantısını test et
python3 -c "
import serial
ser = serial.Serial('/dev/ttyS0', 9600)
print('Arduino bağlantısı başarılı')
ser.close()
"

# 2. GPS verisi alma testi
python3 gps_test.py

# 3. Web arayüzü testi
curl http://localhost/api/gps_position

# 4. Harita güncelleme testi
# Browser'da F12 → Console sekmesinde:
# updateGPSPosition()
```

### **Test Senaryoları:**
1. **GPS Sinyali Testi:** Arduino'dan GPS verisi geliyor mu?
2. **Seri İletişim:** Raspberry Pi verileri alıyor mu?
3. **Web Arayüzü:** Konum haritada güncelleniyor mu?
4. **Gerçek Zamanlı:** Kırmızı nokta hareket ediyor mu?

---

## ✅ Kurulum Kontrol Listesi

### **Donanım:**
- [ ] GPS modülü Arduino'ya bağlandı
- [ ] Arduino Raspberry Pi'ye bağlandı
- [ ] Güç bağlantıları kontrol edildi
- [ ] Jumper kablolar sağlam

### **Yazılım:**
- [ ] Arduino kodu yüklendi
- [ ] Raspberry Pi seri port aktif
- [ ] Python kütüphaneleri kuruldu
- [ ] Web arayüzü entegre edildi

### **Test:**
- [ ] GPS verisi okunuyor
- [ ] Seri iletişim çalışıyor
- [ ] Web arayüzü güncelleniyor
- [ ] Harita konumu takip ediyor

---

## 🎯 Sonuç

**Başarılı Kurulum!** 🎉

Artık sisteminiz:
- 📡 **GPS verisi** Arduino üzerinden okunuyor
- 🔄 **Gerçek zamanlı** konum takibi yapılıyor
- 🗺️ **Haritada** kırmızı nokta hareket ediyor
- 📱 **Web arayüzünde** konum izlenebiliyor

**Kullanım:**
1. GPS modülünü açık alana yerleştirin
2. Sistemi başlatın
3. Web arayüzünden konumu izleyin
4. Haritadaki kırmızı nokta gerçek zamanlı güncellensin!

**GPS Konum Takip Sisteminiz hazır!** 🚀

---
*TAMGA-ADKS GPS Entegrasyon Team*  
*© 2026 Tüm Hakları Saklıdır*