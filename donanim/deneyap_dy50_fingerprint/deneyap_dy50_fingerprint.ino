/*
 * TAMGA-ADKS Deneyap Kart + DY50 Parmak İzi Sensörü + I2C LCD Ekran
 * Bluetooth üzerinden parmak izi ID'sini Raspberry Pi'ye gönderir
 *
 * Bağlantılar:
 * DY50 TX → Deneyap D1
 * DY50 RX → Deneyap D4
 * DY50 VCC → 3.3V
 * DY50 GND → GND
 *
 * LCD Ekran (I2C):
 * LCD SDA → Deneyap DAC1
 * LCD SCL → Deneyap DAC2
 * LCD VCC → 3.3V veya 5V (Ekrana göre değişir)
 * LCD GND → GND
 *
 * Butonlar:
 * BUTON_KAYIT → D9 (Pull-up)
 * BUTON_GONDER → D13 (Pull-up)
 */

#include "BluetoothSerial.h"
#include <Adafruit_Fingerprint.h>
#include <LiquidCrystal_I2C.h>
#include <Wire.h>

// I2C LCD Ekran Ayarları
// Adres genellikle 0x27 veya 0x3F olur.
LiquidCrystal_I2C lcd(0x27, 16, 2);

// DY50 Seri Port (Hardware Serial 2)
#define DY50_RX D1
#define DY50_TX D4
#define DY50_UART_NR 2 // Hardware Serial 2 (UART2)

// Buton pinleri
#define BUTON_KAYIT D9   // Parmak izi kayıt butonu
#define BUTON_GONDER D13 // Veri gönder butonu

// Bluetooth ayarları
const char *DEVICE_NAME = "TAMGA-FP-SENSOR";

// Hardware Serial for DY50 (ESP32 supports HardwareSerial initialization with
// port number)
HardwareSerial fpSerial(DY50_UART_NR);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&fpSerial);

// Bluetooth Serial
BluetoothSerial SerialBT;

// Durum değişkenleri
bool bluetoothConnected = false;
int lastFingerprintID = 0; // -1 yerine 0 ile baslatildi
unsigned long lastScanTime = 0;
const unsigned long SCAN_INTERVAL = 500;

// Kayıt için değişkenler
int enrollID = 1;
bool enrollMode = false;
bool sensorFound = false;

void initSensor() {
  long bauds[] = {57600, 9600};
  sensorFound = false;

  for (int i = 0; i < 2; i++) {
    Serial.print("Sensor deneniyor, Baud: ");
    Serial.println(bauds[i]);
    fpSerial.begin(bauds[i], SERIAL_8N1, DY50_RX, DY50_TX);
    finger.begin(bauds[i]);

    if (finger.verifyPassword()) {
      sensorFound = true;
      Serial.print("DY50 sensoru bulundu! Baud: ");
      Serial.println(bauds[i]);
      break;
    }
    delay(200);
  }

  if (sensorFound) {
    finger.getTemplateCount();
    enrollID = finger.templateCount + 1;
    LCD_Show("SENSOR HAZIR", "KAYIT SAYISI: " + String(finger.templateCount));
    Serial.print("Sensor hazir. Kayitli parmak sayisi: ");
    Serial.println(finger.templateCount);
  } else {
    Serial.println("HATA: DY50 bulunamadi!");
    LCD_Show("HATA!", "SENSOR YOK");
    Serial.println("Kritik: Kablolarin (TX/RX) dogru oldugundan ve enerjinin "
                   "(3.3V) geldiginden emin olun.");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("TAMGA-ADKS Parmak Izi Sensoru + LCD");

  // LCD Başlat
  Wire.begin(DAC1, DAC2); // DAC1=SDA, DAC2=SCL olarak ayarlandı
  lcd.init();
  lcd.backlight();
  LCD_Show("TAMGA-ADKS", "SISTEM BASLIYOR");

  // Buton pinleri
  pinMode(BUTON_KAYIT, INPUT_PULLUP);
  pinMode(BUTON_GONDER, INPUT_PULLUP);

  // DY50 başlat - Otomatik Baud Rate Tespiti
  initSensor();

  delay(2000);

  // Bluetooth başlat
  // BluetoothSerial's begin() takes the device name as a String or char*
  SerialBT.begin(DEVICE_NAME);
  Serial.println("Bluetooth baslatildi");
  Serial.print("Cihaz Adi: ");
  Serial.println(DEVICE_NAME);
  LCD_Show("BLUETOOTH", "BAGLANTI BEKLNR");

  SerialBT.register_callback(btCallback);
}

void loop() {
  // Bluetooth bağlı değilse uyar
  if (!bluetoothConnected) {
    // LCD_Show("BLUETOOTH", "BAGLI DEGIL!"); // Sürekli yenilememek için buraya
    // yazmıyoruz
  }

  // BUTON 1: Kayıt modu
  if (digitalRead(BUTON_KAYIT) == LOW) {
    delay(50);
    if (digitalRead(BUTON_KAYIT) == LOW) {
      enrollFingerprint();
      while (digitalRead(BUTON_KAYIT) == LOW)
        delay(10);
      // Kayıt bitince ana ekrana dön
      if (lastFingerprintID > 0) {
        LCD_Show("PARMAK OKUTUN", "SON ID: " + String(lastFingerprintID));
      } else {
        LCD_Show("PARMAK OKUTUN", "BEKLENIYOR...");
      }
    }
  }

  // BUTON 2: Manuel gönder
  if (digitalRead(BUTON_GONDER) == LOW) {
    delay(50);
    if (digitalRead(BUTON_GONDER) == LOW) {
      if (lastFingerprintID > 0) {
        sendFingerprintID(lastFingerprintID);
      } else {
        LCD_Show("HATA", "ONCE OKUTUN");
        delay(1000);
        LCD_Show("PARMAK OKUTUN", "");
      }
      while (digitalRead(BUTON_GONDER) == LOW)
        delay(10);
    }
  }

  // Otomatik parmak izi tarama
  if (!enrollMode && millis() - lastScanTime > SCAN_INTERVAL) {
    int result = scanFingerprint();
    if (result > 0) {
      lastFingerprintID = result;
      // LCD Bilgisi scanFingerprint içinde de güncellenebilir ama burada
      // gönderim var
      sendFingerprintID(result);

      // Mesajın görünmesi için biraz bekle
      LCD_Show("PARMAK OKUTUN",
               (lastFingerprintID > 0 ? "SON ID: " + String(lastFingerprintID)
                                      : ""));
    }
    lastScanTime = millis();
  }

  // Serial Monitor komut dinle (Hata giderme için)
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "SAY") {
      if (sensorFound) {
        finger.getTemplateCount();
        Serial.print("Kayitli Parmak Sayisi: ");
        Serial.println(finger.templateCount);
      } else {
        Serial.println("Hata: Sensor bagli degil, sayim yapilamaz.");
      }
    } else if (cmd == "DENE") {
      initSensor();
    } else if (cmd == "YARDIM") {
      Serial.println("--- KOMUT LISTESI ---");
      Serial.println("SAY : Kayitli parmak sayisini gosterir");
      Serial.println("DENE: Sensoru tekrar baglamaya calisir");
      Serial.println("KAYIT: Yeni parmak izi kaydini baslatir");
      Serial.println("SIL : TUM hafizayi temizler (DIKKAT!)");
      Serial.println("---------------------");
    } else if (cmd == "KAYIT") {
      enrollFingerprint();
    } else if (cmd == "SIL") {
      if (sensorFound) {
        finger.emptyDatabase();
        enrollID = 1;
        Serial.println("HAFIZA TEMIZLENDI! Tum kayitlar silindi.");
        LCD_Show("HAFIZA SILINDI", "ID SIFIRLANDI");
        delay(2000);
        LCD_Show("PARMAK OKUTUN", "");
      } else {
        Serial.println("Hata: Sensor bagli degil, silme yapilamaz.");
      }
    }
  }

  // Bluetooth komut dinle
  if (SerialBT.available()) {
    String cmd = SerialBT.readStringUntil('\n');
    cmd.trim();
    processCommand(cmd);
  }

  delay(50);
}

// LCD Yardımcı Fonksiyonu
void LCD_Show(String line1, String line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

int scanFingerprint() {
  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK)
    return -1;

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK)
    return -1;

  p = finger.fingerSearch();
  if (p == FINGERPRINT_OK) {
    Serial.print("Bulundu ID: ");
    Serial.println(finger.fingerID);
    LCD_Show("PARMAK OKUNDU", "KIMLIK ID: " + String(finger.fingerID));
    return finger.fingerID;
  } else {
    LCD_Show("TANIMSIZ", "PARMAK");
    delay(1000);
    LCD_Show("PARMAK OKUTUN", "");
  }

  return -1;
}

// 30 saniye içinde parmak VEYA buton bekleyen yardımcı fonksiyon
// 0: Zaman aşımı, 1: Parmak bulundu, 2: Butona basıldı
int waitForFingerOrButton(uint32_t timeoutMs) {
  uint32_t startTime = millis();

  // Önce butonun bırakılmasını bekleyelim
  while (digitalRead(BUTON_KAYIT) == LOW)
    delay(10);
  delay(100);

  while (true) {
    if (finger.getImage() == FINGERPRINT_OK)
      return 1; // Parmak bulundu

    if (digitalRead(BUTON_KAYIT) == LOW) { // Butona tekrar basıldı
      delay(50);
      if (digitalRead(BUTON_KAYIT) == LOW)
        return 2;
    }

    if (millis() - startTime > timeoutMs)
      return 0; // Zaman aşımı
    delay(50);
  }
}

void enrollFingerprint() {
  enrollMode = true;
  LCD_Show("KAYIT MODU", "ID: " + String(enrollID));
  delay(1000);

  LCD_Show("PARMAK OKUTUN", "");

  // Parmak veya Buton bekleyelim
  int result = waitForFingerOrButton(30000);

  if (result == 0) { // Zaman aşımı
    LCD_Show("ZAMAN ASIMI", "IPTAL EDILDI");
    delay(2000);
    enrollMode = false;
    return;
  }

  if (result == 2) { // Butona tekrar basıldı, manuel kayıt yap
    LCD_Show("MANUEL KAYIT", "ID: " + String(enrollID));
    sendFingerprintID(enrollID); // Raspberry'ye gönder
    Serial.print("Manuel Kayit Yapildi! ID: ");
    Serial.println(enrollID);
    enrollID++;
    delay(2000);
    enrollMode = false;
    return;
  }

  // Buradan aşağısı normal parmak izi okuma (result == 1)
  LCD_Show("OKUNUYOR...", "LUTFEN BEKLEYIN");

  // İlk okuma buffer'a alındı zaten (waitForFingerOrButton içinde getImage()
  // yapıldı)
  if (finger.image2Tz(1) != FINGERPRINT_OK) {
    LCD_Show("HATA", "OKUMA HATASI-1");
    delay(1500);
    enrollMode = false;
    return;
  }

  delay(500);

  // İkinci okuma (Daha dayanıklı hale getirildi)
  LCD_Show("OKUNUYOR...", "BEKLEYIN (2/2)");

  uint32_t secondStart = millis();
  while (finger.getImage() != FINGERPRINT_OK) {
    if (millis() - secondStart >
        5000) { // 5 saniye içinde ikinci okuma gelmezse hata ver
      LCD_Show("HATA", "OKUMA HATASI-2");
      delay(1500);
      enrollMode = false;
      return;
    }
    delay(50);
  }

  if (finger.image2Tz(2) != FINGERPRINT_OK) {
    LCD_Show("HATA", "MODEL HATASI-2");
    delay(1500);
    enrollMode = false;
    return;
  }

  // Model oluştur ve kaydet
  if (finger.createModel() != FINGERPRINT_OK) {
    LCD_Show("HATA", "MODEL HATASI");
    delay(1500);
    enrollMode = false;
    return;
  }

  if (finger.storeModel(enrollID) != FINGERPRINT_OK) {
    LCD_Show("HATA", "KAYIT HATASI");
    delay(1500);
    enrollMode = false;
    return;
  }

  LCD_Show("KAYIT BASARILI", "YENI ID: " + String(enrollID));
  Serial.print("Basariyla kaydedildi! ID: ");
  Serial.println(enrollID);

  enrollID++;
  delay(2000);
  enrollMode = false;
}

void sendFingerprintID(int id) {
  String message = "FP_ID:" + String(id);

  if (bluetoothConnected) {
    SerialBT.println(message);
    LCD_Show("VERI GONDERILDI", "RPI'YE BAGLI");
  } else {
    LCD_Show("GONDERILEMEDI", "BT HATASI!");
  }
}

void processCommand(String cmd) {
  if (cmd == "STATUS") {
    SerialBT.println("STATUS:OK");
  } else if (cmd == "PING") {
    SerialBT.println("PONG");
  }
}

void btCallback(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  if (event == ESP_SPP_SRV_OPEN_EVT) {
    bluetoothConnected = true;
    LCD_Show("BLUETOOTH", "BAGLANDI!");
    delay(1000);
    LCD_Show("PARMAK OKUTUN", "");
  } else if (event == ESP_SPP_CLOSE_EVT) {
    bluetoothConnected = false;
    LCD_Show("BLUETOOTH", "BAGLANTI KOPTU");
  }
}
