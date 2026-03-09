# TAMGA-ADKS

> **Afet Sonrası Kimliklendirme ve Kayıt Sistemi**

TAMGA-ADKS; afet, toplu olay ve saha operasyonlarında kişilerin hızlı kayıt/kimliklendirme süreçlerini yönetmek için geliştirilmiş bir sistemdir.

Sistem internet olmadan çalışır, yerel kayıt tutar ve sahada hızlı kullanım için tasarlanmıştır.

---

## Ne İşe Yarar?

- Afet sahasında kişi kaydı oluşturma
- Kimlik no/QR/RFID üzerinden hızlı sorgu
- Triyaj ve transfer durum takibi
- GPS konum kaydı ve harita görüntüleme
- Opsiyonel parmak izi ve RFID donanım entegrasyonu
- Şifreli dışa aktarma (JSON/CSV/ZIP)

---

## Temel Özellikler

- **Offline-first çalışma**: İnternet gerektirmez
- **AES-256-GCM veri şifreleme**: `records.json` şifreli saklanır
- **Web arayüzü**: Sahada hızlı veri girişi ve arama
- **Gerçek zamanlı olaylar**: WebSocket desteği
- **QR üretimi**: Kişi kartı/etiket için
- **Harita önbelleği**: Çevrimdışı harita kutucukları
- **Simülasyon modu**: Donanım olmadan PC üzerinde test

---

## API (Öne Çıkan Uç Noktalar)

- `GET /api/health`
- `GET /api/records`
- `POST /api/records`
- `GET /api/records/search`
- `PATCH /api/records/{kimlik_no}/transfer`
- `DELETE /api/records/{kimlik_no}`
- `GET /api/stats`
- `GET /api/gps`
- `GET /api/map`
- `GET /api/qr/{kimlik_no}`
- `GET /api/export`
- `GET /api/export/package`
- `POST /api/sync`

Opsiyonel donanım uç noktaları:
- `POST /api/rfid/read`
- `POST /api/rfid/write`
- `POST /api/fingerprint/scan`

---

## Veri Alanları (Örnek)

Sistem kayıtlarında aşağıdaki alanlar bulunur:

- `KİMLİK NO`
- `AD SOYAD`
- `TRİYAJ`
- `CİNSİYET`
- `EKİP`
- `OLAY KODU`
- `GPS`
- `PARMAK İZİ ID`
- `RFID UID`
- `DNA`
- `VÜCUT BULGULARI`
- `EKSİK DİŞLER`
- `BOY`, `KİLO`, `SAÇ`, `GÖZ`
- `NOTLAR`

---

## Kurulum

### 1) PC (Simülasyon)

```bash
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python tamga_backend.py --simulate
```

Ardından:
- `http://localhost:8000`
- `http://localhost:8000/docs`

### 2) Raspberry Pi / Orange Pi (Gerçek Donanım)

```bash
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS
chmod +x start_all.sh
./start_all.sh
# veya
python tamga_backend.py
```

### 3) Servis Olarak Çalıştırma (systemd)

```bash
sudo cp donanim/tamga_adks_server.service /etc/systemd/system/
sudo systemctl enable tamga_adks_server
sudo systemctl start tamga_adks_server
```

---

## Donanım (Opsiyonel)

| Bileşen | Model | Zorunlu mu? |
|---|---|---|
| Ana kart | Raspberry Pi / Orange Pi | Üretimde önerilir |
| RFID | RC522 (SPI) | Opsiyonel |
| Parmak izi | Deneyap DY50 | Opsiyonel |
| GPS | SIM808 | Opsiyonel |

---

## Proje Yapısı

```text
TAMGA-ADKS/
├── tamga_backend.py
├── tamga_launcher.py
├── tamga_voice_trainer.py
├── tamga_config.json
├── requirements.txt
├── start_all.sh
├── templates/
├── static/
├── data/
├── donanim/
└── belgeler/
```

---

## Güvenlik Notu

- Şifreleme anahtarı `tamga.key` dosyasında tutulur.
- Üretim ortamında bu dosya güvenli şekilde saklanmalı ve yedeklenmelidir.
- Dışa aktarılan veriler kişisel veri içerir; KVKK/GDPR süreçlerine uygun yönetilmelidir.

---

## Yarışma Bilgisi

Bu proje, TÜBİTAK 2204-A sürecinde ödül almış ve finale yükselmiştir.

---

## Lisans

Bu depo `Apache-2.0` lisansı ile paylaşılmaktadır.
