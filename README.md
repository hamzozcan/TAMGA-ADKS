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
- **Offline AI analiz fallback**: Gemini yoksa yerel tahmin motoru devreye girer
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
- `GET /api/afad/local-snapshot`
- `POST /api/afad/ingest`
- `GET /api/afad/dashboard`
- `GET /api/family/search`
- `POST /api/family/contact`

Opsiyonel donanım uç noktaları:
- `POST /api/rfid/read`
- `POST /api/rfid/write`
- `POST /api/fingerprint/scan`

AI analiz notu:
- `POST /api/ai_query` artık internet olmadan da çalışır.
- `GEMINI_API_KEY` tanımlıysa Gemini yorumu eklenir.
- Anahtar yoksa sistem yerel tahmin modeli ile rapor üretir.

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
├── tamga_afad_bridge.py
├── tamga_launcher.py
├── tamga_voice_trainer.py
├── tamga_config.json
├── requirements.txt
├── start_all.sh
├── start_afad_bridge.sh
├── templates/
├── static/
├── data/
├── donanim/
└── belgeler/
```

---

## AFAD ve Yakın Portalı

Sistem artık üç ayrı yüz sunar:

- Ana saha ekranı: `/`
- AFAD merkez paneli: `/afad`
- Aile / yakın bilgi portalı: `/yakin` veya `/aile`

### Erişim Güvenliği

- AFAD panel API uç noktaları oturum gerektirir.
- Giriş için mevcut kullanıcı hesapları kullanılır; `afad_dashboard` izni olan roller erişebilir.
- Düğüm -> merkez veri aktarımı ayrıca `TAMGA_AFAD_SHARED_KEY` ile korunur.

### Haberleşme Modeli

- Saha cihazı yerelde çalışır ve kayıtları üretir.
- Yakın portalı aynı cihazın Wi‑Fi ağı üzerinden yerel olarak erişilebilir.
- Merkezi AFAD paneli internete açık ayrı bir sunucuda çalışır.
- Saha cihazındaki bridge script belirli aralıklarla merkezi panele JSON snapshot yollar.

### Bridge Kurulumu

Merkezi sunucuda:

```bash
export TAMGA_AFAD_SHARED_KEY='guclu-bir-anahtar'
python tamga_backend.py --host 0.0.0.0 --port 8000
```

Saha cihazında:

```bash
./start_afad_bridge.sh \
  --remote-url https://afad-panel.example.com \
  --shared-key 'guclu-bir-anahtar' \
  --node-id BATMAN-01 \
  --node-label 'Batman Saha 01'
```

Bridge şu akışı kullanır:

1. Yerelden `GET /api/afad/local-snapshot`
2. Merkeze `POST /api/afad/ingest`
3. AFAD paneli `GET /api/afad/dashboard` ile tüm düğümleri toplar

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
