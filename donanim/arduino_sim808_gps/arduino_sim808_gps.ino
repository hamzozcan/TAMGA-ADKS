/*
 * TAMGA-ADKS Arduino UNO + SIM808 GPS Module
 * GPS verilerini Serial Pinler (RX/TX) üzerinden Raspberry Pi'ye gönderir
 *
 * Bağlantılar (UART):
 * Arduino TX (Pin 1) --> Level Converter --> RPi RX (GPIO 15)
 * Arduino RX (Pin 0) <-- Level Converter <-- RPi TX (GPIO 14)
 * Arduino GND        <--> RPi GND
 *
 * SIM808 Bağlantıları:
 * Arduino RX (Pin 6) <-- SIM808 TX
 * Arduino TX (Pin 7) --> SIM808 RX
 *
 * DİKKAT: Kod yüklerken Raspberry Pi bağlantısını (RX/TX) çıkarın!
 */

#include <SoftwareSerial.h>

// SIM808 pinleri
#define SIM808_RX 6
#define SIM808_TX 7

SoftwareSerial sim808(SIM808_RX, SIM808_TX);

// GPS Verisi
struct GPSData {
  double latitude;
  double longitude;
  String timestamp;
  bool valid;
};

GPSData gpsData;

// Zamanlama
unsigned long lastGPSSend = 0;
String nmeaBuffer = "";

void setup() {
  // Raspberry Pi ile haberleşme (Hardware Serial - Pin 0,1)
  Serial.begin(9600);

  // SIM808 ile haberleşme
  sim808.begin(9600);

  // Başlangıç mesajı
  Serial.println("GPS:WAITING");

  delay(1000);
  initSIM808GPS();
}

void loop() {
  readGPSData();

  // Periyodik gönderim (2 saniyede bir)
  if (millis() - lastGPSSend > 2000) {
    if (gpsData.valid) {
      sendGPSData();
    } else {
      Serial.println("GPS:WAITING");
    }
    lastGPSSend = millis();
  }

  delay(10);
}

void initSIM808GPS() {
  sendAT("AT", 1000);
  sendAT("AT+CGNSPWR=1", 1000);
  sendAT("AT+CGNSSEQ=\"RMC\"", 1000);
}

void sendAT(String cmd, int timeout) {
  sim808.println(cmd);
  // Yanıtı bekleme/okuma
  unsigned long t = millis();
  while (millis() - t < timeout) {
    while (sim808.available())
      sim808.read();
  }
}

void readGPSData() {
  static unsigned long lastQuery = 0;

  // 1 saniyede bir GPS verisi iste
  if (millis() - lastQuery > 1000) {
    sim808.println("AT+CGNSINF");
    lastQuery = millis();
  }

  while (sim808.available()) {
    char c = sim808.read();
    if (c == '\n') {
      processNMEA(nmeaBuffer);
      nmeaBuffer = "";
    } else if (c != '\r') {
      nmeaBuffer += c;
    }
  }
}

void processNMEA(String line) {
  if (line.startsWith("+CGNSINF:")) {
    line = line.substring(10);

    // Virgül sayma ve ayırma
    int idx = 0;
    String fields[20];
    int fieldCount = 0;

    for (int i = 0; i < line.length() && fieldCount < 20; i++) {
      if (line[i] == ',') {
        fieldCount++;
      } else {
        fields[fieldCount] += line[i];
      }
    }

    // fields[1] = fix status (1=Fix)
    // fields[3] = latitude
    // fields[4] = longitude
    // fields[2] = timestamp

    if (fieldCount >= 5 && fields[1] == "1") {
      gpsData.timestamp = fields[2];
      gpsData.latitude = fields[3].toDouble();
      gpsData.longitude = fields[4].toDouble();
      gpsData.valid = true;
    } else {
      gpsData.valid = false;
    }
  }
}

void sendGPSData() {
  // Format: GPS:lat,lon
  String data = "GPS:";
  data += String(gpsData.latitude, 6);
  data += ",";
  data += String(gpsData.longitude, 6);
  Serial.println(data);
}
