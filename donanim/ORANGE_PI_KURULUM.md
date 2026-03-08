# TAMGA-ADKS Orange Pi Sunucu Kurulum Rehberi

Bu rehber, **Orange Pi Zero v1.4** üzerinde TAMGA-ADKS arama sunucusunu (`orange_pi_search_server.py`) nasıl kuracağınızı anlatır.

## 📋 Gereksinimler
- Orange Pi Zero v1.4 (Armbian veya Ubuntu yüklü)
- İnternet bağlantısı (Paket yüklemek için)
- Bir bilgisayar (Dosya aktarımı için)

---

## 🚀 Adım 1: Bağlantı ve Hazırlık

1. **SSH ile Bağlanın:**
   Bilgisayarınızdan Putty veya Terminal ile Orange Pi'ye bağlanın:
   ```bash
   ssh root@ORANGE_PI_IP
   # Şifre varsayılan: 1234 (veya sizin belirlediğiniz)
   ```

2. **Sistemi Güncelleyin:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Gerekli Araçları Yükleyin:**
   Python3 ve pip3 kurulu olmalıdır:
   ```bash
   sudo apt install python3 python3-pip -y
   ```

4. **Flask Kütüphanesini Kurun:**
   Web sunucusu için Flask gereklidir:
   ```bash
   pip3 install flask
   ```

---

## 📂 Adım 2: Dosyaları Yükleme

Bilgisayarınızdaki proje dosyalarını Orange Pi'ye aktarmanız gerekiyor.

### Aktarılacak Dosyalar:
1. `orange_pi_search_server.py`
2. `templates` klasörü (ve içindeki `search.html`)

### Yöntem A: WinSCP / FileZilla ile (Kolay)
1. WinSCP veya FileZilla ile Orange Pi'ye bağlanın (Port: 22).
2. `/root/` veya `/home/pi/` dizinine gidin.
3. `TAMGA-SERVER` adında bir klasör oluşturun.
4. Dosyaları bu klasörün içine sürükleyip bırakın.

### Yöntem B: Terminalden (Linux/Mac)
```bash
# Proje klasöründeyken:
scp orange_pi_search_server.py root@ORANGE_PI_IP:/root/TAMGA-SERVER/
scp -r templates root@ORANGE_PI_IP:/root/TAMGA-SERVER/
```

---

## ▶️ Adım 3: Sunucuyu Başlatma

1. **Sunucu Klasörüne Gidin:**
   ```bash
   cd /root/TAMGA-SERVER
   # veya dosyaları nereye attıysanız
   ```

2. **Sunucuyu Çalıştırın:**
   ```bash
   python3 orange_pi_search_server.py
   ```
   
   Ekranda şuna benzer bir çıktı görmelisiniz:
   ```
   ==================================================
   TAMGA-ADKS Orange Pi Arama Sunucusu
   ==================================================
   Sunucu baslatiliyor: http://0.0.0.0:8080
   ...
   ```

3. **Test Edin:**
   Bilgisayarınızın tarayıcısını açın ve şunu yazın:
   `http://ORANGE_PI_IP:8080`
   
   Mavi/Siyah temalı arama ekranını görüyorsanız kurulum başarılıdır! ✅

---

## 🔄 Adım 4: Otomatik Başlatma (Servis Kurulumu)
Orange Pi yeniden başladığında sunucunun otomatik açılması için:

1. **Servis Dosyası Oluşturun:**
   ```bash
   sudo nano /etc/systemd/system/tamga-server.service
   ```

2. **Aşağıdaki Kodları Yapıştırın:**
   *(Dosya yollarını kendi kurulumunuza göre düzenleyin)*
   ```ini
   [Unit]
   Description=TAMGA-ADKS Arama Sunucusu
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/root/TAMGA-SERVER
   ExecStart=/usr/bin/python3 /root/TAMGA-SERVER/orange_pi_search_server.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   *(Kaydetmek için: CTRL+X, sonra Y, sonra Enter)*

3. **Servisi Aktif Edin:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable tamga-server
   sudo systemctl start tamga-server
   ```

Artık Orange Pi fişten çekilip takılsa bile sunucu otomatik çalışacaktır.

---

## 💾 HDD / USB Bellek Ayarı (Opsiyonel)
Verilerin SD karta değil, harici bir diske kaydedilmesini istiyorsanız:

1. **USB Belleği Takın ve Bağlayın:**
   ```bash
   mkdir -p /mnt/usb_storage
   mount /dev/sda1 /mnt/usb_storage
   ```

2. **Kodu Düzenleyin:**
   `orange_pi_search_server.py` dosyasını açın:
   ```python
   CONFIG = {
       "data_dir": "/mnt/usb_storage/tamga_data", 
       ...
   }
   ```
   Kısmının doğru olduğundan emin olun. Kod varsayılan olarak `/mnt/usb_storage/tamga_data` yolunu kullanır. Eğer USB takılı değilse otomatik olarak kendi klasöründeki `data` klasörüne yazar.
