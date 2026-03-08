# TAMGA-ADKS

> 🥇 **TÜBİTAK 2204-A High School Research Projects Competition — Regional 1st Place · Turkey Finalist**

**Smart Attendance Control System** — RFID-based, FastAPI backend, web interface for personnel/student tracking.
Runs with real hardware on Raspberry Pi; testable on any PC with simulation mode.

---

## Features

- **RFID card reading** — RC522 module (Raspberry Pi)
- **Fingerprint** — Deneyap DY50 sensor (optional)
- **GPS tracking** — SIM808 module with location logging (optional)
- **Web interface** — Live attendance tracking, map view, QR code generation
- **Simulation mode** — Test without Raspberry Pi on any PC
- **Audio feedback** — success/error sounds, TTS (optional)
- **Offline operation** — no internet required, local SQLite/JSON
- **WebSocket** — real-time card reading events
- **Barcode/QR** — JsBarcode integration

---

## Hardware Requirements

| Component | Model | Required? |
|---|---|---|
| Main board | Raspberry Pi 3/4/5 or Orange Pi | Yes (production) |
| RFID reader | RC522 (SPI) | Yes |
| Fingerprint sensor | Deneyap DY50 | No |
| GPS module | SIM808 | No |
| Display | Any HDMI display or SSH | No |

> On any PC, use `--simulate` flag to run without hardware.

---

## Setup

### PC (Simulation Mode)

```bash
# 1. Clone the repo
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run in simulation mode
python tamga_backend.py --simulate

# 5. Open in browser
# → http://localhost:8000
```

### Raspberry Pi (Real Hardware)

```bash
# 1. Clone the repo
git clone https://github.com/hamzozcan/TAMGA-ADKS.git
cd TAMGA-ADKS

# 2. Run setup script
chmod +x start_all.sh
./start_all.sh

# Or directly:
python tamga_backend.py
```

### Run as a Service (systemd)
```bash
sudo cp donanim/tamga_adks_server.service /etc/systemd/system/
sudo systemctl enable tamga_adks_server
sudo systemctl start tamga_adks_server
```

---

## Usage

| Address | Description |
|---|---|
| `http://[RPi-IP]:8000` | Main web interface |
| `http://[RPi-IP]:8000/docs` | API documentation |
| `WS://[RPi-IP]:8000/ws` | Real-time card events |

### CLI Options
```bash
python tamga_backend.py --help

  --simulate    Simulation mode without hardware (for PC testing)
  --port 8080   Custom port (default: 8000)
```

---

## File Structure

```
TAMGA-ADKS/
├── tamga_backend.py       ← Main FastAPI server
├── tamga_launcher.py      ← Desktop launcher (pywebview)
├── tamga_voice_trainer.py ← Voice training tool
├── tamga_config.json      ← System configuration
├── requirements.txt       ← Python dependencies
├── start_all.sh           ← Single-command startup
├── templates/
│   └── tamga.html         ← Web interface
├── static/                ← CSS, JS, images
├── donanim/               ← Arduino/RPi setup files
│   ├── arduino_sim808_gps/       ← GPS Arduino code
│   ├── deneyap_dy50_fingerprint/ ← Fingerprint sensor code
│   └── esp32/                    ← ESP32 integration
├── belgeler/              ← Setup and system documentation
│   ├── kurulum_rehberi.md
│   ├── SISTEM_SEMASI.md
│   └── INTERNETSIZ_SISTEM.md
└── data/                  ← Local record database
```

---

## Tech Stack

- **FastAPI** + **Uvicorn** — web server
- **WebSocket** — real-time communication
- **RPi.GPIO** + **mfrc522** — RFID reading (RPi)
- **Folium** — map generation
- **pywebview** — native desktop window
- **JsBarcode** — barcode/QR generation
- **Arduino/ESP32** — external sensor integration

---

## Award

This project won **1st Place** in the regional TÜBİTAK 2204-A High School Research Projects Competition and advanced to the **Turkey Finals**.

TÜBİTAK 2204-A is Turkey's most prestigious national science competition for high school students.
