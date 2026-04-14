#!/usr/bin/env python3
"""TAMGA-ADKS icin Raspberry Pi uzerinde 4 pin I2C 16x2 LCD durum gostergesi.

Gorunum:
- 1. satir: TAMGA-ADKS
- 2. satir: toplam ve triyaj sayilari

Alt satir formati:
- T: toplam kayit
- Y: yesil
- S: sari
- K: kirmizi
- H: siyah

Ornek:
- TAMGA-ADKS
- T:27 Y:8 S:10 K:6 H:3

Not:
- 16x2 LCD kucuk oldugu icin ikinci satir otomatik kaydirilir.
- Veriler varsayilan olarak lokal backend'den /api/stats ile okunur.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    from smbus2 import SMBus
except ImportError:
    try:
        from smbus import SMBus  # type: ignore
    except ImportError:
        SMBus = None

# HD44780 komutlari
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_FUNCTIONSET = 0x20
LCD_SETDDRAMADDR = 0x80

LCD_ENTRYLEFT = 0x02
LCD_DISPLAYON = 0x04
LCD_2LINE = 0x08
LCD_4BITMODE = 0x00
LCD_5X8DOTS = 0x00

# PCF8574 backpack bit haritasi
MASK_RS = 0x01
MASK_EN = 0x04
MASK_BL = 0x08

ROW_ADDR = (0x00, 0x40)
TOP_LINE = "TAMGA-ADKS".center(16)
WAITING_LINE = "VERI BEKLENIYOR".center(16)[:16]


class I2C1602:
    def __init__(self, bus: int, address: int, backlight: bool = True) -> None:
        if SMBus is None:
            raise RuntimeError(
                "smbus/smbus2 bulunamadi. Raspberry Pi'de su komutlardan birini kurun: "
                "sudo apt install python3-smbus i2c-tools -y  veya  pip install smbus2"
            )
        self.bus = SMBus(bus)
        self.address = address
        self.backlight = MASK_BL if backlight else 0x00
        self._init_lcd()

    def close(self) -> None:
        try:
            self.bus.close()
        except Exception:
            pass

    def _write_byte(self, value: int) -> None:
        self.bus.write_byte(self.address, value | self.backlight)

    def _pulse(self, value: int) -> None:
        self._write_byte(value | MASK_EN)
        time.sleep(0.0005)
        self._write_byte(value & ~MASK_EN)
        time.sleep(0.0001)

    def _write4(self, nibble: int, mode: int = 0) -> None:
        data = (nibble & 0xF0) | mode
        self._write_byte(data)
        self._pulse(data)

    def _send(self, value: int, mode: int = 0) -> None:
        self._write4(value & 0xF0, mode)
        self._write4((value << 4) & 0xF0, mode)

    def command(self, value: int) -> None:
        self._send(value, 0)

    def write_char(self, value: int) -> None:
        self._send(value, MASK_RS)

    def write_text(self, text: str) -> None:
        for ch in text:
            self.write_char(ord(ch))

    def set_cursor(self, col: int, row: int) -> None:
        self.command(LCD_SETDDRAMADDR | (ROW_ADDR[row] + col))

    def clear(self) -> None:
        self.command(LCD_CLEARDISPLAY)
        time.sleep(0.002)

    def home(self) -> None:
        self.command(LCD_RETURNHOME)
        time.sleep(0.002)

    def _init_lcd(self) -> None:
        time.sleep(0.05)
        self._write4(0x30)
        time.sleep(0.005)
        self._write4(0x30)
        time.sleep(0.005)
        self._write4(0x30)
        time.sleep(0.001)
        self._write4(0x20)

        self.command(LCD_FUNCTIONSET | LCD_4BITMODE | LCD_2LINE | LCD_5X8DOTS)
        self.command(LCD_DISPLAYCONTROL | LCD_DISPLAYON)
        self.clear()
        self.command(LCD_ENTRYMODESET | LCD_ENTRYLEFT)
        self.home()


def fetch_stats(api_url: str, timeout: float) -> dict[str, Any] | None:
    try:
        with urlopen(api_url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def build_stats_text(payload: dict[str, Any] | None) -> str:
    if not payload:
        return WAITING_LINE

    tri = payload.get("triage", {}) if isinstance(payload.get("triage", {}), dict) else {}
    total = int(payload.get("total", 0) or 0)
    green = int(tri.get("YEŞİL", tri.get("YESIL", 0)) or 0)
    yellow = int(tri.get("SARI", 0) or 0)
    red = int(tri.get("KIRMIZI", 0) or 0)
    black = int(tri.get("SİYAH", tri.get("SIYAH", 0)) or 0)
    return f"T:{total} Y:{green} S:{yellow} K:{red} H:{black}"


def marquee_window(text: str, width: int, offset: int) -> str:
    base = (text or "").strip() or "VERI BEKLENIYOR"
    padded = f"{base}   "
    loop_text = padded + padded
    start = offset % len(padded)
    window = loop_text[start : start + width]
    if len(window) < width:
        window = (window + loop_text)[:width]
    return window


def render_status(lcd: I2C1602, api_url: str, refresh_seconds: float, http_timeout: float) -> None:
    last_top = None
    last_bottom = None
    stats_text = WAITING_LINE
    scroll_offset = 0
    last_fetch = 0.0

    while True:
        now = time.monotonic()
        if now - last_fetch >= refresh_seconds:
            payload = fetch_stats(api_url=api_url, timeout=http_timeout)
            new_stats_text = build_stats_text(payload)
            if new_stats_text != stats_text:
                stats_text = new_stats_text
                scroll_offset = 0
            last_fetch = now

        top_line = TOP_LINE
        bottom_line = marquee_window(stats_text, 16, scroll_offset)

        if top_line != last_top:
            lcd.set_cursor(0, 0)
            lcd.write_text(top_line[:16].ljust(16))
            last_top = top_line

        if bottom_line != last_bottom:
            lcd.set_cursor(0, 1)
            lcd.write_text(bottom_line[:16].ljust(16))
            last_bottom = bottom_line

        scroll_offset += 1

        time.sleep(0.35)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raspberry Pi 16x2 I2C LCD durum ekrani")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus numarasi (varsayilan: 1)")
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        default=0x27,
        help="LCD I2C adresi, ornek: 0x27 veya 0x3F",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000/api/stats",
        help="Istatistikler icin backend adresi",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=2.0,
        help="Backend verisini kac saniyede bir yenilesin",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=1.0,
        help="HTTP istek zaman asimi",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lcd: I2C1602 | None = None

    try:
        lcd = I2C1602(bus=args.bus, address=args.address)
        lcd.set_cursor(0, 0)
        lcd.write_text(TOP_LINE[:16].ljust(16))
        lcd.set_cursor(0, 1)
        lcd.write_text("SISTEM ACILIYOR".center(16)[:16])
        render_status(
            lcd,
            api_url=args.api_url,
            refresh_seconds=args.refresh_seconds,
            http_timeout=args.http_timeout,
        )
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1
    finally:
        if lcd is not None:
            try:
                lcd.clear()
                lcd.set_cursor(0, 0)
                lcd.write_text(TOP_LINE[:16].ljust(16))
                lcd.set_cursor(0, 1)
                lcd.write_text("LCD DURDU".center(16)[:16])
                time.sleep(0.5)
                lcd.clear()
            except Exception:
                pass
            lcd.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
