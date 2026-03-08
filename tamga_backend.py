"""
TAMGA-ADKS Backend v2.0
=======================
FastAPI tabanlı backend — Raspberry Pi'de gerçek donanım,
normal bilgisayarda --simulate bayrağıyla simülasyon modu.

Çalıştırma:
  Normal PC (simülasyon): python tamga_backend_v2.py --simulate
  Raspberry Pi (donanım): python tamga_backend_v2.py
  Özel port           :   python tamga_backend_v2.py --port 8080
"""

# ─────────────────────────────────────────────
# BÖLÜM 1 — Import'lar & Sabitler
# ─────────────────────────────────────────────
import argparse
import asyncio
import csv
import html
import io
import json
import logging
import math
import os
import random
import string
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Opsiyonel: harita üretimi
try:
    import folium
    FOLIUM_OK = True
except ImportError:
    folium = None
    FOLIUM_OK = False

# Opsiyonel: QR üretimi
try:
    import qrcode
    QR_OK = True
except ImportError:
    qrcode = None
    QR_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    Image = None
    PIL_OK = False

# ─── AES-256-GCM Şifreleme ───────────────────────
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TAMGA")

BASE_DIR      = Path(__file__).parent
RECORDS_FILE  = BASE_DIR / "records.json"
KEY_FILE      = BASE_DIR / "tamga.key"

def _load_or_create_key() -> bytes:
    if KEY_FILE.exists():
        return base64.b64decode(KEY_FILE.read_bytes().strip())
    key = os.urandom(32)
    KEY_FILE.write_bytes(base64.b64encode(key))
    log.info("Yeni AES-256 anahtarı oluşturuldu: tamga.key")
    return key

def _encrypt_records(records: list) -> bytes:
    aesgcm = AESGCM(AES_KEY)
    nonce  = os.urandom(12)
    plain  = json.dumps(records, ensure_ascii=False).encode("utf-8")
    ct     = aesgcm.encrypt(nonce, plain, None)
    return base64.b64encode(nonce + ct)

def _decrypt_records(blob: bytes) -> list:
    raw    = base64.b64decode(blob)
    aesgcm = AESGCM(AES_KEY)
    plain  = aesgcm.decrypt(raw[:12], raw[12:], None)
    return json.loads(plain)

AES_KEY = _load_or_create_key()

TILE_CACHE    = BASE_DIR / "map_cache" / "tiles"
SAT_CACHE     = BASE_DIR / "map_cache" / "satellite"
TILE_CACHE.mkdir(parents=True, exist_ok=True)
SAT_CACHE.mkdir(parents=True, exist_ok=True)
CONFIG_FILE  = BASE_DIR / "tamga_config.json"
TEMPLATE_FILE = BASE_DIR / "templates" / "tamga.html"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)
VOICE_ALIAS_FILE = BASE_DIR / "voice_aliases.json"
VOICE_ALIAS_PROFILE_FILE = BASE_DIR / "voice_alias_profiles.json"

ORANGE_PI_URL = "http://192.168.1.100:8080"   # Değiştirebilirsiniz
BUZZER_PIN = 18


def _normalize_profile_name(name: str) -> str:
    p = (name or "").strip().lower()
    return p if p else "default"


def _clean_alias_map(raw: Dict) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        kk = " ".join(k.lower().split())
        vv = " ".join(v.lower().split())
        if kk and vv:
            out[kk] = vv
    return out


def _load_base_voice_alias_profiles() -> Dict[str, Dict[str, str]]:
    if not VOICE_ALIAS_FILE.exists():
        return {"default": {}}
    try:
        raw = json.loads(VOICE_ALIAS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"default": {}}
    if not isinstance(raw, dict):
        return {"default": {}}

    # Eski format: {"heard":"canonical",...}
    if raw and all(isinstance(v, str) for v in raw.values()):
        return {"default": _clean_alias_map(raw)}

    # Yeni format: {"default": {...}, "admin": {...}}
    profiles: Dict[str, Dict[str, str]] = {"default": {}}
    for profile, aliases in raw.items():
        if isinstance(aliases, dict):
            profiles[_normalize_profile_name(str(profile))] = _clean_alias_map(aliases)
    if "default" not in profiles:
        profiles["default"] = {}
    return profiles


def _load_custom_voice_alias_profiles() -> Dict[str, Dict[str, str]]:
    if not VOICE_ALIAS_PROFILE_FILE.exists():
        return {}
    try:
        raw = json.loads(VOICE_ALIAS_PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    custom: Dict[str, Dict[str, str]] = {}
    for profile, aliases in raw.items():
        if isinstance(aliases, dict):
            custom[_normalize_profile_name(str(profile))] = _clean_alias_map(aliases)
    return custom


def _save_custom_voice_alias_profiles(custom: Dict[str, Dict[str, str]]):
    cleaned: Dict[str, Dict[str, str]] = {}
    for profile, aliases in custom.items():
        p = _normalize_profile_name(profile)
        a = _clean_alias_map(aliases)
        if a:
            cleaned[p] = a
    VOICE_ALIAS_PROFILE_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_voice_alias_profiles() -> Dict[str, Dict[str, str]]:
    base = _load_base_voice_alias_profiles()
    custom = _load_custom_voice_alias_profiles()
    merged: Dict[str, Dict[str, str]] = {"default": {}}
    for src in (base, custom):
        for profile, aliases in src.items():
            p = _normalize_profile_name(profile)
            merged.setdefault(p, {})
            merged[p].update(_clean_alias_map(aliases))
    if "default" not in merged:
        merged["default"] = {}
    return merged


def _build_export_object(records: List[Dict]) -> Dict:
    return {
        "version": "1.1",
        "system": "TAMGA-ADKS",
        "timestamp": datetime.now().isoformat(),
        "record_count": len(records),
        "records": records,
    }


def _encrypt_export_blob(export_obj: Dict) -> bytes:
    aesgcm = AESGCM(AES_KEY)
    nonce = os.urandom(12)
    plain = json.dumps(export_obj, ensure_ascii=False).encode("utf-8")
    ct = aesgcm.encrypt(nonce, plain, None)
    return base64.b64encode(nonce + ct)


def _export_csv_bytes(records: List[Dict]) -> bytes:
    ordered = [
        "KİMLİK NO",
        "TARİH/SAAT",
        "AD SOYAD",
        "TRİYAJ",
        "CİNSİYET",
        "EKİP",
        "OLAY KODU",
        "GPS",
        "PARMAK İZİ ID",
        "RFID UID",
        "DNA",
        "VÜCUT BULGULARI",
        "EKSİK DİŞLER",
        "BOY",
        "KİLO",
        "SAÇ",
        "GÖZ",
        "NOTLAR",
    ]
    extra = sorted({k for r in records for k in r.keys() if k not in ordered})
    fields = ordered + extra
    s = io.StringIO()
    writer = csv.DictWriter(s, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow({k: r.get(k, "") for k in fields})
    return s.getvalue().encode("utf-8-sig")


_TR_ASCII_MAP = str.maketrans({
    "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
})


def _ascii_text(txt: str) -> str:
    val = str(txt or "").translate(_TR_ASCII_MAP)
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in val)


def _pdf_escape(txt: str) -> str:
    return txt.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: List[str]) -> bytes:
    if not lines:
        lines = ["TAMGA-ADKS"]
    safe = [_pdf_escape(_ascii_text(x))[:110] for x in lines[:52]]
    body = ["BT", "/F1 11 Tf", "50 800 Td", "14 TL", f"({safe[0]}) Tj"]
    for line in safe[1:]:
        body.append(f"T* ({line}) Tj")
    body.append("ET")
    stream = ("\n".join(body) + "\n").encode("latin-1", "replace")

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))
    out.write(
        f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode("ascii")
    )
    return out.getvalue()


def _summary_pdf_bytes(records: List[Dict], stats: Dict) -> bytes:
    tri = stats.get("triage", {})
    lines = [
        "TAMGA-ADKS ACIL DURUM OZET RAPORU",
        f"Rapor Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Toplam Kayit: {stats.get('total', len(records))}",
        f"KIRMIZI: {tri.get('KIRMIZI', 0)}",
        f"SARI: {tri.get('SARI', 0)}",
        f"YESIL: {tri.get('YEŞİL', tri.get('YESIL', 0))}",
        f"SIYAH: {tri.get('SİYAH', tri.get('SIYAH', 0))}",
        "",
        "Son Kayitlar:",
    ]
    for rec in list(records)[-20:][::-1]:
        lines.append(
            f"- {rec.get('KİMLİK NO', '-')}"
            f" | {rec.get('AD SOYAD', 'Bilinmiyor')}"
            f" | {rec.get('TRİYAJ', '-')}"
            f" | {rec.get('GPS', '-')}"
        )
    return _build_simple_pdf(lines)


def _data_url_to_bytes(data_url: str) -> Optional[bytes]:
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None
    try:
        b64 = data_url.split(",", 1)[1]
        return base64.b64decode(b64)
    except Exception:
        return None


def _grayscale_data_url(data_url: str) -> Optional[str]:
    raw = _data_url_to_bytes(data_url)
    if not raw:
        return None
    if not PIL_OK:
        return data_url
    try:
        img = Image.open(io.BytesIO(raw)).convert("L")
        out = io.BytesIO()
        img.save(out, format="PNG")
        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return data_url


def _norm_text(v: str) -> str:
    t = str(v or "").strip().lower().replace("i̇", "i")
    return " ".join(t.split())


def _detect_record_conflicts(existing_records: List[Dict], body: "RecordIn") -> List[Dict[str, str]]:
    fp = _norm_text(body.parmak_izi_id)
    rfid = _norm_text(body.rfid_uid)
    ad = _norm_text(body.ad_soyad)
    gps = _norm_text(body.gps)
    out: List[Dict[str, str]] = []

    for r in existing_records:
        reasons: List[str] = []
        if fp and _norm_text(r.get("PARMAK İZİ ID", "")) == fp:
            reasons.append("parmak izi eşleşmesi")
        if rfid and _norm_text(r.get("RFID UID", "")) == rfid:
            reasons.append("RFID eşleşmesi")
        if ad and _norm_text(r.get("AD SOYAD", "")) == ad:
            reasons.append("ad soyad benzerliği")
        if gps and _norm_text(r.get("GPS", "")) == gps and gps:
            reasons.append("aynı GPS noktası")

        if reasons:
            out.append({
                "id": str(r.get("KİMLİK NO", "-")),
                "name": str(r.get("AD SOYAD", "Bilinmiyor")),
                "reason": ", ".join(reasons),
            })
        if len(out) >= 6:
            break
    return out

# ─────────────────────────────────────────────
# BÖLÜM 2 — Donanım Soyutlama Katmanı (HAL)
# ─────────────────────────────────────────────

class SimulatedGPIO:
    BCM = OUT = IN = HIGH = LOW = BOARD = 0
    def setmode(self, *a): pass
    def setup(self, *a, **kw): pass
    def output(self, *a): pass
    def cleanup(self): pass
    def setwarnings(self, *a): pass


class BuzzerManager:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.gpio = None
        if not simulate:
            try:
                import RPi.GPIO as GPIO
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(BUZZER_PIN, GPIO.OUT)
                self.gpio = GPIO
                log.info("Buzzer: GPIO hazır")
            except Exception as e:
                log.warning(f"Buzzer GPIO hatası, simülasyona geçiliyor: {e}")
                self.simulate = True

    def beep(self, pattern="short"):
        patterns = {
            "short":   [(0.1, True), (0.1, False)],
            "success": [(0.1, True), (0.05, False), (0.1, True), (0.05, False)],
            "error":   [(0.5, True), (0.1, False)],
            "long":    [(0.8, True), (0.1, False)],
        }
        seq = patterns.get(pattern, patterns["short"])
        if self.simulate:
            log.info(f"[SIM] Buzzer: {pattern}")
            return
        def _run():
            for dur, state in seq:
                self.gpio.output(BUZZER_PIN, self.gpio.HIGH if state else self.gpio.LOW)
                time.sleep(dur)
            self.gpio.output(BUZZER_PIN, self.gpio.LOW)
        threading.Thread(target=_run, daemon=True).start()

    def cleanup(self):
        if self.gpio:
            self.gpio.cleanup()


class GPSManager:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.serial_port = None
        self.lat = 39.9334
        self.lon = 32.8597
        self._lock = threading.Lock()
        self._running = False
        if not simulate:
            try:
                import serial as pyserial
                ports = ["/dev/serial0", "/dev/ttyS0", "/dev/ttyAMA0", "/dev/ttyUSB0"]
                for p in ports:
                    try:
                        self.serial_port = pyserial.Serial(p, 9600, timeout=1)
                        log.info(f"GPS: {p} üzerinden bağlandı")
                        break
                    except Exception:
                        continue
                if not self.serial_port:
                    raise RuntimeError("GPS portu bulunamadı")
            except Exception as e:
                log.warning(f"GPS seri port hatası, simülasyona geçiliyor: {e}")
                self.simulate = True

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        if self.serial_port:
            self.serial_port.close()

    def _loop(self):
        while self._running:
            if self.simulate:
                # Türkiye içinde yavaş hareket
                with self._lock:
                    self.lat += random.uniform(-0.0001, 0.0001)
                    self.lon += random.uniform(-0.0001, 0.0001)
                    self.lat = max(36.0, min(42.0, self.lat))
                    self.lon = max(26.0, min(45.0, self.lon))
                time.sleep(3)
            else:
                try:
                    line = self.serial_port.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("GPS:"):
                        parts = line[4:].split(",")
                        if len(parts) == 2:
                            with self._lock:
                                self.lat = float(parts[0])
                                self.lon = float(parts[1])
                except Exception:
                    time.sleep(1)

    def get(self):
        with self._lock:
            return {"lat": round(self.lat, 6), "lon": round(self.lon, 6)}


class RFIDManager:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.reader = None
        if not simulate:
            try:
                from mfrc522 import SimpleMFRC522
                self.reader = SimpleMFRC522()
                log.info("RFID: RC522 hazır")
            except Exception as e:
                log.warning(f"RFID hatası, simülasyona geçiliyor: {e}")
                self.simulate = True

    def read(self) -> Dict:
        if self.simulate:
            uid = "".join(random.choices("0123456789ABCDEF", k=8))
            text = f"TR-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
            log.info(f"[SIM] RFID okundu: uid={uid} text={text}")
            return {"uid": uid, "text": text, "success": True}
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            uid, text = self.reader.read()
            return {"uid": str(uid), "text": str(text).strip(), "success": True}
        except Exception as e:
            return {"uid": "", "text": "", "success": False, "error": str(e)}

    def write(self, text: str) -> Dict:
        if self.simulate:
            log.info(f"[SIM] RFID yazıldı: {text}")
            return {"success": True}
        try:
            self.reader.write(text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


class FingerprintManager:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.sock = None
        self._connected = False
        if not simulate:
            threading.Thread(target=self._connect_bt, daemon=True).start()

    def _connect_bt(self):
        try:
            import bluetooth
            devices = bluetooth.discover_devices(lookup_names=True, duration=8)
            for addr, name in devices:
                if "TAMGA" in name or "FP" in name:
                    self.sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                    self.sock.connect((addr, 1))
                    self._connected = True
                    log.info(f"Bluetooth parmak izi sensörü bağlandı: {name} ({addr})")
                    break
        except Exception as e:
            log.warning(f"Bluetooth bağlantısı başarısız, simülasyona geçiliyor: {e}")
            self.simulate = True

    def scan(self) -> Dict:
        if self.simulate:
            fp_id = str(random.randint(1, 127))
            log.info(f"[SIM] Parmak izi okundu: ID={fp_id}")
            return {"id": fp_id, "found": True, "success": True}
        if not self._connected or not self.sock:
            return {"id": "", "found": False, "success": False, "error": "Bluetooth bağlı değil"}
        try:
            self.sock.send("SCAN\n")
            data = self.sock.recv(128).decode("utf-8", errors="ignore").strip()
            if data.startswith("FP_ID:"):
                fp_id = data[6:]
                return {"id": fp_id, "found": True, "success": True}
            return {"id": "", "found": False, "success": True, "raw": data}
        except Exception as e:
            return {"id": "", "found": False, "success": False, "error": str(e)}


# ─────────────────────────────────────────────
# BÖLÜM 3 — Veri Yöneticisi
# ─────────────────────────────────────────────

class DataManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._records: List[Dict] = []
        self._load()

    def _load(self):
        if RECORDS_FILE.exists():
            try:
                raw = RECORDS_FILE.read_bytes().strip()
                # Migration: plain JSON → şifreli
                try:
                    data = json.loads(raw)
                    self._records = data if isinstance(data, list) else []
                    log.info(f"Plain JSON bulundu, şifrelenerek kaydedilecek: {len(self._records)} kayıt")
                    self._save()  # şifreli olarak yeniden kaydet
                except (json.JSONDecodeError, ValueError):
                    self._records = _decrypt_records(raw)
                log.info(f"Veri yüklendi: {len(self._records)} kayıt")
            except Exception as e:
                log.error(f"records.json okuma hatası: {e}")
                self._records = []

    def _save(self):
        try:
            RECORDS_FILE.write_bytes(_encrypt_records(self._records))
        except Exception as e:
            log.error(f"records.json kaydetme hatası: {e}")

    def get_all(self) -> List[Dict]:
        with self._lock:
            return list(self._records)

    def get_by_id(self, kimlik_no: str) -> Optional[Dict]:
        with self._lock:
            for r in self._records:
                if r.get("KİMLİK NO") == kimlik_no:
                    return dict(r)
        return None

    def add(self, record: Dict) -> Dict:
        with self._lock:
            self._records.append(record)
            self._save()
        return record

    def update_transfer(self, kimlik_no: str, status: str) -> Optional[Dict]:
        with self._lock:
            for r in self._records:
                if r.get("KİMLİK NO") == kimlik_no:
                    r["TRANSFER DURUMU"] = status
                    r["SON GÜNCELLEME"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._save()
                    return dict(r)
        return None

    def delete(self, kimlik_no: str) -> bool:
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.get("KİMLİK NO") != kimlik_no]
            if len(self._records) < before:
                self._save()
                return True
            return False

    def search(self, query: str) -> List[Dict]:
        q = query.lower()
        with self._lock:
            return [
                r for r in self._records
                if any(q in str(v).lower() for v in r.values())
            ]

    def stats(self) -> Dict:
        with self._lock:
            total = len(self._records)
            triage = {"KIRMIZI": 0, "SARI": 0, "YEŞİL": 0, "SİYAH": 0, "BİLİNMİYOR": 0}
            gender = {"Erkek": 0, "Kadın": 0, "Bilinmiyor": 0}
            for r in self._records:
                t = r.get("TRİYAJ", "")
                if "KIRMIZI" in t: triage["KIRMIZI"] += 1
                elif "SARI" in t:  triage["SARI"] += 1
                elif "YEŞİL" in t: triage["YEŞİL"] += 1
                elif "SİYAH" in t: triage["SİYAH"] += 1
                else:              triage["BİLİNMİYOR"] += 1
                g = r.get("CİNSİYET", "Bilinmiyor")
                if "Male" in g or "Erkek" in g: gender["Erkek"] += 1
                elif "Female" in g or "Kadın" in g: gender["Kadın"] += 1
                else: gender["Bilinmiyor"] += 1
            return {"total": total, "triage": triage, "gender": gender}


# ─────────────────────────────────────────────
# BÖLÜM 4 — Güvenlik Yöneticisi
# ─────────────────────────────────────────────

class SecurityManager:
    DEFAULT_USERS = [
        {"username": "goruntule", "password": "1234", "role": "viewer"},
        {"username": "admin",     "password": "1001", "role": "admin"},
        {"username": "doktor",    "password": "2222", "role": "doctor"},
        {"username": "saha",      "password": "3333", "role": "saha"},
        {"username": "izleme",    "password": "4444", "role": "izleme"},
    ]

    ROLE_PERMISSIONS = {
        "admin":  {"view": True, "delete": True, "export": True, "package": True, "change_password": True, "transfer_update": True, "bulk_qr": True, "prefetch_map": True},
        "doctor": {"view": True, "delete": False, "export": True, "package": True, "change_password": False, "transfer_update": True, "bulk_qr": True, "prefetch_map": True},
        "saha":   {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": True, "bulk_qr": True, "prefetch_map": False},
        "izleme": {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": False, "bulk_qr": False, "prefetch_map": False},
        "viewer": {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": False, "bulk_qr": False, "prefetch_map": False},
    }

    def __init__(self):
        self._lock = threading.Lock()
        self.data = self._load()
        # Migrate old single-password config → users list
        if "users" not in self.data:
            old_pw = self.data.get("password", "1001")
            self.data["users"] = [
                {"username": "goruntule", "password": "1234",   "role": "viewer"},
                {"username": "admin",     "password": old_pw,   "role": "admin"},
            ]
            self._save()
        changed = self._ensure_default_users()
        if changed:
            self._save()

    def _load(self) -> Dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"users": [u.copy() for u in self.DEFAULT_USERS], "login_count": 0}

    def _save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _ensure_default_users(self) -> bool:
        users = self.data.setdefault("users", [])
        changed = False
        idx = {u.get("username"): u for u in users if isinstance(u, dict)}
        for du in self.DEFAULT_USERS:
            u = idx.get(du["username"])
            if not u:
                users.append(du.copy())
                changed = True
            elif not u.get("role"):
                u["role"] = du["role"]
                changed = True
        return changed

    def verify_user(self, username: str, password: str) -> Optional[str]:
        """Kullanıcı adı + şifre doğrula; rol döndür (None = hatalı)."""
        for u in self.data.get("users", []):
            if u["username"] == username and u["password"] == password:
                return u["role"]
        return None

    def change_password(self, username: str, new_password: str) -> bool:
        with self._lock:
            for u in self.data.get("users", []):
                if u["username"] == username:
                    u["password"] = new_password
                    self._save()
                    return True
        return False

    def role_permissions(self, role: str) -> Dict[str, bool]:
        return dict(self.ROLE_PERMISSIONS.get(role, self.ROLE_PERMISSIONS["viewer"]))

    # Geriye dönük uyumluluk
    def verify_password(self, pw: str) -> bool:
        return self.verify_user("admin", pw) is not None

    def needs_reset(self) -> bool:
        return False


# ─────────────────────────────────────────────
# BÖLÜM 5 — Harita Yöneticisi (Folium)
# ─────────────────────────────────────────────

class MapManager:
    def generate(self, records: List[Dict], center_lat=39.9, center_lon=32.8) -> str:
        if not FOLIUM_OK:
            return "<p style='color:red'>Folium kütüphanesi bulunamadı. pip install folium</p>"
        triage_colors = {
            "KIRMIZI": "red",
            "SARI":    "orange",
            "YEŞİL":   "green",
            "SİYAH":   "black",
        }
        m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="OpenStreetMap")
        for r in records:
            gps = r.get("GPS", "")
            if not gps or "," not in gps:
                continue
            try:
                lat, lon = map(float, gps.split(","))
            except Exception:
                continue
            triyaj = r.get("TRİYAJ", "")
            color = "blue"
            for k, v in triage_colors.items():
                if k in triyaj:
                    color = v
                    break
            popup_html = f"""
            <b>{r.get('AD SOYAD', 'Bilinmiyor')}</b><br>
            ID: {r.get('KİMLİK NO', '-')}<br>
            Triyaj: <span style='color:{color}'>{triyaj}</span><br>
            GPS: {lat:.5f}, {lon:.5f}<br>
            Tarih: {r.get('TARİH/SAAT', '-')}
            """
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=r.get("AD SOYAD", "?"),
            ).add_to(m)
        return m._repr_html_()


# ─────────────────────────────────────────────
# BÖLÜM 5b — Tile Yöneticisi (Offline Harita)
# ─────────────────────────────────────────────

class TileManager:
    """OSM ve uydu tile'larını yerel dizinde önbelleğe alır."""

    OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    SAT_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    HEADERS = {"User-Agent": "TAMGA-ADKS/2.0 (offline map caching)"}

    # Türkiye bölgesi lon/lat sınırları
    TURKEY_BOUNDS = {"min_lat": 35.8, "max_lat": 42.2, "min_lon": 25.6, "max_lon": 44.8}

    def _deg2tile(self, lat, lon, z):
        lat_r = math.radians(lat)
        n = 2 ** z
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
        return x, y

    def _fetch(self, url: str) -> Optional[bytes]:
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=10)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return None

    def get_osm_tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        path = TILE_CACHE / str(z) / str(x) / f"{y}.png"
        if path.exists():
            return path.read_bytes()
        data = self._fetch(self.OSM_URL.format(z=z, x=x, y=y))
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return data

    def get_sat_tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        path = SAT_CACHE / str(z) / str(x) / f"{y}.png"
        if path.exists():
            return path.read_bytes()
        data = self._fetch(self.SAT_URL.format(z=z, x=x, y=y))
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return data

    def prefetch_turkey(self, min_zoom: int = 4, max_zoom: int = 8, include_sat: bool = False, progress_cb=None):
        """Türkiye için tile paketini indir."""
        b = self.TURKEY_BOUNDS
        min_zoom = max(1, int(min_zoom))
        max_zoom = max(min_zoom, int(max_zoom))

        def _tile_bounds(z: int):
            # Kuzeybatı ve güneydoğu köşelerinden gelen indeksleri normalize et.
            x_a, y_a = self._deg2tile(b["max_lat"], b["min_lon"], z)
            x_b, y_b = self._deg2tile(b["min_lat"], b["max_lon"], z)
            x_min, x_max = (x_a, x_b) if x_a <= x_b else (x_b, x_a)
            y_min, y_max = (y_a, y_b) if y_a <= y_b else (y_b, y_a)
            return x_min, x_max, y_min, y_max

        total = 0
        for z in range(min_zoom, max_zoom + 1):
            x_min, x_max, y_min, y_max = _tile_bounds(z)
            total += (x_max - x_min + 1) * (y_max - y_min + 1)

        processed = 0
        downloaded_osm = 0
        downloaded_sat = 0

        for z in range(min_zoom, max_zoom + 1):
            x_min, x_max, y_min, y_max = _tile_bounds(z)
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    osm_path = TILE_CACHE / str(z) / str(x) / f"{y}.png"
                    if not osm_path.exists():
                        if self.get_osm_tile(z, x, y):
                            downloaded_osm += 1
                    if include_sat:
                        sat_path = SAT_CACHE / str(z) / str(x) / f"{y}.png"
                        if not sat_path.exists():
                            if self.get_sat_tile(z, x, y):
                                downloaded_sat += 1

                    processed += 1
                    if progress_cb and (processed % 25 == 0 or processed == total):
                        progress_cb(processed, total, downloaded_osm, downloaded_sat, z)
                    time.sleep(0.03)

        log.info(
            f"Tile prefetch tamamlandı: OSM={downloaded_osm}, SAT={downloaded_sat}, "
            f"zoom {min_zoom}-{max_zoom}, include_sat={include_sat}"
        )
        return {
            "processed": processed,
            "total": total,
            "downloaded_osm": downloaded_osm,
            "downloaded_sat": downloaded_sat,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "include_sat": include_sat,
        }


# ─────────────────────────────────────────────
# BÖLÜM 6 — Orange Pi Senkronizasyon
# ─────────────────────────────────────────────

class SyncManager:
    def __init__(self, server_url: str):
        self.url = server_url.rstrip("/")
        self._synced: Set[str] = set()
        self._lock = threading.Lock()

    def sync_record(self, record: Dict) -> bool:
        kid = record.get("KİMLİK NO", "")
        with self._lock:
            if kid in self._synced:
                return True
        try:
            r = requests.post(f"{self.url}/api/data", json=record, timeout=5)
            if r.status_code == 200:
                with self._lock:
                    self._synced.add(kid)
                log.info(f"Senkronize edildi: {kid}")
                return True
        except Exception as e:
            log.warning(f"Senkronizasyon hatası: {e}")
        return False

    def sync_all(self, records: List[Dict]) -> int:
        count = 0
        for r in records:
            if self.sync_record(r):
                count += 1
        return count


# ─────────────────────────────────────────────
# BÖLÜM 7 — Uygulama Durumu
# ─────────────────────────────────────────────

class AppState:
    def __init__(self, simulate: bool):
        self.simulate = simulate
        self.data_mgr  = DataManager()
        self.sec_mgr   = SecurityManager()
        self.map_mgr   = MapManager()
        self.sync_mgr  = SyncManager(ORANGE_PI_URL)
        self.tile_mgr  = TileManager()
        self.buzzer    = BuzzerManager(simulate)
        self.gps       = GPSManager(simulate)
        self.rfid      = RFIDManager(simulate)
        self.fp        = FingerprintManager(simulate)
        self.sessions: Dict[str, bool] = {}   # token → authenticated
        self._prefetch_lock = threading.Lock()
        self._prefetch_status: Dict[str, object] = {
            "running": False,
            "processed": 0,
            "total": 0,
            "downloaded_osm": 0,
            "downloaded_sat": 0,
            "min_zoom": 4,
            "max_zoom": 8,
            "include_sat": False,
            "error": "",
            "started_at": "",
            "finished_at": "",
            "source": "idle",
        }

    def start(self):
        self.gps.start()
        # Türkiye tile'larını arka planda indir (internet varsa)
        threading.Thread(target=self.tile_mgr.prefetch_turkey, kwargs={"min_zoom": 4, "max_zoom": 8, "include_sat": False}, daemon=True).start()
        log.info(f"TAMGA backend başlatıldı (simulate={self.simulate})")

    def stop(self):
        self.gps.stop()
        self.buzzer.cleanup()

    def get_prefetch_status(self) -> Dict:
        with self._prefetch_lock:
            return dict(self._prefetch_status)

    def request_prefetch(self, min_zoom: int, max_zoom: int, include_sat: bool) -> Dict:
        with self._prefetch_lock:
            if self._prefetch_status.get("running"):
                return {"started": False, "status": dict(self._prefetch_status)}
            self._prefetch_status.update({
                "running": True,
                "processed": 0,
                "total": 0,
                "downloaded_osm": 0,
                "downloaded_sat": 0,
                "min_zoom": int(min_zoom),
                "max_zoom": int(max_zoom),
                "include_sat": bool(include_sat),
                "error": "",
                "started_at": datetime.now().isoformat(),
                "finished_at": "",
                "source": "manual",
            })

        def _worker():
            try:
                def _cb(processed, total, d_osm, d_sat, _z):
                    with self._prefetch_lock:
                        self._prefetch_status.update({
                            "processed": processed,
                            "total": total,
                            "downloaded_osm": d_osm,
                            "downloaded_sat": d_sat,
                        })

                result = self.tile_mgr.prefetch_turkey(
                    min_zoom=min_zoom,
                    max_zoom=max_zoom,
                    include_sat=include_sat,
                    progress_cb=_cb,
                )
                with self._prefetch_lock:
                    self._prefetch_status.update(result)
                    self._prefetch_status["running"] = False
                    self._prefetch_status["finished_at"] = datetime.now().isoformat()
            except Exception as e:
                with self._prefetch_lock:
                    self._prefetch_status["running"] = False
                    self._prefetch_status["error"] = str(e)
                    self._prefetch_status["finished_at"] = datetime.now().isoformat()

        threading.Thread(target=_worker, daemon=True).start()
        return {"started": True, "status": self.get_prefetch_status()}


# ─────────────────────────────────────────────
# BÖLÜM 8 — WebSocket Yöneticisi
# ─────────────────────────────────────────────

class WSManager:
    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, msg: Dict):
        payload = json.dumps(msg, ensure_ascii=False)
        async with self._lock:
            dead = set()
            for ws in self._clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            self._clients -= dead


# ─────────────────────────────────────────────
# BÖLÜM 9 — FastAPI Uygulaması
# ─────────────────────────────────────────────

app = FastAPI(title="TAMGA-ADKS API v2", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

state: Optional[AppState] = None
ws_mgr = WSManager()


# ─────────────────────────────────────────────
# BÖLÜM 10 — Pydantic Modelleri
# ─────────────────────────────────────────────

class RecordIn(BaseModel):
    ad_soyad:      str = ""
    cinsiyet:      str = "Bilinmiyor"
    boy:           str = ""
    kilo:          str = ""
    goz:           str = ""
    sac:           str = ""
    triyaj:        str = ""
    bilincl:       str = "Açık"
    dna:           str = "Alınmadı"
    parmak_izi_id: str = ""
    rfid_uid:      str = ""
    gps:           str = ""
    olay_kodu:     str = ""
    ekip:          str = ""
    vucut_bulgulari: str = ""
    eksik_disler:  str = ""
    notlar:        str = ""
    fotograf:      str = ""
    face_photo_b64: str = ""
    transfer_durumu: str = "Sahada"

class LoginIn(BaseModel):
    username: str
    password: str

class AdminLoginIn(BaseModel):
    username: str
    password: str

class ChangePwIn(BaseModel):
    username: str
    current_password: str
    new_password: str

class BuzzerIn(BaseModel):
    pattern: str = "short"

class RFIDWriteIn(BaseModel):
    text: str


class VoiceAliasUpsertIn(BaseModel):
    profile: str = "default"
    heard: str
    canonical: str


class TransferIn(BaseModel):
    status: str


class MapPrefetchIn(BaseModel):
    min_zoom: int = 4
    max_zoom: int = 10
    include_sat: bool = True


# ─────────────────────────────────────────────
# BÖLÜM 11 — REST Endpoint'leri
# ─────────────────────────────────────────────

def _gen_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"TR-{suffix}"


@app.get("/", response_class=HTMLResponse)
async def root():
    if TEMPLATE_FILE.exists():
        return HTMLResponse(TEMPLATE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend bulunamadı</h1><p>templates/tamga.html oluşturun.</p>")


@app.get("/api/health")
async def health():
    gps_data = state.gps.get()
    return {
        "status": "ok",
        "simulate": state.simulate,
        "record_count": len(state.data_mgr.get_all()),
        "gps": gps_data,
        "hardware": {
            "rfid":        not state.rfid.simulate,
            "gps":         not state.gps.simulate,
            "fingerprint": not state.fp.simulate,
            "buzzer":      not state.buzzer.simulate,
        },
        "folium": FOLIUM_OK,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/records")
async def get_records():
    return state.data_mgr.get_all()


@app.post("/api/records")
async def create_record(body: RecordIn):
    conflicts = _detect_record_conflicts(state.data_mgr.get_all(), body)
    record = {
        "KİMLİK NO":       _gen_id(),
        "TARİH/SAAT":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "GPS":             body.gps or f"{state.gps.get()['lat']}, {state.gps.get()['lon']}",
        "PARMAK İZİ ID":   body.parmak_izi_id,
        "RFID UID":        body.rfid_uid,
        "AD SOYAD":        body.ad_soyad,
        "CİNSİYET":        body.cinsiyet,
        "BOY":             body.boy,
        "KİLO":            body.kilo,
        "GÖZ":             body.goz,
        "SAÇ":             body.sac,
        "TRİYAJ":          body.triyaj,
        "BİLİNÇ":          body.bilincl,
        "DNA":             body.dna,
        "OLAY KODU":       body.olay_kodu,
        "EKİP":            body.ekip,
        "VÜCUT BULGULARI": body.vucut_bulgulari,
        "EKSİK DİŞLER":    body.eksik_disler,
        "NOTLAR":          body.notlar,
        "FOTOĞRAF":        body.fotograf,
        "YÜZ FOTOĞRAFI":   body.face_photo_b64,
        "TRANSFER DURUMU": body.transfer_durumu or "Sahada",
        "ÇAKIŞMA UYARISI": " | ".join([f"{c['id']} ({c['reason']})" for c in conflicts]) if conflicts else "",
    }
    state.data_mgr.add(record)
    state.buzzer.beep("success")
    # WebSocket'e bildir
    await ws_mgr.broadcast({"type": "record_added", "data": record})
    # Arka planda Orange Pi senkronizasyonu
    threading.Thread(target=state.sync_mgr.sync_record, args=(record,), daemon=True).start()
    resp = dict(record)
    resp["_conflicts"] = conflicts
    return resp


@app.delete("/api/records/{kimlik_no}")
async def delete_record(kimlik_no: str):
    if state.data_mgr.delete(kimlik_no):
        await ws_mgr.broadcast({"type": "record_deleted", "data": {"id": kimlik_no}})
        return {"success": True}
    raise HTTPException(404, "Kayıt bulunamadı")


@app.get("/api/records/search")
async def search_records(q: str = ""):
    if not q:
        return state.data_mgr.get_all()
    return state.data_mgr.search(q)


@app.get("/api/stats")
async def stats():
    return state.data_mgr.stats()


@app.patch("/api/records/{kimlik_no}/transfer")
async def update_transfer(kimlik_no: str, body: TransferIn):
    status = (body.status or "").strip()[:40]
    if not status:
        raise HTTPException(400, "Transfer durumu boş olamaz")
    rec = state.data_mgr.update_transfer(kimlik_no, status)
    if not rec:
        raise HTTPException(404, "Kayıt bulunamadı")
    await ws_mgr.broadcast({"type": "record_updated", "data": rec})
    return {"success": True, "record": rec}


@app.post("/api/rfid/read")
async def rfid_read():
    result = state.rfid.read()
    if result.get("success"):
        state.buzzer.beep("short")
        await ws_mgr.broadcast({"type": "rfid_detected", "data": result})
    return result


@app.post("/api/rfid/write")
async def rfid_write(body: RFIDWriteIn):
    result = state.rfid.write(body.text)
    if result.get("success"):
        state.buzzer.beep("success")
    return result


@app.post("/api/fingerprint/scan")
async def fp_scan():
    result = state.fp.scan()
    if result.get("success"):
        state.buzzer.beep("short")
        await ws_mgr.broadcast({"type": "fingerprint", "data": result})
    return result


@app.get("/api/gps")
async def get_gps():
    return state.gps.get()


@app.post("/api/buzzer")
async def buzzer(body: BuzzerIn):
    state.buzzer.beep(body.pattern)
    return {"success": True, "pattern": body.pattern}


@app.get("/api/map")
async def get_map():
    records = state.data_mgr.get_all()
    gps = state.gps.get()
    html = state.map_mgr.generate(records, gps["lat"], gps["lon"])
    return HTMLResponse(html)


@app.get("/api/qr/{kimlik_no}")
async def get_qr(kimlik_no: str, request: Request):
    if not QR_OK:
        raise HTTPException(503, "QR modülü bulunamadı (qrcode)")
    safe_id = (kimlik_no or "").strip()
    if not safe_id:
        raise HTTPException(400, "Kimlik no boş olamaz")
    payload = str(request.url_for("qr_view", kimlik_no=safe_id))
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return Response(content=out.getvalue(), media_type="image/png")


@app.get("/qr-view/{kimlik_no}", response_class=HTMLResponse, name="qr_view")
async def qr_view(kimlik_no: str):
    rec = state.data_mgr.get_by_id(kimlik_no)
    if not rec:
        return HTMLResponse(
            "<html><body style='background:#000;color:#fff;font-family:Arial;padding:24px'>"
            "<h2>Kayıt bulunamadı</h2></body></html>",
            status_code=404,
        )

    face = rec.get("YÜZ FOTOĞRAFI", "") or ""
    bw_face = _grayscale_data_url(face) if face else None
    ad = html.escape(rec.get("AD SOYAD", "Bilinmiyor"))
    tri = html.escape(rec.get("TRİYAJ", "-"))
    gps = html.escape(rec.get("GPS", "-"))
    kid = html.escape(rec.get("KİMLİK NO", kimlik_no))
    tms = html.escape(rec.get("TARİH/SAAT", "-"))

    if bw_face:
        img_html = f"<img src='{bw_face}' alt='Siyah beyaz yüz' style='width:100%;max-width:420px;border:2px solid #fff;border-radius:10px;object-fit:cover'>"
    else:
        img_html = (
            "<div style='width:100%;max-width:420px;height:320px;display:flex;align-items:center;justify-content:center;"
            "border:2px dashed #888;border-radius:10px;background:#111;color:#ddd'>Görsel bulunamadı</div>"
        )

    page = f"""
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TAMGA-ADKS QR Görüntü</title>
  <style>
    body{{margin:0;background:#000;color:#fff;font-family:Arial,Helvetica,sans-serif}}
    .w{{max-width:700px;margin:0 auto;padding:18px}}
    .ttl{{font-size:20px;font-weight:700;letter-spacing:1px;margin-bottom:12px}}
    .meta{{line-height:1.6;font-size:14px;color:#e5e7eb;margin-top:12px}}
    .tag{{display:inline-block;border:1px solid #666;padding:2px 8px;border-radius:999px;font-size:12px;margin-top:8px}}
  </style>
</head>
<body>
  <div class="w">
    <div class="ttl">TAMGA-ADKS | Siyah-Beyaz Görsel</div>
    {img_html}
    <div class="meta">
      <div><strong>ID:</strong> {kid}</div>
      <div><strong>Ad Soyad:</strong> {ad}</div>
      <div><strong>Triyaj:</strong> {tri}</div>
      <div><strong>GPS:</strong> {gps}</div>
      <div><strong>Tarih/Saat:</strong> {tms}</div>
      <div class="tag">QR ile erişim</div>
    </div>
  </div>
</body>
</html>
"""
    return HTMLResponse(page)


@app.get("/api/voice-words")
async def get_voice_words():
    path = BASE_DIR / "voice_training_words.json"
    if path.exists():
        return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))
    return JSONResponse({"error": "voice_training_words.json bulunamadı"}, status_code=404)


@app.get("/api/voice-aliases")
async def get_voice_aliases(profile: str = "default"):
    merged = _load_voice_alias_profiles()
    p = _normalize_profile_name(profile)
    if p not in merged:
        p = "default"
    return {
        "success": True,
        "active_profile": p,
        "profiles": sorted(merged.keys()),
        "aliases": merged.get(p, {}),
        "all": merged,
    }


@app.post("/api/voice-aliases")
async def upsert_voice_alias(body: VoiceAliasUpsertIn):
    profile = _normalize_profile_name(body.profile)
    heard = " ".join((body.heard or "").lower().split())
    canonical = " ".join((body.canonical or "").lower().split())
    if not heard or not canonical:
        raise HTTPException(400, "heard ve canonical zorunlu")

    custom = _load_custom_voice_alias_profiles()
    custom.setdefault(profile, {})
    custom[profile][heard] = canonical
    _save_custom_voice_alias_profiles(custom)

    merged = _load_voice_alias_profiles()
    return {
        "success": True,
        "profile": profile,
        "alias_count": len(merged.get(profile, {})),
        "aliases": merged.get(profile, {}),
    }


@app.get("/api/export")
async def export_records():
    """Tüm kayıtları AES-256-GCM şifreli .tae dosyası olarak indir."""
    records = state.data_mgr.get_all()
    export_obj = _build_export_object(records)
    blob = _encrypt_export_blob(export_obj)
    fname = f"tamga_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tae"
    return Response(
        content=blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.get("/api/export/package")
async def export_emergency_package():
    """Acil paket: şifreli .tae + csv + özet pdf (zip)."""
    records = state.data_mgr.get_all()
    stats = state.data_mgr.stats()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    encrypted_blob = _encrypt_export_blob(_build_export_object(records))
    csv_blob = _export_csv_bytes(records)
    pdf_blob = _summary_pdf_bytes(records, stats)

    readme = (
        "TAMGA-ADKS ACIL PAKET\n"
        f"Olusturma: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Toplam Kayit: {len(records)}\n"
        "\n"
        "- *.tae : AES-256-GCM sifreli tum kayitlar\n"
        "- *.csv : tablo/veri analizi icin duz metin export\n"
        "- *.pdf : saha yonetimi icin kisa ozet rapor\n"
    ).encode("utf-8")

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"tamga_export_{stamp}.tae", encrypted_blob)
        zf.writestr(f"tamga_records_{stamp}.csv", csv_blob)
        zf.writestr(f"tamga_ozet_{stamp}.pdf", pdf_blob)
        zf.writestr("README.txt", readme)
    package.seek(0)

    zip_name = f"tamga_acil_paket_{stamp}.zip"
    return Response(
        content=package.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"},
    )


@app.post("/api/auth/login")
async def login(body: LoginIn):
    role = state.sec_mgr.verify_user(body.username, body.password)
    if role:
        return {
            "success": True,
            "role": role,
            "username": body.username,
            "permissions": state.sec_mgr.role_permissions(role),
        }
    return JSONResponse({"success": False, "error": "Kullanıcı adı veya şifre hatalı"}, status_code=401)


@app.post("/api/auth/change-password")
async def change_password_ep(body: ChangePwIn):
    role = state.sec_mgr.verify_user(body.username, body.current_password)
    if role == "admin":
        ok = state.sec_mgr.change_password(body.username, body.new_password)
        return {"success": ok}
    return JSONResponse({"success": False, "error": "Yetki yok veya şifre hatalı"}, status_code=403)


@app.post("/api/sync")
async def sync_all():
    records = state.data_mgr.get_all()
    count = state.sync_mgr.sync_all(records)
    return {"success": True, "synced": count, "total": len(records)}


@app.post("/api/map/prefetch")
async def map_prefetch(body: MapPrefetchIn):
    min_zoom = max(1, min(15, int(body.min_zoom)))
    max_zoom = max(min_zoom, min(18, int(body.max_zoom)))
    include_sat = bool(body.include_sat)
    return state.request_prefetch(min_zoom, max_zoom, include_sat)


@app.get("/api/map/prefetch-status")
async def map_prefetch_status():
    return state.get_prefetch_status()


@app.get("/tiles/{z}/{x}/{y}.png")
async def osm_tile(z: int, x: int, y: int):
    """Yerel önbellekten OSM tile'ı sun; yoksa indir."""
    data = state.tile_mgr.get_osm_tile(z, x, y)
    if not data:
        raise HTTPException(404, "Tile bulunamadı ve indirilemedi")
    return Response(content=data, media_type="image/png")


@app.get("/satellite/{z}/{x}/{y}.png")
async def satellite_tile(z: int, x: int, y: int):
    """Yerel önbellekten uydu tile'ı sun; yoksa Esri'den indir."""
    data = state.tile_mgr.get_sat_tile(z, x, y)
    if not data:
        raise HTTPException(404, "Uydu tile bulunamadı")
    return Response(content=data, media_type="image/png")


# ─────────────────────────────────────────────
# BÖLÜM 12 — WebSocket Endpoint
# ─────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_mgr.connect(ws)
    log.info("WebSocket bağlantısı kuruldu")
    try:
        # İlk durum mesajını gönder
        gps = state.gps.get()
        await ws.send_text(json.dumps({
            "type": "hw_status",
            "data": {
                "rfid":        not state.rfid.simulate,
                "gps":         not state.gps.simulate,
                "fingerprint": not state.fp.simulate,
                "buzzer":      not state.buzzer.simulate,
                "simulate":    state.simulate,
                "lat":         gps["lat"],
                "lon":         gps["lon"],
            }
        }))

        # GPS güncellemelerini düzenli gönder
        async def gps_broadcaster():
            while True:
                await asyncio.sleep(5)
                g = state.gps.get()
                try:
                    await ws.send_text(json.dumps({"type": "gps_update", "data": g}))
                except Exception:
                    break

        asyncio.create_task(gps_broadcaster())

        # İstemciden komut dinle
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            action = msg.get("action", "")

            if action == "rfid_scan":
                result = state.rfid.read()
                await ws.send_text(json.dumps({"type": "rfid_detected", "data": result}))

            elif action == "fp_scan":
                result = state.fp.scan()
                await ws.send_text(json.dumps({"type": "fingerprint", "data": result}))

            elif action == "buzzer":
                state.buzzer.beep(msg.get("pattern", "short"))

            elif action == "get_gps":
                await ws.send_text(json.dumps({"type": "gps_update", "data": state.gps.get()}))

    except WebSocketDisconnect:
        log.info("WebSocket bağlantısı kesildi")
    finally:
        await ws_mgr.disconnect(ws)


# ─────────────────────────────────────────────
# BÖLÜM 13 — Lifecycle & Ana Giriş
# ─────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    if state:
        state.start()


@app.on_event("shutdown")
async def on_shutdown():
    if state:
        state.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TAMGA-ADKS Backend v2.0")
    parser.add_argument("--simulate", action="store_true", help="Donanım simülasyon modu")
    parser.add_argument("--port",     type=int, default=8000, help="Dinlenecek port")
    parser.add_argument("--host",     type=str, default="0.0.0.0", help="Dinlenecek host")
    args = parser.parse_args()

    # GPIO olmayan sistemlerde otomatik simülasyon
    if not args.simulate:
        try:
            import RPi.GPIO  # noqa
        except ImportError:
            log.warning("RPi.GPIO bulunamadı → simülasyon moduna geçiliyor")
            args.simulate = True

    state = AppState(simulate=args.simulate)

    import uvicorn
    mode_str = "SİMÜLASYON" if args.simulate else "DONANIM"
    log.info(f"TAMGA-ADKS Backend v2.0 başlatılıyor [{mode_str} modu]")
    log.info(f"Arayüz: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
