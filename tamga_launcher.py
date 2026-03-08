"""
TAMGA-ADKS Launcher v2.0
========================
Masaüstü uygulaması olarak başlatır:
  1. tamga_backend.py'yi arka planda başlatır
  2. PyWebView ile native pencerede arayüzü açar

Çalıştırma:
  python tamga_launcher.py            # Simülasyon (RPi.GPIO yoksa otomatik)
  python tamga_launcher.py --simulate # Zorla simülasyon
  python tamga_launcher.py --port 8080
"""

import argparse
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKEND  = BASE_DIR / "tamga_backend.py"

def wait_for_server(port: int, timeout: int = 20) -> bool:
    import socket
    for _ in range(timeout * 4):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def launch_pywebview(url: str):
    """PyWebView ile native pencere aç."""
    try:
        import webview  # pip install pywebview
        window = webview.create_window(
            title      = "TAMGA-ADKS v2.0 — Acil Durum Kimlik Sistemi",
            url        = url,
            width      = 1280,
            height     = 800,
            min_size   = (900, 600),
            resizable  = True,
            text_select= True,
        )
        webview.start(debug=False)
    except ImportError:
        print("[TAMGA] pywebview bulunamadı → tarayıcı açılıyor")
        print("[TAMGA] pip install pywebview  komutu ile kurabilirsiniz")
        webbrowser.open(url)
        # Tarayıcı açıkken bekle
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description="TAMGA-ADKS Launcher")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--port",     type=int, default=8000)
    args = parser.parse_args()

    # Backend komutunu oluştur
    cmd = [sys.executable, str(BACKEND), "--port", str(args.port)]
    if args.simulate:
        cmd.append("--simulate")

    print(f"[TAMGA] Backend başlatılıyor: {' '.join(cmd)}")
    backend_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Log satırlarını göster
    def log_thread():
        for line in backend_proc.stdout:
            print(f"[BACKEND] {line}", end="")
    threading.Thread(target=log_thread, daemon=True).start()

    # Sunucu hazır olana dek bekle
    url = f"http://127.0.0.1:{args.port}"
    print(f"[TAMGA] Sunucu bekleniyor ({url})…")
    if not wait_for_server(args.port):
        print("[TAMGA] HATA: Backend başlatılamadı!")
        backend_proc.terminate()
        sys.exit(1)

    print(f"[TAMGA] Sunucu hazır → {url}")
    try:
        launch_pywebview(url)
    finally:
        print("[TAMGA] Kapatılıyor…")
        backend_proc.terminate()
        backend_proc.wait(timeout=5)


if __name__ == "__main__":
    main()
