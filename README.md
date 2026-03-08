# TAMGA-ADKS

**Akıllı Devamsızlık Kontrol Sistemi** — RFID tabanlı, FastAPI backend'li, web arayüzlü personel/öğrenci takip sistemi.
Raspberry Pi üzerinde gerçek donanımla çalışır; normal bilgisayarda simülasyon moduyla test edilebilir.

---

## Özellikler

- **RFID kart okuma** — RC522 modülü (Raspberry Pi)
- **Parmak izi** — Deneyap DY50 sensörü (opsiyonel)
- **GPS takibi** — SIM808 modülü ile konum kaydı (opsiyonel)
- **Web arayüzü** — Canlı devamsızlık takibi, harita görünümü, QR kod
- **Simülasyon modu** — RPi olmadan PC'de test
- **Ses geri bildirimi** — başarı/hata sesleri, TTS (isteğe bağlı)
- **Çevrimdışı çalışma** — internet gerekmez, yerel SQLite/JSON
- **WebSocket** — gerçek zamanlı kart okuma olayları
- **Barkod/QR** — JsBarcode entegrasyonu

---

## Donanım Gereksinimleri

| Bileşen | Model | Zorunlu mu? |
|---|---|---|
| Ana kart | Raspberry Pi 3/4/5 veya Orange Pi | Evet (production) |
| RFID okuyucu | RC522 (SPI) | Evet |
| Parmak izi | Deneyap DY50 | Hayır |
| GPS modülü | SIM808 | Hayır |
| Ekran | Herhangi HDMI ekran veya SSH | Hayır |

> Normal PC'de `--simulate` bayrağıyla donanım olmadan çalışır.

---

## Kurulum

### Normal PC (Simülasyon Modu)

```bash
# 1. Repoyu klonla
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS

# 2. Sanal ortam oluştur
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Bağımlılıkları kur
pip install -r requirements.txt

# 4. Simülasyon modunda başlat
python tamga_backend.py --simulate

# 5. Tarayıcıda aç
# → http://localhost:8000
```

### Raspberry Pi (Gerçek Donanım)

```bash
# 1. Repoyu klonla
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS

# 2. Kurulum betiğini çalıştır
chmod +x start_all.sh
./start_all.sh

# veya doğrudan:
python tamga_backend.py
```

### Servis olarak çalıştırma (systemd)
```bash
sudo cp donanim/tamga_adks_server.service /etc/systemd/system/
sudo systemctl enable tamga_adks_server
sudo systemctl start tamga_adks_server
```

---

## Kullanım

| Adres | Açıklama |
|---|---|
| `http://[RPi-IP]:8000` | Ana web arayüzü |
| `http://[RPi-IP]:8000/docs` | API dökümantasyonu |
| `WS://[RPi-IP]:8000/ws` | Gerçek zamanlı kart olayları |

### Komut Satırı Seçenekleri
```bash
python tamga_backend.py --help

  --simulate    Donanım olmadan simülasyon modu (PC'de test)
  --port 8080   Farklı port (varsayılan: 8000)
```

---

## Dosya Yapısı

```
TAMGA-ADKS/
├── tamga_backend.py       ← Ana FastAPI sunucusu
├── tamga_launcher.py      ← Masaüstü başlatıcı (pywebview)
├── tamga_voice_trainer.py ← Ses eğitim aracı
├── tamga_config.json      ← Sistem konfigürasyonu
├── requirements.txt       ← Python bağımlılıkları
├── start_all.sh           ← Tek komutla başlatma
├── templates/
│   └── tamga.html         ← Web arayüzü
├── static/                ← CSS, JS, görseller
├── donanim/               ← Arduino/RPi kurulum dosyaları
│   ├── arduino_sim808_gps/    ← GPS Arduino kodu
│   ├── deneyap_dy50_fingerprint/ ← Parmak izi kodu
│   └── esp32/                 ← ESP32 entegrasyon
├── belgeler/              ← Kurulum ve sistem belgeleri
│   ├── kurulum_rehberi.md
│   ├── SISTEM_SEMASI.md
│   └── INTERNETSIZ_SISTEM.md
└── data/                  ← Yerel kayıt veritabanı
```

---

## Teknolojiler

- **FastAPI** + **Uvicorn** — web sunucusu
- **WebSocket** — gerçek zamanlı iletişim
- **RPi.GPIO** + **mfrc522** — RFID okuma (RPi)
- **Folium** — harita üretimi
- **pywebview** — native masaüstü pencere
- **JsBarcode** — barkod/QR üretimi
- **Arduino/ESP32** — harici sensör entegrasyonu
