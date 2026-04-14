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
import difflib
import html
import io
import json
import logging
import math
import os
import random
import re
import string
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from google import genai
    GENAI_OK = True
except ImportError:
    genai = None
    GENAI_OK = False

GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY", "").strip()
    or os.environ.get("TAMGA_GEMINI_API_KEY", "").strip()
)
GEMINI_MODEL = os.environ.get("TAMGA_GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

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
MESSAGES_FILE = BASE_DIR / "data" / "messages.json"
MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)

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
MESSAGES_TEMPLATE_FILE = BASE_DIR / "templates" / "messages.html"
AFAD_TEMPLATE_FILE = BASE_DIR / "templates" / "afad.html"
FAMILY_TEMPLATE_FILE = BASE_DIR / "templates" / "yakin.html"
AFAD_NODES_FILE = BASE_DIR / "data" / "afad_nodes.json"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)
VOICE_ALIAS_FILE = BASE_DIR / "voice_aliases.json"
VOICE_ALIAS_PROFILE_FILE = BASE_DIR / "voice_alias_profiles.json"

ORANGE_PI_URL = "http://192.168.1.100:8080"   # Değiştirebilirsiniz
BUZZER_PIN = 18
AFAD_BRIDGE_HEADER = "x-tamga-key"
DEFAULT_NODE_ID = os.environ.get("TAMGA_NODE_ID", "TAMGA-EDGE-001").strip() or "TAMGA-EDGE-001"
DEFAULT_NODE_LABEL = os.environ.get("TAMGA_NODE_LABEL", "TAMGA Saha Düğümü").strip() or "TAMGA Saha Düğümü"


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
        "KAN GRUBU",
        "AYIRT EDİCİ İZ DURUMU",
        "AYIRT EDİCİ İZ AÇIKLAMA",
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


_TR_FAMILY_TRANSLATION = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
})


def _family_norm_text(v: str) -> str:
    return _norm_text(v).translate(_TR_FAMILY_TRANSLATION)


def _family_tokens(v: str) -> Set[str]:
    return {
        tok for tok in re.findall(r"[a-z0-9]+", _family_norm_text(v))
        if tok and len(tok) >= 2
    }


def _parse_gps_coords(value: str) -> Optional[Dict[str, float]]:
    txt = str(value or "").strip().replace(";", ",")
    if "," not in txt:
        return None
    parts = [p.strip() for p in txt.split(",")]
    if len(parts) < 2:
        return None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except Exception:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon}


def _family_match_level(score: float) -> str:
    if score >= 0.82:
        return "high"
    if score >= 0.62:
        return "medium"
    return "low"


def _family_match_label(level: str) -> str:
    return {
        "high": "Yüksek Güven",
        "medium": "Orta Güven",
        "low": "Düşük Güven",
    }.get(level, "Düşük Güven")


def _family_score_record(rec: Dict, query: str) -> Optional[Dict[str, object]]:
    q_raw = (query or "").strip()
    q_norm = _family_norm_text(q_raw)
    if len(q_norm) < 2:
        return None

    record_id = str(rec.get("KİMLİK NO", "") or "")
    name = str(rec.get("AD SOYAD", "Bilinmiyor") or "Bilinmiyor")
    team = str(rec.get("EKİP", "") or "")
    event_code = str(rec.get("OLAY KODU", "") or "")
    notes = str(rec.get("NOTLAR", "") or "")
    triage = str(rec.get("TRİYAJ", "Bilinmiyor") or "Bilinmiyor")
    transfer = str(rec.get("TRANSFER DURUMU", "Sahada") or "Sahada")

    rid_norm = _family_norm_text(record_id)
    name_norm = _family_norm_text(name)
    team_norm = _family_norm_text(team)
    event_norm = _family_norm_text(event_code)
    notes_norm = _family_norm_text(notes)
    triage_norm = _family_norm_text(triage)
    transfer_norm = _family_norm_text(transfer)
    q_tokens = _family_tokens(q_raw)

    score = 0.0
    reasons: List[str] = []

    if q_norm == rid_norm and rid_norm:
        score = 1.0
        reasons.append("kimlik numarası tam eşleşti")
    elif q_norm and q_norm in rid_norm and len(q_norm) >= 4:
        score = max(score, 0.95)
        reasons.append("kimlik numarası benzerliği bulundu")

    if q_norm == name_norm and name_norm:
        score = max(score, 0.96)
        reasons.append("ad soyad tam eşleşti")
    elif q_norm and q_norm in name_norm and len(q_norm) >= 3:
        score = max(score, 0.86)
        reasons.append("ad soyad içinde doğrudan eşleşme bulundu")

    if q_norm and name_norm:
        ratio = difflib.SequenceMatcher(None, q_norm, name_norm).ratio()
        if ratio >= 0.88:
            score = max(score, 0.80 + ((ratio - 0.88) * 1.25))
            reasons.append("ad soyad çok yüksek benzerlik gösteriyor")
        elif ratio >= 0.74:
            score = max(score, 0.54 + ((ratio - 0.74) * 1.25))
            reasons.append("ad soyad benzerlik gösteriyor")

    if q_tokens:
        name_tokens = _family_tokens(name)
        overlap = q_tokens & name_tokens
        if overlap:
            coverage = len(overlap) / max(len(q_tokens), 1)
            score = max(score, 0.44 + coverage * 0.44)
            if coverage >= 0.66:
                reasons.append("isim parçaları büyük ölçüde örtüşüyor")
            else:
                reasons.append("isim parçalarında kısmi örtüşme var")

        if q_tokens & _family_tokens(team):
            score += 0.06
            reasons.append("ekip bilgisiyle ilişkili")
        if q_tokens & _family_tokens(event_code):
            score += 0.08
            reasons.append("olay kodu ile ilişkili")
        if q_tokens & _family_tokens(notes):
            score += 0.04
            reasons.append("notlarda benzer ifade bulundu")
        if q_tokens & _family_tokens(triage):
            score += 0.03
            reasons.append("triyaj bilgisiyle ilişkili")
        if q_tokens & _family_tokens(transfer):
            score += 0.03
            reasons.append("transfer durumuyla ilişkili")

    if q_norm and q_norm in notes_norm and len(q_norm) >= 4:
        score = max(score, 0.40)
        reasons.append("notlarda doğrudan eşleşme bulundu")
    if q_norm and q_norm in event_norm and len(q_norm) >= 3:
        score = max(score, 0.42)
        reasons.append("olay kodunda doğrudan eşleşme bulundu")
    if q_norm and q_norm in team_norm and len(q_norm) >= 3:
        score = max(score, 0.38)
        reasons.append("ekip kodunda doğrudan eşleşme bulundu")
    if q_norm and q_norm in triage_norm:
        score = max(score, 0.34)
        reasons.append("triyaj terimi eşleşti")
    if q_norm and q_norm in transfer_norm:
        score = max(score, 0.34)
        reasons.append("transfer durumu eşleşti")

    score = min(score, 1.0)
    if score < 0.34:
        return None

    gps_point = _parse_gps_coords(rec.get("GPS", ""))
    map_lat: Optional[float] = None
    map_lon: Optional[float] = None
    approx_location = "Konum bilgisi paylaşılmıyor"
    if gps_point:
        map_lat = round(gps_point["lat"], 2)
        map_lon = round(gps_point["lon"], 2)
        approx_location = f"{map_lat:.2f}, {map_lon:.2f} civarı"

    level = _family_match_level(score)
    result = _public_record_view(rec)
    result.update({
        "match_score": int(round(score * 100)),
        "match_level": level,
        "match_label": _family_match_label(level),
        "reasons": list(dict.fromkeys(reasons))[:4],
        "approx_location": approx_location,
        "map_lat": map_lat,
        "map_lon": map_lon,
        "face_available": bool(rec.get("YÜZ FOTOĞRAFI")),
    })
    return result


def _build_family_match_payload(query: str, limit: int = 12) -> Dict[str, object]:
    cleaned_query = (query or "").strip()
    empty_summary = {
        "total_matches": 0,
        "high_confidence": 0,
        "mapped_count": 0,
        "latest_update": "",
        "triage_summary": {},
        "transfer_summary": {},
        "hotspots": [],
    }
    if len(cleaned_query) < 2:
        return {"query": cleaned_query, "matches": [], "summary": empty_summary}

    scored: List[Dict[str, object]] = []
    for rec in state.data_mgr.get_all():
        item = _family_score_record(rec, cleaned_query)
        if item:
            scored.append(item)

    scored.sort(
        key=lambda item: (
            int(item.get("match_score", 0)),
            _parse_timestamp(str(item.get("timestamp", ""))),
        ),
        reverse=True,
    )
    matches = scored[:limit]

    triage_summary: Dict[str, int] = {}
    transfer_summary: Dict[str, int] = {}
    hotspots: Dict[str, Dict[str, object]] = {}
    for item in matches:
        triage_label = str(item.get("triage", "Bilinmiyor") or "Bilinmiyor")
        transfer_label = str(item.get("transfer", "Sahada") or "Sahada")
        triage_summary[triage_label] = triage_summary.get(triage_label, 0) + 1
        transfer_summary[transfer_label] = transfer_summary.get(transfer_label, 0) + 1
        lat = item.get("map_lat")
        lon = item.get("map_lon")
        if lat is None or lon is None:
            continue
        hotspot_key = f"{round(float(lat), 1):.1f},{round(float(lon), 1):.1f}"
        entry = hotspots.setdefault(hotspot_key, {
            "label": f"{round(float(lat), 1):.1f}, {round(float(lon), 1):.1f} civarı",
            "count": 0,
        })
        entry["count"] = int(entry["count"]) + 1

    summary = {
        "total_matches": len(matches),
        "high_confidence": sum(1 for item in matches if item.get("match_level") == "high"),
        "mapped_count": sum(1 for item in matches if item.get("map_lat") is not None and item.get("map_lon") is not None),
        "latest_update": str(matches[0].get("timestamp", "")) if matches else "",
        "triage_summary": triage_summary,
        "transfer_summary": transfer_summary,
        "hotspots": sorted(hotspots.values(), key=lambda item: int(item.get("count", 0)), reverse=True)[:4],
    }
    return {"query": cleaned_query, "matches": matches, "summary": summary}


AI_SCALE_FACTORS = {
    "dusuk": 0.35,
    "orta": 0.7,
    "yuksek": 1.0,
    "cok yuksek": 1.35,
    "yikici": 1.8,
}

CITY_POPULATION_HINTS = {
    "adana": {"label": "Adana", "population": 2270000},
    "adiyaman": {"label": "Adıyaman", "population": 610000},
    "ankara": {"label": "Ankara", "population": 5800000},
    "antalya": {"label": "Antalya", "population": 2700000},
    "aydin": {"label": "Aydın", "population": 1160000},
    "balikesir": {"label": "Balıkesir", "population": 1280000},
    "bursa": {"label": "Bursa", "population": 3230000},
    "canakkale": {"label": "Çanakkale", "population": 570000},
    "denizli": {"label": "Denizli", "population": 1060000},
    "diyarbakir": {"label": "Diyarbakır", "population": 1810000},
    "elazig": {"label": "Elazığ", "population": 600000},
    "erzincan": {"label": "Erzincan", "population": 245000},
    "erzurum": {"label": "Erzurum", "population": 750000},
    "eskisehir": {"label": "Eskişehir", "population": 915000},
    "gaziantep": {"label": "Gaziantep", "population": 2160000},
    "hatay": {"label": "Hatay", "population": 1540000},
    "istanbul": {"label": "İstanbul", "population": 15600000},
    "izmir": {"label": "İzmir", "population": 4480000},
    "kahramanmaras": {"label": "Kahramanmaraş", "population": 1160000},
    "kayseri": {"label": "Kayseri", "population": 1450000},
    "kilis": {"label": "Kilis", "population": 160000},
    "kocaeli": {"label": "Kocaeli", "population": 2120000},
    "konya": {"label": "Konya", "population": 2330000},
    "malatya": {"label": "Malatya", "population": 760000},
    "manisa": {"label": "Manisa", "population": 1470000},
    "mersin": {"label": "Mersin", "population": 1940000},
    "mugla": {"label": "Muğla", "population": 1080000},
    "ordu": {"label": "Ordu", "population": 770000},
    "osmaniye": {"label": "Osmaniye", "population": 560000},
    "rize": {"label": "Rize", "population": 350000},
    "sakarya": {"label": "Sakarya", "population": 1110000},
    "samsun": {"label": "Samsun", "population": 1380000},
    "sanliurfa": {"label": "Şanlıurfa", "population": 2210000},
    "tekirdag": {"label": "Tekirdağ", "population": 1180000},
    "tokat": {"label": "Tokat", "population": 610000},
    "trabzon": {"label": "Trabzon", "population": 830000},
    "van": {"label": "Van", "population": 1140000},
}

AI_DISASTER_PROFILES = [
    {
        "name": "Deprem",
        "keywords": ("deprem",),
        "impact_ratio": 0.18,
        "injury_ratio": 0.024,
        "fatality_ratio": 0.0038,
        "areas": [
            "eski yapı stokunun yoğun olduğu mahalleler",
            "ana ulaşım koridorları ve kavşaklar",
            "hastane ve toplanma alanı çevreleri",
            "sanayi ve depo bölgeleri",
        ],
    },
    {
        "name": "Sel",
        "keywords": ("sel", "su baskini", "tas kin", "taskin"),
        "impact_ratio": 0.12,
        "injury_ratio": 0.01,
        "fatality_ratio": 0.0008,
        "areas": [
            "dere yatakları ve taşkın ovaları",
            "alt geçitler ve düşük kotlu yollar",
            "zemin kat konut ve iş yerleri",
            "köprü ve menfez bağlantıları",
        ],
    },
    {
        "name": "Yangın",
        "keywords": ("yangin", "orman", "wildfire"),
        "impact_ratio": 0.08,
        "injury_ratio": 0.007,
        "fatality_ratio": 0.0005,
        "areas": [
            "orman sınırındaki yerleşimler",
            "rüzgar koridorları ve kuru bitki örtüsü alanları",
            "enerji nakil hattı çevreleri",
            "depo ve akaryakıt alanları",
        ],
    },
    {
        "name": "Heyelan",
        "keywords": ("heyelan", "toprak kaymasi", "landslide"),
        "impact_ratio": 0.04,
        "injury_ratio": 0.008,
        "fatality_ratio": 0.0011,
        "areas": [
            "eğimli yamaç yerleşimleri",
            "vadi tabanına bağlanan yollar",
            "yağış almış gevşek zemin bölgeleri",
            "istinat duvarı riski taşıyan alanlar",
        ],
    },
    {
        "name": "Çığ",
        "keywords": ("cig", "çığ", "avalanche"),
        "impact_ratio": 0.025,
        "injury_ratio": 0.008,
        "fatality_ratio": 0.0014,
        "areas": [
            "yüksek eğimli kar yüklü yamaçlar",
            "dağ yolu ve geçitler",
            "yayla ve dağ evi kümeleri",
            "arama kurtarma erişimi sınırlı bölgeler",
        ],
    },
    {
        "name": "Patlama / Endüstriyel Kaza",
        "keywords": ("patlama", "kimyasal", "endustriyel", "endüstriyel", "kaza", "gaz kacagi", "gaz kaçağı"),
        "impact_ratio": 0.05,
        "injury_ratio": 0.018,
        "fatality_ratio": 0.0022,
        "areas": [
            "sanayi tesisleri ve organize sanayi bölgeleri",
            "depo ve lojistik merkezleri",
            "hakim rüzgar yönündeki yerleşimler",
            "ana tahliye aksları",
        ],
    },
    {
        "name": "Fırtına",
        "keywords": ("firtina", "kasirga", "hortum", "ruzgar", "rüzgar"),
        "impact_ratio": 0.09,
        "injury_ratio": 0.006,
        "fatality_ratio": 0.0004,
        "areas": [
            "kıyı şeridi ve açık alanlar",
            "çatı ve cephe hasarı riski olan yapılar",
            "enerji ve haberleşme hatları",
            "geçici barınma alanları",
        ],
    },
]

AI_DEFAULT_PROFILE = {
    "name": "Genel Afet",
    "impact_ratio": 0.07,
    "injury_ratio": 0.007,
    "fatality_ratio": 0.0007,
    "areas": [
        "yoğun nüfuslu merkez ilçeler",
        "ulaşım ve lojistik düğümleri",
        "kritik altyapı çevresi",
        "geçici toplanma alanları",
    ],
}


def _env_truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_lookup_text(value: str) -> str:
    txt = _ascii_text(str(value or "")).lower()
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return " ".join(txt.split())


def _format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _resolve_city_population(city_name: str) -> Dict[str, object]:
    raw = (city_name or "").strip()
    cleaned = _normalize_lookup_text(raw)
    parts = []
    for piece in re.split(r"[,/|-]+", raw):
        norm = _normalize_lookup_text(piece)
        if norm:
            parts.append(norm)
    if cleaned and cleaned not in parts:
        parts.append(cleaned)

    for candidate in reversed(parts):
        info = CITY_POPULATION_HINTS.get(candidate)
        if info:
            return {**info, "matched": True}

    for key, info in CITY_POPULATION_HINTS.items():
        if key in cleaned:
            return {**info, "matched": True}

    label = raw or "Belirtilmeyen şehir"
    return {"label": label, "population": 650000, "matched": False}


def _pick_disaster_profile(disaster_type: str) -> Dict[str, object]:
    cleaned = _normalize_lookup_text(disaster_type)
    for profile in AI_DISASTER_PROFILES:
        for keyword in profile["keywords"]:
            if _normalize_lookup_text(keyword) in cleaned:
                return profile
    return AI_DEFAULT_PROFILE


def _pick_scale_factor(scale_name: str) -> float:
    cleaned = _normalize_lookup_text(scale_name)
    return AI_SCALE_FACTORS.get(cleaned, 0.85)


def _field_snapshot(stats: Dict, record_count: int) -> Dict[str, int]:
    tri = stats.get("triage", {}) if isinstance(stats, dict) else {}
    return {
        "record_count": int(record_count),
        "red": int(tri.get("KIRMIZI", 0)),
        "yellow": int(tri.get("SARI", 0)),
        "green": int(tri.get("YEŞİL", tri.get("YESIL", 0))),
        "black": int(tri.get("SİYAH", tri.get("SIYAH", 0))),
    }


def _estimate_disaster_summary(city_name: str, disaster_type: str, disaster_scale: str, stats: Dict) -> Dict[str, object]:
    city_info = _resolve_city_population(city_name)
    profile = _pick_disaster_profile(disaster_type)
    scale_factor = _pick_scale_factor(disaster_scale)
    snapshot = _field_snapshot(stats, int(stats.get("total", 0) if isinstance(stats, dict) else 0))
    record_count = snapshot["record_count"]
    critical_count = snapshot["red"] + snapshot["black"]
    pressure_factor = 1.0
    if record_count > 0:
        pressure_factor += min(0.35, (critical_count / max(record_count, 1)) * 0.8)

    population = int(city_info["population"])
    impacted_people = max(50, int(population * float(profile["impact_ratio"]) * scale_factor))
    injury_estimate = max(
        snapshot["red"] * 4 + snapshot["yellow"] * 2,
        int(population * float(profile["injury_ratio"]) * scale_factor * pressure_factor),
    )
    casualty_estimate = max(
        snapshot["black"],
        int(population * float(profile["fatality_ratio"]) * scale_factor * pressure_factor),
    )
    injury_estimate = min(injury_estimate, max(impacted_people, 1))
    casualty_estimate = min(casualty_estimate, max(injury_estimate, impacted_people // 3))
    injury_estimate = min(max(injury_estimate, casualty_estimate * 2), max(impacted_people, 1))

    affected_regions = list(profile["areas"])
    district = city_name.split(",")[0].strip() if "," in city_name else ""
    if district and district.lower() != str(city_info["label"]).lower():
        affected_regions.insert(0, f"{district} ve yakın çevresi")
    affected_regions.insert(0, f"{city_info['label']} merkez")

    operational_notes = [
        f"Sahada doğrulanan {record_count} kayıt var; kritik triyaj sayısı {critical_count}.",
        "Tıbbi tahliye koridoru, toplanma alanı ve hastane kapasitesi eş zamanlı izlenmeli.",
        "Kimliklendirme akışı ile arama-kurtarma ekip listesi senkron tutulmalı.",
    ]
    if critical_count >= 5:
        operational_notes.insert(1, "Kırmızı/siyah triyaj yoğunluğu nedeniyle ileri triyaj ve morg zinciri önceliklendirilmeli.")
    if snapshot["yellow"] > snapshot["red"]:
        operational_notes.append("Gecikmeli vakalar için ikinci dalga sevk planı hazırlanmalı.")
    if not city_info["matched"]:
        operational_notes.append("Şehir nüfusu tahmini genel katsayı ile üretildi; yerel nüfus bilgisiyle doğrulama önerilir.")

    confidence = "yüksek" if city_info["matched"] and record_count >= 25 else "orta" if city_info["matched"] or record_count >= 10 else "düşük"

    return {
        "city": city_name.strip() or str(city_info["label"]),
        "city_label": str(city_info["label"]),
        "disaster_type": disaster_type.strip(),
        "disaster_scale": disaster_scale.strip(),
        "profile_name": str(profile["name"]),
        "population_estimate": population,
        "impacted_people_estimate": impacted_people,
        "casualty_estimate": casualty_estimate,
        "injury_estimate": injury_estimate,
        "affected_regions": affected_regions[:5],
        "operational_notes": operational_notes[:5],
        "confidence": confidence,
        "population_matched": bool(city_info["matched"]),
        "field_snapshot": snapshot,
    }


def _safe_text_to_html(text: str) -> str:
    lines = [html.escape(line) for line in str(text or "").splitlines()]
    return "<br>".join(lines) if lines else ""


def _render_ai_result_html(summary: Dict[str, object], source_label: str, narrative_html: str = "", warnings: Optional[List[str]] = None) -> str:
    warns = warnings or []
    warn_html = ""
    if warns:
        warn_items = "".join(f"<li>{html.escape(w)}</li>" for w in warns)
        warn_html = (
            "<div style='margin:14px 0;padding:12px 14px;border:1px solid rgba(251,191,36,.28);"
            "border-radius:10px;background:rgba(251,191,36,.08)'>"
            "<div style='font-weight:800;color:#fbbf24;margin-bottom:6px'>Uyarılar</div>"
            f"<ul style='margin:0;padding-left:18px;color:#fde68a;line-height:1.5'>{warn_items}</ul>"
            "</div>"
        )

    region_items = "".join(f"<li>{html.escape(item)}</li>" for item in summary.get("affected_regions", []))
    note_items = "".join(f"<li>{html.escape(item)}</li>" for item in summary.get("operational_notes", []))
    snapshot = summary.get("field_snapshot", {})
    snapshot_line = (
        f"{snapshot.get('record_count', 0)} kayıt"
        f" | Kırmızı {snapshot.get('red', 0)}"
        f" | Sarı {snapshot.get('yellow', 0)}"
        f" | Yeşil {snapshot.get('green', 0)}"
        f" | Siyah {snapshot.get('black', 0)}"
    )

    cards = [
        ("Tahmini Nüfus", _format_int(int(summary.get("population_estimate", 0)))),
        ("Tahmini Can Kaybı", _format_int(int(summary.get("casualty_estimate", 0)))),
        ("Tahmini Yaralı", _format_int(int(summary.get("injury_estimate", 0)))),
        ("Etkilenen Nüfus", _format_int(int(summary.get("impacted_people_estimate", 0)))),
    ]
    card_html = "".join(
        "<div style='padding:12px;border:1px solid rgba(56,189,248,.18);border-radius:10px;background:rgba(2,6,14,.55)'>"
        f"<div style='font-size:11px;color:#93c5fd;margin-bottom:4px'>{html.escape(label)}</div>"
        f"<div style='font-size:22px;font-weight:800;color:#f8fafc'>{html.escape(value)}</div>"
        "</div>"
        for label, value in cards
    )

    advisory_block = ""
    if narrative_html:
        advisory_block = (
            "<div style='margin-top:16px;padding:14px;border:1px solid rgba(139,92,246,.24);"
            "border-radius:10px;background:rgba(139,92,246,.08)'>"
            "<div style='font-size:12px;font-weight:800;color:#c4b5fd;margin-bottom:8px'>AI Operasyon Yorumu</div>"
            f"<div style='font-size:13px;line-height:1.7;color:#e5e7eb'>{narrative_html}</div>"
            "</div>"
        )

    return (
        "<div style='display:flex;flex-direction:column;gap:14px'>"
        "<div style='display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
        f"<div><div style='font-size:12px;color:#93c5fd'>Şehir / Senaryo</div><div style='font-size:18px;font-weight:800;color:#f8fafc'>{html.escape(str(summary.get('city', '-')))}</div></div>"
        f"<div style='padding:6px 12px;border-radius:999px;border:1px solid rgba(56,189,248,.25);background:rgba(56,189,248,.08);font-size:11px;font-weight:800;color:#7dd3fc'>{html.escape(source_label.upper())}</div>"
        "</div>"
        f"<div style='font-size:12px;color:#94a3b8'>Afet türü: <b>{html.escape(str(summary.get('profile_name', '-')))}</b> | Ölçek: <b>{html.escape(str(summary.get('disaster_scale', '-')))}</b> | Güven: <b>{html.escape(str(summary.get('confidence', '-')))}</b></div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px'>{card_html}</div>"
        f"{warn_html}"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>"
        "<div style='padding:14px;border:1px solid rgba(56,189,248,.15);border-radius:10px;background:rgba(2,6,14,.42)'>"
        "<div style='font-size:12px;font-weight:800;color:#93c5fd;margin-bottom:8px'>Öncelikli Etki Alanları</div>"
        f"<ul style='margin:0;padding-left:18px;line-height:1.6;color:#e5e7eb'>{region_items}</ul>"
        "</div>"
        "<div style='padding:14px;border:1px solid rgba(56,189,248,.15);border-radius:10px;background:rgba(2,6,14,.42)'>"
        "<div style='font-size:12px;font-weight:800;color:#93c5fd;margin-bottom:8px'>Operasyon Notları</div>"
        f"<ul style='margin:0;padding-left:18px;line-height:1.6;color:#e5e7eb'>{note_items}</ul>"
        "</div>"
        "</div>"
        "<div style='padding:12px 14px;border-radius:10px;background:rgba(15,23,42,.7);border:1px solid rgba(148,163,184,.18)'>"
        "<div style='font-size:11px;font-weight:800;color:#93c5fd;margin-bottom:4px'>Saha Snapshot</div>"
        f"<div style='font-size:12px;color:#cbd5e1'>{html.escape(snapshot_line)}</div>"
        "</div>"
        f"{advisory_block}"
        "</div>"
    )


def _build_gemini_prompt(summary: Dict[str, object]) -> str:
    regions = ", ".join(summary.get("affected_regions", []))
    notes = "; ".join(summary.get("operational_notes", []))
    snapshot = summary.get("field_snapshot", {})
    return (
        "Türkçe yaz. Aşağıdaki afet senaryosu için 5 kısa bölüm halinde operasyon değerlendirmesi üret: "
        "Durum Özeti, Risk Alanları, İlk 6 Saat, İlk 24 Saat, Lojistik Notlar. "
        "Abartısız, net ve karar verdirici ol. HTML veya markdown kullanma; düz metin yaz.\n\n"
        f"Şehir: {summary.get('city')}\n"
        f"Afet Türü: {summary.get('profile_name')}\n"
        f"Afet Ölçeği: {summary.get('disaster_scale')}\n"
        f"Tahmini Nüfus: {summary.get('population_estimate')}\n"
        f"Tahmini Can Kaybı: {summary.get('casualty_estimate')}\n"
        f"Tahmini Yaralı: {summary.get('injury_estimate')}\n"
        f"Etkilenebilecek Alanlar: {regions}\n"
        f"Saha Snapshot: kayıt={snapshot.get('record_count', 0)}, kırmızı={snapshot.get('red', 0)}, "
        f"sarı={snapshot.get('yellow', 0)}, yeşil={snapshot.get('green', 0)}, siyah={snapshot.get('black', 0)}\n"
        f"Operasyon Notları: {notes}"
    )


def _parse_timestamp(value: str) -> float:
    txt = str(value or "").strip()
    if not txt:
        return 0.0
    for parser in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(txt, parser).timestamp()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(txt.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _transfer_summary_from_records(records: List[Dict]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for rec in records:
        status = str(rec.get("TRANSFER DURUMU", "Sahada") or "Sahada").strip() or "Sahada"
        summary[status] = summary.get(status, 0) + 1
    return summary


def _public_record_view(rec: Dict) -> Dict[str, str]:
    return {
        "id": str(rec.get("KİMLİK NO", "")),
        "name": str(rec.get("AD SOYAD", "Bilinmiyor")),
        "triage": str(rec.get("TRİYAJ", "Bilinmiyor")),
        "transfer": str(rec.get("TRANSFER DURUMU", "Sahada")),
        "team": str(rec.get("EKİP", "")),
        "event_code": str(rec.get("OLAY KODU", "")),
        "timestamp": str(rec.get("SON GÜNCELLEME") or rec.get("TARİH/SAAT", "")),
    }


def _message_public_view(msg: Dict) -> Dict[str, str]:
    return {
        "id": str(msg.get("id", "")),
        "timestamp": str(msg.get("timestamp", "")),
        "sender": str(msg.get("sender", "")),
        "person_id": str(msg.get("person_id", "")),
        "person_name": str(msg.get("person_name", "")),
        "message": str(msg.get("message", "")),
        "source": str(msg.get("source", "")),
    }


def _build_local_afad_snapshot(node_id: str = "", node_label: str = "") -> Dict[str, object]:
    records = state.data_mgr.get_all()
    stats = state.data_mgr.stats()
    health_info = {
        "simulate": state.simulate,
        "hardware": {
            "rfid": not state.rfid.simulate,
            "gps": not state.gps.simulate,
            "fingerprint": not state.fp.simulate,
            "buzzer": not state.buzzer.simulate,
        },
    }
    recent_records = sorted(
        [_public_record_view(rec) for rec in records],
        key=lambda item: _parse_timestamp(item.get("timestamp", "")),
        reverse=True,
    )[:25]
    recent_messages = sorted(
        [_message_public_view(m) for m in state.msg_mgr.list(limit=300)],
        key=lambda item: _parse_timestamp(item.get("timestamp", "")),
        reverse=True,
    )[:40]
    family_messages = [m for m in recent_messages if m.get("source") == "family-portal"][:20]
    gps = state.gps.get()
    return {
        "node_id": (node_id or DEFAULT_NODE_ID).strip() or DEFAULT_NODE_ID,
        "node_label": (node_label or DEFAULT_NODE_LABEL).strip() or DEFAULT_NODE_LABEL,
        "pushed_at": datetime.now().isoformat(),
        "health": health_info,
        "stats": stats,
        "gps": gps,
        "transfer_summary": _transfer_summary_from_records(records),
        "recent_records": recent_records,
        "recent_messages": recent_messages,
        "family_messages": family_messages,
    }


def _get_afad_shared_key() -> str:
    env_key = os.environ.get("TAMGA_AFAD_SHARED_KEY", "").strip()
    if env_key:
        return env_key
    if state and getattr(state, "sec_mgr", None):
        cfg_key = state.sec_mgr.data.get("afad_shared_key", "")
        if isinstance(cfg_key, str):
            return cfg_key.strip()
    return ""


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
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        if not self._running:
            return
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


class MessageManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._messages: List[Dict] = []
        self._load()

    def _load(self):
        if not MESSAGES_FILE.exists():
            self._messages = []
            return
        try:
            raw = json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
            self._messages = raw if isinstance(raw, list) else []
        except Exception:
            self._messages = []

    def _save(self):
        try:
            MESSAGES_FILE.write_text(
                json.dumps(self._messages, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"Mesajlar kaydedilemedi: {e}")

    def list(self, person_id: str = "", limit: int = 200) -> List[Dict]:
        with self._lock:
            items = list(self._messages)
        pid = (person_id or "").strip().lower()
        if pid:
            items = [m for m in items if pid in str(m.get("person_id", "")).lower()]
        lim = max(1, min(1000, int(limit)))
        return items[-lim:]

    def add(self, msg: Dict) -> Dict:
        with self._lock:
            self._messages.append(msg)
            if len(self._messages) > 5000:
                self._messages = self._messages[-5000:]
            self._save()
        return msg


class AfadHubManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._nodes: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if not AFAD_NODES_FILE.exists():
            self._nodes = {}
            return
        try:
            raw = json.loads(AFAD_NODES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._nodes = raw
            else:
                self._nodes = {}
        except Exception:
            self._nodes = {}

    def _save(self):
        AFAD_NODES_FILE.parent.mkdir(parents=True, exist_ok=True)
        AFAD_NODES_FILE.write_text(
            json.dumps(self._nodes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ingest(self, snapshot: Dict) -> Dict:
        node_id = str(snapshot.get("node_id", "")).strip()
        if not node_id:
            raise ValueError("node_id zorunlu")
        entry = {
            "node_id": node_id,
            "node_label": str(snapshot.get("node_label", node_id))[:120],
            "updated_at": datetime.now().isoformat(),
            "snapshot": snapshot,
        }
        with self._lock:
            self._nodes[node_id] = entry
            self._save()
        return entry

    def list_nodes(self) -> List[Dict]:
        with self._lock:
            items = [dict(v) for v in self._nodes.values()]
        for item in items:
            updated_at = item.get("updated_at", "")
            age_seconds = max(0, int(time.time() - _parse_timestamp(updated_at)))
            item["age_seconds"] = age_seconds
            item["status"] = "online" if age_seconds <= 120 else "stale" if age_seconds <= 600 else "offline"
        items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return items

    def dashboard(self, local_snapshot: Optional[Dict] = None) -> Dict:
        nodes = self.list_nodes()
        if local_snapshot:
            local_node_id = local_snapshot.get("node_id", DEFAULT_NODE_ID)
            if not any(n.get("node_id") == local_node_id for n in nodes):
                nodes.insert(0, {
                    "node_id": local_node_id,
                    "node_label": local_snapshot.get("node_label", DEFAULT_NODE_LABEL),
                    "updated_at": local_snapshot.get("pushed_at", datetime.now().isoformat()),
                    "age_seconds": 0,
                    "status": "online",
                    "snapshot": local_snapshot,
                })

        summary = {
            "node_count": len(nodes),
            "online_nodes": 0,
            "total_records": 0,
            "critical_total": 0,
            "triage": {"KIRMIZI": 0, "SARI": 0, "YEŞİL": 0, "SİYAH": 0},
            "transfer": {},
        }
        recent_records: List[Dict] = []
        recent_messages: List[Dict] = []
        family_messages: List[Dict] = []
        node_rows: List[Dict] = []

        for node in nodes:
            snapshot = node.get("snapshot", {}) or {}
            stats = snapshot.get("stats", {}) if isinstance(snapshot, dict) else {}
            tri = stats.get("triage", {}) if isinstance(stats, dict) else {}
            transfer_summary = snapshot.get("transfer_summary", {}) if isinstance(snapshot, dict) else {}
            record_total = int(stats.get("total", 0)) if isinstance(stats, dict) else 0
            red = int(tri.get("KIRMIZI", 0))
            black = int(tri.get("SİYAH", tri.get("SIYAH", 0)))
            summary["online_nodes"] += 1 if node.get("status") == "online" else 0
            summary["total_records"] += record_total
            summary["critical_total"] += red + black
            for key in ("KIRMIZI", "SARI", "YEŞİL", "SİYAH"):
                summary["triage"][key] += int(tri.get(key, 0))
            for key, value in transfer_summary.items():
                summary["transfer"][key] = summary["transfer"].get(key, 0) + int(value)

            node_rows.append({
                "node_id": node.get("node_id", ""),
                "node_label": node.get("node_label", ""),
                "updated_at": node.get("updated_at", ""),
                "status": node.get("status", "offline"),
                "age_seconds": node.get("age_seconds", 0),
                "simulate": bool(snapshot.get("health", {}).get("simulate", False)),
                "gps": snapshot.get("gps", {}),
                "record_total": record_total,
                "critical_total": red + black,
                "transfer_summary": transfer_summary,
            })

            for rec in snapshot.get("recent_records", [])[:12]:
                recent_records.append({**rec, "node_id": node.get("node_id", ""), "node_label": node.get("node_label", "")})
            for msg in snapshot.get("recent_messages", [])[:12]:
                recent_messages.append({**msg, "node_id": node.get("node_id", ""), "node_label": node.get("node_label", "")})
            for msg in snapshot.get("family_messages", [])[:12]:
                family_messages.append({**msg, "node_id": node.get("node_id", ""), "node_label": node.get("node_label", "")})

        recent_records.sort(key=lambda item: _parse_timestamp(item.get("timestamp", "")), reverse=True)
        recent_messages.sort(key=lambda item: _parse_timestamp(item.get("timestamp", "")), reverse=True)
        family_messages.sort(key=lambda item: _parse_timestamp(item.get("timestamp", "")), reverse=True)

        return {
            "summary": summary,
            "nodes": node_rows,
            "recent_records": recent_records[:30],
            "recent_messages": recent_messages[:30],
            "family_messages": family_messages[:30],
            "updated_at": datetime.now().isoformat(),
        }


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
        "admin":  {"view": True, "delete": True, "export": True, "package": True, "change_password": True, "transfer_update": True, "bulk_qr": True, "prefetch_map": True, "afad_dashboard": True},
        "doctor": {"view": True, "delete": False, "export": True, "package": True, "change_password": False, "transfer_update": True, "bulk_qr": True, "prefetch_map": True, "afad_dashboard": True},
        "saha":   {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": True, "bulk_qr": True, "prefetch_map": False, "afad_dashboard": False},
        "izleme": {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": False, "bulk_qr": False, "prefetch_map": False, "afad_dashboard": True},
        "viewer": {"view": True, "delete": False, "export": False, "package": False, "change_password": False, "transfer_update": False, "bulk_qr": False, "prefetch_map": False, "afad_dashboard": False},
        "afad":   {"view": True, "delete": False, "export": True, "package": True, "change_password": False, "transfer_update": True, "bulk_qr": False, "prefetch_map": True, "afad_dashboard": True},
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

    def generate_family_public(self, matches: List[Dict], query: str = "", center_lat=39.9, center_lon=32.8) -> str:
        if not FOLIUM_OK:
            return (
                "<html><body style='background:#08111c;color:#eef6ff;font-family:Segoe UI,Arial,sans-serif;"
                "padding:24px'><h3>Harita modülü yüklenemedi</h3><p>Folium kurulu olmadığı için "
                "yakın portalı haritası oluşturulamadı.</p></body></html>"
            )

        visible_points = [m for m in matches if m.get("map_lat") is not None and m.get("map_lon") is not None]
        if visible_points:
            center_lat = float(visible_points[0]["map_lat"])
            center_lon = float(visible_points[0]["map_lon"])

        m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="OpenStreetMap")
        title = html.escape(query or "Yakın Portalı")
        title_html = (
            "<div style=\"position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:999999;"
            "background:rgba(8,17,28,.92);color:#eef6ff;border:1px solid rgba(125,211,252,.25);"
            "padding:10px 14px;border-radius:12px;font-family:Segoe UI,Arial,sans-serif;"
            "box-shadow:0 12px 30px rgba(0,0,0,.25)\">"
            "<div style=\"font-size:11px;font-weight:800;letter-spacing:1px;color:#7dd3fc\">YAKIN EŞLEŞME HARİTASI</div>"
            f"<div style=\"font-size:14px;font-weight:700;margin-top:4px\">Sorgu: {title}</div>"
            "<div style=\"font-size:11px;color:#a0b0c2;margin-top:4px\">Noktalar yaklaşık konumu gösterir.</div>"
            "</div>"
        )
        m.get_root().html.add_child(folium.Element(title_html))

        level_colors = {"high": "red", "medium": "orange", "low": "blue"}
        for item in visible_points:
            color = level_colors.get(str(item.get("match_level", "low")), "blue")
            popup_html = (
                f"<b>{html.escape(str(item.get('name', 'Bilinmiyor')))}</b><br>"
                f"Eşleşme Güveni: {html.escape(str(item.get('match_label', '-')))} "
                f"(%{int(item.get('match_score', 0))})<br>"
                f"Triyaj: {html.escape(str(item.get('triage', '-')))}<br>"
                f"Transfer: {html.escape(str(item.get('transfer', '-')))}<br>"
                f"Olay: {html.escape(str(item.get('event_code', '-')))}<br>"
                f"Yaklaşık konum: {html.escape(str(item.get('approx_location', '-')))}<br>"
                f"Son güncelleme: {html.escape(str(item.get('timestamp', '-')))}"
            )
            folium.CircleMarker(
                location=[float(item["map_lat"]), float(item["map_lon"])],
                radius=9,
                color=color,
                fill=True,
                fill_opacity=0.78,
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=str(item.get("name", "?")),
            ).add_to(m)

        if not visible_points:
            folium.Marker(
                [center_lat, center_lon],
                popup=folium.Popup(
                    "Bu sorgu için paylaşılabilir konum verisi bulunamadı. Eşleşme kartlarını inceleyin.",
                    max_width=260,
                ),
                tooltip="Konum verisi yok",
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
        self._started = False
        self.data_mgr  = DataManager()
        self.msg_mgr   = MessageManager()
        self.afad_hub  = AfadHubManager()
        self.sec_mgr   = SecurityManager()
        self.map_mgr   = MapManager()
        self.sync_mgr  = SyncManager(ORANGE_PI_URL)
        self.tile_mgr  = TileManager()
        self.buzzer    = BuzzerManager(simulate)
        self.gps       = GPSManager(simulate)
        self.rfid      = RFIDManager(simulate)
        self.fp        = FingerprintManager(simulate)
        self.sessions: Dict[str, Dict[str, object]] = {}
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
        if self._started:
            return
        self._started = True
        self.gps.start()
        auto_prefetch = os.environ.get("TAMGA_AUTO_PREFETCH")
        should_prefetch = _env_truthy(auto_prefetch) if auto_prefetch is not None else (not self.simulate)
        if should_prefetch:
            threading.Thread(
                target=self.tile_mgr.prefetch_turkey,
                kwargs={"min_zoom": 4, "max_zoom": 8, "include_sat": False},
                daemon=True,
            ).start()
        log.info(f"TAMGA backend başlatıldı (simulate={self.simulate})")

    def stop(self):
        if not self._started:
            return
        self._started = False
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

state: Optional[AppState] = None
ws_mgr = WSManager()


def _should_simulate(force_simulate: bool = False) -> bool:
    if force_simulate:
        return True
    env = os.environ.get("TAMGA_SIMULATE")
    if env is not None:
        return _env_truthy(env)
    try:
        import RPi.GPIO  # noqa
        return False
    except ImportError:
        return True


def _ensure_state(force_simulate: bool = False) -> AppState:
    global state
    if state is None:
        state = AppState(simulate=_should_simulate(force_simulate))
    return state


def _issue_session_token(username: str, role: str, scope: str = "default", ttl_seconds: int = 8 * 3600) -> str:
    token = f"tok_{scope}_{''.join(random.choices(string.ascii_letters + string.digits, k=40))}"
    expires_at = time.time() + max(300, int(ttl_seconds))
    state.sessions[token] = {
        "username": username,
        "role": role,
        "scope": scope,
        "expires_at": expires_at,
    }
    return token


def _get_session(token: str, scope: Optional[str] = None) -> Optional[Dict[str, object]]:
    raw = state.sessions.get(token)
    if not raw:
        return None
    if float(raw.get("expires_at", 0)) < time.time():
        state.sessions.pop(token, None)
        return None
    if scope and raw.get("scope") != scope:
        return None
    return raw


def _extract_bearer_token(request: Request) -> str:
    auth = (request.headers.get("authorization", "") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-afad-token", "") or "").strip()


def _require_afad_session(request: Request) -> Dict[str, object]:
    token = _extract_bearer_token(request)
    session = _get_session(token, scope="afad")
    if not session:
        raise HTTPException(401, "AFAD oturumu geçersiz")
    perms = state.sec_mgr.role_permissions(str(session.get("role", "")))
    if not perms.get("afad_dashboard"):
        raise HTTPException(403, "AFAD panel yetkisi yok")
    return session

@asynccontextmanager
async def lifespan(application: FastAPI):
    app_state = _ensure_state()
    app_state.start()
    yield
    app_state.stop()

app = FastAPI(title="TAMGA-ADKS API v2", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    kan_grubu:     str = ""
    ayirt_edici_iz_durumu: str = "Yok"
    ayirt_edici_iz_detay: str = ""
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


class MessageIn(BaseModel):
    sender: str = ""
    person_id: str = ""
    person_name: str = ""
    message: str
    source: str = "main"


class FamilyContactIn(BaseModel):
    contact_name: str = ""
    contact_phone: str = ""
    person_query: str = ""
    person_id: str = ""
    message: str


class LoginIn(BaseModel):
    username: str
    password: str


class AfadLoginIn(BaseModel):
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

class AiQueryRequest(BaseModel):
    sehir: str
    afet_turu: str
    afet_olcegi: str



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


class AfadIngestIn(BaseModel):
    node_id: str
    node_label: str = ""
    pushed_at: str = ""
    health: Dict = Field(default_factory=dict)
    stats: Dict = Field(default_factory=dict)
    gps: Dict = Field(default_factory=dict)
    transfer_summary: Dict[str, int] = Field(default_factory=dict)
    recent_records: List[Dict] = Field(default_factory=list)
    recent_messages: List[Dict] = Field(default_factory=list)
    family_messages: List[Dict] = Field(default_factory=list)


# ─────────────────────────────────────────────
# BÖLÜM 11 — REST Endpoint'leri
# ─────────────────────────────────────────────

def _gen_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"TR-{suffix}"


def _gen_msg_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"MSG-{int(time.time() * 1000)}-{suffix}"


@app.get("/", response_class=HTMLResponse)
async def root():
    if TEMPLATE_FILE.exists():
        return HTMLResponse(TEMPLATE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend bulunamadı</h1><p>templates/tamga.html oluşturun.</p>")


@app.get("/messages", response_class=HTMLResponse)
async def messages_ui():
    if MESSAGES_TEMPLATE_FILE.exists():
        return HTMLResponse(MESSAGES_TEMPLATE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Mesajlaşma arayüzü bulunamadı</h1><p>templates/messages.html oluşturun.</p>")


@app.get("/afad", response_class=HTMLResponse)
async def afad_ui():
    if AFAD_TEMPLATE_FILE.exists():
        return HTMLResponse(AFAD_TEMPLATE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AFAD paneli bulunamadı</h1><p>templates/afad.html oluşturun.</p>")


@app.get("/yakin", response_class=HTMLResponse)
@app.get("/aile", response_class=HTMLResponse)
async def family_ui():
    if FAMILY_TEMPLATE_FILE.exists():
        return HTMLResponse(FAMILY_TEMPLATE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Yakın portalı bulunamadı</h1><p>templates/yakin.html oluşturun.</p>")


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
        "KAN GRUBU":       body.kan_grubu,
        "AYIRT EDİCİ İZ DURUMU": body.ayirt_edici_iz_durumu or "Yok",
        "AYIRT EDİCİ İZ AÇIKLAMA": body.ayirt_edici_iz_detay,
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


@app.get("/api/messages")
async def get_messages(person_id: str = "", limit: int = 200):
    return state.msg_mgr.list(person_id=person_id, limit=limit)


@app.get("/api/family/search")
async def family_search(q: str = ""):
    payload = _build_family_match_payload(q, limit=12)
    return payload.get("matches", [])


@app.get("/api/family/match")
async def family_match(q: str = ""):
    return _build_family_match_payload(q, limit=12)


@app.get("/api/family/map")
async def family_map(q: str = ""):
    payload = _build_family_match_payload(q, limit=24)
    gps = state.gps.get()
    html_map = state.map_mgr.generate_family_public(
        list(payload.get("matches", [])),
        query=str(payload.get("query", "")),
        center_lat=gps.get("lat", 39.9),
        center_lon=gps.get("lon", 32.8),
    )
    return HTMLResponse(html_map)


@app.post("/api/family/contact")
async def family_contact(body: FamilyContactIn):
    message_text = (body.message or "").strip()
    if not message_text:
        raise HTTPException(400, "Mesaj boş olamaz")
    contact_name = (body.contact_name or "Yakın").strip()[:60]
    contact_phone = (body.contact_phone or "").strip()[:30]
    person_id = (body.person_id or "").strip()[:64]
    person_query = (body.person_query or "").strip()[:120]
    msg = {
        "id": _gen_msg_id(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sender": f"Yakın: {contact_name}",
        "person_id": person_id,
        "person_name": person_query,
        "message": f"{message_text[:450]}{' | Tel: ' + contact_phone if contact_phone else ''}",
        "source": "family-portal",
    }
    state.msg_mgr.add(msg)
    await ws_mgr.broadcast({"type": "message_added", "data": msg})
    return {"success": True, "message_id": msg["id"]}


@app.post("/api/messages")
async def create_message(body: MessageIn):
    txt = (body.message or "").strip()
    if not txt:
        raise HTTPException(400, "Mesaj boş olamaz")
    msg = {
        "id": _gen_msg_id(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sender": (body.sender or "Operatör").strip()[:60],
        "person_id": (body.person_id or "").strip()[:64],
        "person_name": (body.person_name or "").strip()[:120],
        "message": txt[:500],
        "source": (body.source or "main").strip()[:30],
    }
    state.msg_mgr.add(msg)
    await ws_mgr.broadcast({"type": "message_added", "data": msg})
    return msg


@app.get("/api/afad/local-snapshot")
async def afad_local_snapshot(node_id: str = "", node_label: str = ""):
    return _build_local_afad_snapshot(node_id=node_id, node_label=node_label)


@app.post("/api/afad/auth/login")
async def afad_auth_login(body: AfadLoginIn):
    role = state.sec_mgr.verify_user(body.username, body.password)
    if not role:
        return JSONResponse({"success": False, "error": "Kullanıcı adı veya şifre hatalı"}, status_code=401)
    perms = state.sec_mgr.role_permissions(role)
    if not perms.get("afad_dashboard"):
        return JSONResponse({"success": False, "error": "AFAD panel yetkiniz yok"}, status_code=403)
    token = _issue_session_token(body.username, role, scope="afad", ttl_seconds=12 * 3600)
    return {
        "success": True,
        "token": token,
        "role": role,
        "username": body.username,
        "permissions": perms,
        "expires_in": 12 * 3600,
    }


@app.get("/api/afad/auth/me")
async def afad_auth_me(request: Request):
    session = _require_afad_session(request)
    role = str(session.get("role", "viewer"))
    return {
        "success": True,
        "username": session.get("username", ""),
        "role": role,
        "permissions": state.sec_mgr.role_permissions(role),
    }


@app.post("/api/afad/ingest")
async def afad_ingest(body: AfadIngestIn, request: Request):
    shared_key = _get_afad_shared_key()
    if not shared_key:
        raise HTTPException(503, "TAMGA_AFAD_SHARED_KEY tanımlı değil")
    provided = (
        request.headers.get(AFAD_BRIDGE_HEADER, "")
        or request.headers.get(AFAD_BRIDGE_HEADER.upper(), "")
        or request.headers.get("x-tamga-afad-key", "")
    ).strip()
    if provided != shared_key:
        raise HTTPException(401, "Bridge anahtarı hatalı")
    entry = state.afad_hub.ingest(body.model_dump())
    return {
        "success": True,
        "node_id": entry.get("node_id", ""),
        "updated_at": entry.get("updated_at", ""),
    }


@app.get("/api/afad/dashboard")
async def afad_dashboard(request: Request, include_local: bool = True):
    _require_afad_session(request)
    local_snapshot = _build_local_afad_snapshot() if include_local else None
    return state.afad_hub.dashboard(local_snapshot=local_snapshot)


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

@app.post("/api/ai_query")
async def ai_query(body: AiQueryRequest):
    if not body.sehir.strip():
        raise HTTPException(400, "Şehir adı boş olamaz.")
    if not body.afet_turu.strip():
        raise HTTPException(400, "Afet türü boş olamaz.")
    if not body.afet_olcegi.strip():
        raise HTTPException(400, "Afet ölçeği boş olamaz.")
    stats = state.data_mgr.stats()
    summary = _estimate_disaster_summary(
        city_name=body.sehir,
        disaster_type=body.afet_turu,
        disaster_scale=body.afet_olcegi,
        stats=stats,
    )

    warnings: List[str] = []
    if summary.get("field_snapshot", {}).get("record_count", 0) < 10:
        warnings.append("Sahadan toplanan kayıt sayısı 10'un altında; tahmin güveni sınırlıdır.")
    if not summary.get("population_matched"):
        warnings.append("Şehir nüfusu yerel veri tabanında bulunamadı; genel şehir katsayısı kullanıldı.")

    source = "offline"
    source_label = "Yerel tahmin motoru"
    advisory_html = ""

    if not GENAI_OK:
        warnings.append("google-genai paketi bulunamadığı için çevrimdışı analiz kullanıldı.")
    elif not GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY tanımlı olmadığı için çevrimdışı analiz kullanıldı.")
    else:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=_build_gemini_prompt(summary),
            )
            response_text = (getattr(response, "text", "") or "").strip()
            if response_text:
                source = "gemini"
                source_label = f"Gemini + yerel tahmin ({GEMINI_MODEL})"
                advisory_html = _safe_text_to_html(response_text)
            else:
                warnings.append("Gemini boş yanıt verdi; çevrimdışı analiz kullanıldı.")
        except Exception as e:
            log.warning(f"Gemini analizine erişilemedi, offline moda geçiliyor: {e}")
            warnings.append(f"Gemini erişilemedi; çevrimdışı analiz kullanıldı. ({str(e)[:120]})")

    result_html = _render_ai_result_html(
        summary=summary,
        source_label=source_label,
        narrative_html=advisory_html,
        warnings=warnings,
    )
    return {
        "success": True,
        "source": source,
        "source_label": source_label,
        "summary": summary,
        "warnings": warnings,
        "result": result_html,
        "result_html": result_html,
    }



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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TAMGA-ADKS Backend v2.0")
    parser.add_argument("--simulate", action="store_true", help="Donanım simülasyon modu")
    parser.add_argument("--port",     type=int, default=8000, help="Dinlenecek port")
    parser.add_argument("--host",     type=str, default="0.0.0.0", help="Dinlenecek host")
    args = parser.parse_args()

    args.simulate = _should_simulate(args.simulate)
    if args.simulate:
        log.warning("RPi.GPIO bulunamadı veya simülasyon istendi → simülasyon modu aktif")

    state = _ensure_state(args.simulate)

    import uvicorn
    mode_str = "SİMÜLASYON" if args.simulate else "DONANIM"
    log.info(f"TAMGA-ADKS Backend v2.0 başlatılıyor [{mode_str} modu]")
    log.info(f"Arayüz: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
