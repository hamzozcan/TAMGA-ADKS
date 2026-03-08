# TAMGA-ADKS Sistem Şemaları ve Çalışma Mantığı

Bu döküman, sistemin donanım bağlantılarını ve veri akışını görsel olarak açıklar.

## 1. Genel Sistem Mimarisi

Sistem 4 ana bileşenden oluşur:
1. **Veri Toplayıcılar:** Arduino (GPS) ve Deneyap (Parmak İzi)
2. **Ana Kontrolcü:** Raspberry Pi (Arayüz, RFID, Buzzer)
3. **Depolama ve Sunucu:** Orange Pi (Veritabanı, Web Arayüzü)

```mermaid
graph TD
    subgraph "Veri Toplama Birimleri"
        A[Arduino UNO] -- "UART (RX/TX)" --> RP[Raspberry Pi 4B]
        GPS[SIM808 GPS] --> A
        
        D[Deneyap Kart] -. "Bluetooth" .-> RP
        FP[DY50 Parmak İzi] --> D
        LCD[I2C LCD Ekran] --> D
    end

    subgraph "Ana Kontrol Birimi (Raspberry Pi)"
        RP --> RFID[RFID-RC522]
        RP --> BUZZ[Buzzer]
        RP --> GUI[Masaüstü Arayüzü]
    end

    subgraph "Sunucu ve Depolama (Orange Pi)"
        RP -- "Ethernet / Wi-Fi (HTTP)" --> OP[Orange Pi Web Sunucusu]
        OP --> HDD[(USB HDD / Veritabanı)]
        PC[Kullanıcı Bilgisayarı] -- "Web Tarayıcı" --> OP
    end

    style RP fill:#f9f,stroke:#333,stroke-width:2px
    style OP fill:#ff9,stroke:#333,stroke-width:2px
```

---

## 2. Donanım Bağlantı Şeması

Hangi pinin nereye bağlanacağını gösteren detaylı şema.

**ÖNEMLİ:** Arduino (5V) ve Raspberry Pi (3.3V) arasına Logic Level Converter takılmalıdır!

```mermaid
graph LR
    subgraph "Arduino UNO + GPS"
        SIM_TX((SIM808 TX)) --"Pin 2"--> ARD_RX[Arduino RX]
        SIM_RX((SIM808 RX)) --"Pin 3"--> ARD_TX[Arduino TX]
        SIM_PWR((SIM Pwr)) --"Harici 5V"--> SIM_VCC[SIM808 VCC]
        
        ARD_TX1[Pin 1 TX] --"UART"--> LVL[Level Converter]
        ARD_RX0[Pin 0 RX] --"UART"--> LVL
    end

    subgraph "Raspberry Pi 4B GPIO"
        LVL --"UART"--> RP_RX[GPIO 15 - RX]
        LVL --"UART"--> RP_TX[GPIO 14 - TX]
        
        RP_3V3[3.3V] --- RFID_3V3
        RP_GND1[GND] --- RFID_GND
        RP_24[GPIO 8] --- RFID_SDA[RFID SDA]
        RP_23[GPIO 11] --- RFID_SCK[RFID SCK]
        RP_19[GPIO 10] --- RFID_MOSI[RFID MOSI]
        RP_21[GPIO 9] --- RFID_MISO[RFID MISO]
        RP_22[GPIO 25] --- RFID_RST[RFID RST]
        
        RP_12[GPIO 18] --> BUZZ_POS[Buzzer +]
        RP_GND2[GND] --> BUZZ_NEG[Buzzer -]
    end

    subgraph "Deneyap Kart + DY50 + LCD"
        DY_TX((DY50 TX)) --"GPIO 16"--> DEN_RX[RX2]
        DY_RX((DY50 RX)) --"GPIO 17"--> DEN_TX[TX2]
        BTN1((Kayit Btn)) --"GPIO 4"--> DEN_D4
        BTN2((Gonder Btn)) --"GPIO 5"--> DEN_D5
        
        LCD_SDA((LCD SDA)) --"I2C SDA"--> DEN_SDA
        LCD_SCL((LCD SCL)) --"I2C SCL"--> DEN_SCL
    end
```

---

## 3. Veri Akış Senaryosu (Adım Adım)

Bir afetzede sisteme kaydedilirken veriler nasıl akar?

```mermaid
sequenceDiagram
    participant User as Operatör
    participant GUI as Raspberry Arayüzü
    participant GPS as Arduino GPS
    participant FP as Deneyap Parmak İzi
    participant LCD as Deneyap LCD
    participant RFID as RFID Kart
    participant Server as Orange Pi Sunucu

    Note over User, GUI: 1. Veri Girişi
    GPS->>GUI: "GPS:38.74,41.49" (Serial UART)
    User->>FP: Parmağı okutur
    FP->>LCD: "PARMAK OKUNDU\nID: 105"
    User->>FP: Gönder Butonuna Basar
    FP-->>GUI: "FP_ID:105" (Bluetooth)
    FP->>LCD: "VERI GONDERILDI"
    User->>GUI: Formu doldurur (Ad, Durum vb.)

    Note over User, GUI: 2. Kimliklendirme
    User->>GUI: "KİMLİKLENDİR" tıklar
    GUI->>GUI: Kimlik No üretir (TR-X1Y2...)
    GUI->>RFID: Kimlik No Yazar
    RFID-->>GUI: İşlem Başarılı
    GUI->>User: Buzzer "Bip-Bip" öter
    
    Note over GUI, Server: 3. Kayıt ve Aktarım
    GUI->>Server: HTTP POST (Tüm Veriler Json)
    Server->>Server: HDD'ye kaydeder
    Server-->>GUI: 200 OK (Başarılı)
```
