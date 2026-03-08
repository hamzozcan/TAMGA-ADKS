# 🚀 TAMGA-ADKS Kurulum Rehberi

## 📋 Gerekli Kütüphaneler

### **requirements.txt dosyası hazır:**
```
Flask==2.3.3
folium==0.15.0
RPi.GPIO==0.7.1
mfrc522==0.0.7
Pillow==10.1.0
pyserial==3.5
requests==2.31.0
bluetooth==0.23
customtkinter==5.2.2
```

---

## 🔧 Kurulum Adımları

### **1. Sistem Güncelleme:**
```bash
sudo apt update
sudo apt upgrade -y
```

### **2. Python ve Pip:**
```bash
# Python 3 kontrol et
python3 --version

# Pip kontrol et
pip3 --version

# Eğer yoksa kur:
sudo apt install python3 python3-pip -y
```

### **3. Sistem Kütüphaneleri:**
```bash
# GPIO için
sudo apt install python3-dev -y

# I2C ve SPI için
sudo apt install i2c-tools spi-tools -y

# Bluetooth için
sudo apt install bluetooth bluez libbluetooth-dev -y

# PIL için
sudo apt install python3-pil python3-pil.imagetk -y
```

### **4. Virtual Environment (Önerilen):**
```bash
# Virtual environment oluştur
python3 -m venv tamga_env

# Aktifleştir
source tamga_env/bin/activate

# Kütüphaneleri kur
pip install -r requirements.txt
```

### **5. Direkt Kurulum (Virtual environment olmadan):**
```bash
# Tüm kütüphaneleri kur
pip3 install -r requirements.txt

# Eğer hata çıkarsa tek tek kur:
pip3 install Flask==2.3.3
pip3 install folium==0.15.0
pip3 install RPi.GPIO==0.7.1
pip3 install mfrc522==0.0.7
pip3 install Pillow==10.1.0
pip3 install pyserial==3.5
pip3 install requests==2.31.0
pip3 install bluetooth==0.23
pip3 install customtkinter==5.2.2
```

---

## 🐧 Raspberry Pi Özel Ayarları

### **1. GPIO ve SPI Aktifleştirme:**
```bash
# Raspberry Pi konfigürasyon aracı
sudo raspi-config

# Interfacing Options → SPI → Enable
# Interfacing Options → I2C → Enable
# Interfacing Options → Serial → Enable (Serial port NO, Serial console YES)
# Advanced Options → Expand Filesystem

# Yeniden başlat
sudo reboot
```

### **2. Kullanıcı Grupları:**
```bash
# GPIO, I2C, SPI gruplarına ekle
sudo usermod -a -G gpio,i2c,spi,bluetooth pi

# Yeniden başlat
sudo reboot
```

### **3. Port Kontrolü:**
```bash
# GPIO portlarını kontrol et
ls /dev/gpio*

# I2C portlarını kontrol et
ls /dev/i2c*

# SPI portlarını kontrol et
ls /dev/spi*

# Serial portları kontrol et
ls /dev/tty*
```

---

## 🐍 Python Test

### **1. Kütüphane Test:**
```python
# test_libraries.py
import sys

print("🔍 Kütüphane Testi...")
print(f"Python Version: {sys.version}")

try:
    import flask
    print("✅ Flask:", flask.__version__)
except ImportError as e:
    print("❌ Flask:", e)

try:
    import folium
    print("✅ Folium:", folium.__version__)
except ImportError as e:
    print("❌ Folium:", e)

try:
    import RPi.GPIO as GPIO
    print("✅ RPi.GPIO: Yüklendi")
except ImportError as e:
    print("❌ RPi.GPIO:", e)

try:
    import mfrc522
    print("✅ mfrc522: Yüklendi")
except ImportError as e:
    print("❌ mfrc522:", e)

try:
    import serial
    print("✅ pyserial:", serial.VERSION)
except ImportError as e:
    print("❌ pyserial:", e)

try:
    import requests
    print("✅ requests:", requests.__version__)
except ImportError as e:
    print("❌ requests:", e)

try:
    import bluetooth
    print("✅ bluetooth: Yüklendi")
except ImportError as e:
    print("❌ bluetooth:", e)

try:
    import PIL
    print("✅ PIL:", PIL.__version__)
except ImportError as e:
    print("❌ PIL:", e)

print("\n🎯 Test tamamlandı!")
```

### **2. Test'i Çalıştır:**
```bash
python3 test_libraries.py
```

---

## 🚨 Sık Karşılaşılan Sorunlar

### **1. RPi.GPIO Hatası:**
```bash
# Çözüm:
sudo apt install python3-rpi.gpio -y

# Alternatif:
pip3 install RPi.GPIO --force-reinstall
```

### **2. mfrc522 Hatası:**
```bash
# Çözüm:
pip3 install mfrc522 --force-reinstall

# Eğer hata devam ederse:
pip3 uninstall mfrc522
pip3 install git+https://github.com/mxgxw/MFRC522-python.git
```

### **3. Folium Hatası:**
```bash
# Çözüm:
pip3 install folium --upgrade

# Eğer hata devam ederse:
pip3 install folium==0.14.0
```

### **4. PIL/Pillow Hatası:**
```bash
# Çözüm:
sudo apt install python3-pil python3-pil.imagetk -y
pip3 install Pillow --upgrade
```

### **5. Bluetooth Hatası:**
```bash
# Çözüm:
sudo apt install libbluetooth-dev -y
pip3 install pybluez --force-reinstall
```

---

## 🎯 Hızlı Başlangıç

### **1. Otomatik Kurulum Script'i:**
```bash
#!/bin/bash
# install_tamga.sh

echo "🚀 TAMGA-ADKS Otomatik Kurulum..."

# Sistem güncelleme
sudo apt update && sudo apt upgrade -y

# Python kütüphaneleri
sudo apt install python3 python3-pip python3-dev -y

# Sistem kütüphaneleri
sudo apt install i2c-tools spi-tools python3-pil python3-pil.imagetk -y

# GPIO ayarları
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Kullanıcı grupları
sudo usermod -a -G gpio,i2c,spi pi

# Python kütüphaneleri
pip3 install -r requirements.txt

echo "✅ Kurulum tamamlandı!"
echo "🔄 Sistemi yeniden başlatmak için: sudo reboot"
```

### **2. Script'i Çalıştır:**
```bash
chmod +x install_tamga.sh
./install_tamga.sh
```

---

## 🚀 Sistemi Çalıştırma

### **1. Virtual Environment ile:**
```bash
# Environment'ı aktifleştir
source tamga_env/bin/activate

# Sistemi çalıştır
python3 tamga_adks_optimized.py
```

### **2. Direkt Çalıştırma:**
```bash
# Sistemi çalıştır
python3 tamga_adks_optimized.py

# Veya
python3 tamga_adks_complete_system.py
```

### **3. Servis Olarak Çalıştırma:**
```bash
# Servis dosyası oluştur
sudo tee /etc/systemd/system/tamga-adks.service > /dev/null << 'EOF'
[Unit]
Description=TAMGA-ADKS System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/TAMGA-ADKS/tamga_adks_optimized.py
WorkingDirectory=/home/pi/TAMGA-ADKS
User=pi
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Servisi başlat
sudo systemctl daemon-reload
sudo systemctl enable tamga-adks.service
sudo systemctl start tamga-adks.service

# Durumu kontrol et
sudo systemctl status tamga-adks.service
```

---

## 🌐 Web Arayüzü

### **1. Sistem Başladıktan Sonra:**
- **Adres:** `http://192.168.4.1`
- **Port:** 80
- **Durum:** Tüm bileşenlerin durumu

### **2. Test Et:**
```bash
# API testi
curl http://localhost/api/health

# GPS testi
curl http://localhost/api/gps_position

# Kayıtlar testi
curl http://localhost/api/records
```

---

## ✅ Başarılı Kurulum Kontrolü

### **1. Tüm Bileşenler Çalışıyor Mu?**
- ✅ **Web Arayüzü:** `http://192.168.4.1`
- ✅ **LED Göstergeleri:** Console'da görünüyor
- ✅ **RFID Okuyucu:** Kart okuyunca bildirim
- ✅ **GPS:** Arduino'dan veri geliyorsa
- ✅ **Veri Kaydı:** JSON dosyasına yazıyor

### **2. Log Kontrolü:**
```bash
# Sistem logları
sudo journalctl -u tamga-adks -f

# USB depolama kontrolü
ls -la /mnt/usb_storage/

# Kart okuma logları
tail -f /mnt/usb_storage/card_reads.log
```

---

## 🎯 Sonuç

**Artık TAMGA-ADKS sistemi hazır!** 🚀

### **📋 Özet:**
1. ✅ **requirements.txt** hazır
2. ✅ **Kurulum script'i** hazır
3. ✅ **Test script'i** hazır
4. ✅ **Sorun çözümleri** hazır

### **🚀 Başlatmak için:**
```bash
# 1. Kütüphaneleri kur
pip3 install -r requirements.txt

# 2. Sistemi çalıştır
python3 tamga_adks_optimized.py

# 3. Web arayüzüne git
http://192.168.4.1
```

**Sistem çalışmaya hazır!** 🎯
