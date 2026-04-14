"""
TAMGA-ADKS Launcher v2.0
========================
Geliştirme ortamı ve masaüstü çalıştırıcı.
(Üretim/RPi için: install_rpi.sh → systemd servisini kullanın)

Çalıştırma:
  python tamga_launcher.py                # Otomatik mod (RPi → donanım, diğer → simülasyon)
  python tamga_launcher.py --simulate     # Zorla simülasyon
  python tamga_launcher.py --port 8080    # Farklı port
  python tamga_launcher.py --headless     # Sadece backend, tarayıcı açma
  python tamga_launcher.py --browser      # Sistem tarayıcısını aç (pywebview yerine)
"""

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKEND = BASE_DIR / "tamga_backend.py"
LCD_CLOCK = BASE_DIR / "donanim" / "rpi_i2c_16x2_clock.py"

# ANSI renk kodları
R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
C = "\033[36m"
B = "\033[1m"
N = "\033[0m"


def log(msg, level="info"):
    prefix = {
        "info": f"{C}[•]{N}",
        "ok": f"{G}[✓]{N}",
        "warn": f"{Y}[!]{N}",
        "error": f"{R}[✗]{N}",
    }.get(level, "[?]")
    print(f"{prefix} {msg}")


def is_raspberry_pi() -> bool:
    try:
        model = Path("/proc/device-tree/model").read_text()
        return "raspberry" in model.lower()
    except Exception:
        return False


def has_rpi_gpio() -> bool:
    try:
        import RPi.GPIO  # noqa

        return True
    except ImportError:
        return False


def env_flag(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "evet"}


def wait_for_server(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def stream_process_logs(proc, label: str):
    """Alt süreç log satırlarını ana çıktıya yönlendir."""
    try:
        for line in proc.stdout:
            stripped = line.rstrip()
            if stripped:
                print(f"  [{label}] {stripped}")
    except Exception:
        pass


def start_process(cmd: list[str], label: str) -> subprocess.Popen:
    log(f"{label} başlatılıyor → {' '.join(cmd)}", "info")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(BASE_DIR),
    )
    threading.Thread(target=stream_process_logs, args=(proc, label), daemon=True).start()
    return proc


def build_lcd_clock_cmd(python: str, args: argparse.Namespace, is_rpi: bool, simulate: bool) -> list[str] | None:
    lcd_enabled = args.lcd_clock and env_flag("TAMGA_LCD_CLOCK_ENABLED", True)
    if not lcd_enabled:
        return None
    if not is_rpi or simulate:
        return None
    if not LCD_CLOCK.exists():
        log(f"LCD saat scripti bulunamadı: {LCD_CLOCK}", "warn")
        return None

    address = args.lcd_address or os.environ.get("TAMGA_LCD_I2C_ADDRESS", "0x27")
    bus = str(args.lcd_bus or os.environ.get("TAMGA_LCD_I2C_BUS", "1"))
    use_12h = args.lcd_12h or env_flag("TAMGA_LCD_CLOCK_12H", False)
    blink = env_flag("TAMGA_LCD_CLOCK_BLINK", True)

    cmd = [python, str(LCD_CLOCK), "--address", address, "--bus", bus]
    if use_12h:
        cmd.append("--12h")
    if not blink:
        cmd.append("--no-blink")
    return cmd


def terminate_process(proc: subprocess.Popen | None, label: str, timeout: int = 5) -> None:
    if proc is None or proc.poll() is not None:
        return
    log(f"{label} kapatılıyor...", "info")
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def open_window(url: str, fullscreen: bool = False, use_browser: bool = False):
    """PyWebView penceresi veya sistem tarayıcısı aç."""
    if use_browser:
        log(f"Tarayıcıda açılıyor: {url}", "info")
        webbrowser.open(url)
        log("Kapatmak için Ctrl+C", "info")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    try:
        import webview

        log("PyWebView penceresi açılıyor...", "info")
        webview.create_window(
            title="TAMGA-ADKS v2.0 — Acil Durum Kimlik Sistemi",
            url=url,
            width=1280 if not fullscreen else 1920,
            height=800 if not fullscreen else 1080,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
            fullscreen=fullscreen,
        )
        webview.start(debug=False)
    except ImportError:
        log("pywebview bulunamadı → sistem tarayıcısı kullanılıyor", "warn")
        log("Kurmak için: pip install pywebview", "info")
        open_window(url, fullscreen, use_browser=True)
    except Exception as e:
        log(f"PyWebView hatası: {e} → tarayıcıya geçiliyor", "warn")
        open_window(url, fullscreen, use_browser=True)


def print_banner(port: int, is_rpi: bool, simulate: bool, lcd_clock: bool):
    mode = "DONANIM" if (is_rpi and not simulate) else "SİMÜLASYON"
    mode_color = G if not simulate else Y
    lcd_status = "AKTİF" if lcd_clock else "KAPALI"
    print(f"\n{B}{C}╔══════════════════════════════════════════╗{N}")
    print(f"{B}{C}║   TAMGA-ADKS v2.0 — Launcher            ║{N}")
    print(f"{B}{C}╚══════════════════════════════════════════╝{N}")
    print(f"  Platform   : {'Raspberry Pi' if is_rpi else 'Standart PC/Linux'}")
    print(f"  Mod        : {mode_color}{mode}{N}")
    print(f"  LCD Saat   : {lcd_status}")
    print(f"  Adres      : http://127.0.0.1:{port}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="TAMGA-ADKS Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Üretim ortamı (Raspberry Pi):
  sudo bash install_rpi.sh   # Otomatik kurulum + systemd servisi
  sudo reboot                # Boot'ta otomatik başlar
        """,
    )
    parser.add_argument("--simulate", action="store_true", help="Donanım simülasyon modunu zorla")
    parser.add_argument("--port", type=int, default=8000, help="Backend port numarası (varsayılan: 8000)")
    parser.add_argument("--headless", action="store_true", help="Sadece backend başlat, pencere açma")
    parser.add_argument("--browser", action="store_true", help="PyWebView yerine sistem tarayıcısını kullan")
    parser.add_argument("--fullscreen", action="store_true", help="Tam ekran modunda aç")
    parser.add_argument("--no-lcd-clock", dest="lcd_clock", action="store_false", help="LCD saat sürecini başlatma")
    parser.add_argument("--lcd-address", help="LCD I2C adresi, örnek: 0x27 veya 0x3F")
    parser.add_argument("--lcd-bus", type=int, help="LCD I2C bus numarası, varsayılan 1")
    parser.add_argument("--lcd-12h", action="store_true", help="LCD saati 12 saat formatında göster")
    parser.set_defaults(lcd_clock=True)
    args = parser.parse_args()

    is_rpi = is_raspberry_pi()
    simulate = args.simulate or (not is_rpi and not has_rpi_gpio())

    lcd_cmd = build_lcd_clock_cmd(sys.executable, args, is_rpi=is_rpi, simulate=simulate)
    print_banner(args.port, is_rpi, simulate, lcd_clock=bool(lcd_cmd))

    cmd = [sys.executable, str(BACKEND), "--port", str(args.port), "--host", "127.0.0.1"]
    if simulate:
        cmd.append("--simulate")

    if not BACKEND.exists():
        log(f"tamga_backend.py bulunamadı: {BACKEND}", "error")
        sys.exit(1)

    backend_proc = start_process(cmd, "backend")
    lcd_proc = None
    if lcd_cmd is not None:
        try:
            lcd_proc = start_process(lcd_cmd, "lcd-clock")
        except Exception as exc:
            log(f"LCD saat başlatılamadı: {exc}", "warn")
            lcd_proc = None

    url = f"http://127.0.0.1:{args.port}"
    log(f"Sunucu bekleniyor ({url})...", "info")

    if not wait_for_server(args.port, timeout=30):
        log("HATA: Backend 30 saniyede başlatılamadı!", "error")
        rc = backend_proc.poll()
        if rc is not None:
            log(f"Backend çıkış kodu: {rc}", "error")
        terminate_process(lcd_proc, "lcd-clock", timeout=2)
        terminate_process(backend_proc, "backend")
        sys.exit(1)

    log(f"Backend hazır → {url}", "ok")

    try:
        if args.headless:
            log("Headless mod — pencere açılmıyor. Çıkmak için Ctrl+C.", "info")
            backend_proc.wait()
        else:
            open_window(url, fullscreen=args.fullscreen, use_browser=args.browser)
    except KeyboardInterrupt:
        pass
    finally:
        log("Kapatılıyor...", "info")
        terminate_process(lcd_proc, "lcd-clock", timeout=2)
        terminate_process(backend_proc, "backend")
        log("Tamamlandı.", "ok")


if __name__ == "__main__":
    main()
