#!/usr/bin/env python3
"""
TAMGA-ADKS Şifreli Veri Çözücü
================================
AES-256-GCM ile şifrelenmiş .tae dosyalarını çözer.

Kullanım (CLI):
  python3 tamga_decrypt.py dosya.tae tamga.key
  python3 tamga_decrypt.py dosya.tae tamga.key cikti.json

Kullanım (GUI — argümansız çalıştırın):
  python3 tamga_decrypt.py
"""

import base64
import json
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit("❌ cryptography kurulu değil: pip install cryptography")


# ─── Çözme fonksiyonu ──────────────────────────────────────────
def decrypt_tae(tae_path: str, key_path: str, out_path: str = None) -> dict:
    """
    .tae dosyasını çöz ve dict döndür.
    out_path verilirse JSON dosyasına kaydet.
    """
    key_raw  = Path(key_path).read_bytes().strip()
    key      = base64.b64decode(key_raw)

    tae_raw  = Path(tae_path).read_bytes().strip()
    raw      = base64.b64decode(tae_raw)

    if len(raw) < 13:
        raise ValueError("Dosya çok kısa veya bozuk.")

    aesgcm   = AESGCM(key)
    nonce    = raw[:12]
    ct       = raw[12:]
    plain    = aesgcm.decrypt(nonce, ct, None)
    data     = json.loads(plain.decode("utf-8"))

    if out_path is None:
        out_path = str(Path(tae_path).with_suffix("")) + "_decoded.json"

    Path(out_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return data, out_path


# ─── CLI modu ──────────────────────────────────────────────────
def cli_main():
    tae_path = sys.argv[1]
    key_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) >= 4 else None

    print(f"\n🔓 TAMGA-ADKS Şifre Çözücü")
    print(f"   Dosya : {tae_path}")
    print(f"   Anahtar: {key_path}\n")

    try:
        data, saved = decrypt_tae(tae_path, key_path, out_path)
        records = data.get("records", [])
        print(f"✅ Başarılı!")
        print(f"   Sistem    : {data.get('system', '–')}")
        print(f"   Tarih     : {data.get('timestamp', '–')}")
        print(f"   Kayıt sayısı: {len(records)}")
        print(f"   Çıktı     : {saved}\n")
    except Exception as e:
        print(f"❌ Hata: {e}")
        sys.exit(1)


# ─── GUI modu (Tkinter) ─────────────────────────────────────────
def gui_main():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        sys.exit("❌ tkinter bulunamadı.")

    root = tk.Tk()
    root.title("TAMGA-ADKS — Şifre Çözücü")
    root.geometry("560x400")
    root.configure(bg="#020608")
    root.resizable(False, False)

    # Renkler
    BG   = "#020608"
    BG2  = "#071222"
    ACC  = "#38bdf8"
    TEXT = "#f0f6ff"
    MUTED= "#607898"
    OK   = "#22d3a0"
    ERR  = "#f87171"

    style = ttk.Style()
    style.theme_use("clam")

    # ── Başlık ──────────────────────────────────────
    tk.Label(root, text="🔓  TAMGA-ADKS", font=("Segoe UI", 18, "bold"),
             bg=BG, fg=ACC).pack(pady=(20, 2))
    tk.Label(root, text="Şifreli Veri Çözücü / AES-256-GCM",
             font=("Segoe UI", 10), bg=BG, fg=MUTED).pack(pady=(0, 16))

    frame = tk.Frame(root, bg=BG2, padx=20, pady=16,
                     highlightthickness=1, highlightbackground="#1e3a5f")
    frame.pack(fill=tk.X, padx=20)

    tae_var = tk.StringVar()
    key_var = tk.StringVar(value=str(Path(__file__).parent / "tamga.key"))

    def browse(var, title, ext):
        p = filedialog.askopenfilename(title=title,
            filetypes=[(title, ext), ("Tümü", "*")])
        if p:
            var.set(p)

    # .tae dosyası
    tk.Label(frame, text="Şifreli Dosya (.tae):", font=("Segoe UI", 9, "bold"),
             bg=BG2, fg=TEXT).grid(row=0, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=tae_var, width=38, bg="#0a1a30", fg=TEXT,
             insertbackground=ACC, relief="flat", font=("Segoe UI", 9)
             ).grid(row=0, column=1, padx=6)
    tk.Button(frame, text="Gözat", command=lambda: browse(tae_var, "TAE Dosyası", "*.tae"),
              bg="#0e2236", fg=ACC, relief="flat", padx=8, cursor="hand2"
              ).grid(row=0, column=2)

    # Anahtar dosyası
    tk.Label(frame, text="Anahtar Dosyası (.key):", font=("Segoe UI", 9, "bold"),
             bg=BG2, fg=TEXT).grid(row=1, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=key_var, width=38, bg="#0a1a30", fg=TEXT,
             insertbackground=ACC, relief="flat", font=("Segoe UI", 9)
             ).grid(row=1, column=1, padx=6)
    tk.Button(frame, text="Gözat", command=lambda: browse(key_var, "Anahtar Dosyası", "*.key"),
              bg="#0e2236", fg=ACC, relief="flat", padx=8, cursor="hand2"
              ).grid(row=1, column=2)

    # Sürükle-bırak ipucu
    tk.Label(root, text="💡 Dosyaları yukarıdaki alanlara sürükleyip bırakabilirsiniz.",
             font=("Segoe UI", 8), bg=BG, fg=MUTED).pack(pady=6)

    # Sonuç kutusu
    result_var = tk.StringVar(value="Dosyaları seçin ve çöz butonuna basın.")
    result_lbl = tk.Label(root, textvariable=result_var, wraplength=500,
                          font=("Segoe UI", 9), bg=BG, fg=MUTED, justify="left")
    result_lbl.pack(pady=8, padx=20)

    def do_decrypt():
        tae = tae_var.get().strip()
        key = key_var.get().strip()
        if not tae or not key:
            messagebox.showwarning("Eksik", "Lütfen .tae ve .key dosyalarını seçin.")
            return
        try:
            data, saved = decrypt_tae(tae, key)
            recs = data.get("records", [])
            msg = (f"✅ Başarılı!\n"
                   f"Sistem: {data.get('system','–')} | "
                   f"Tarih: {data.get('timestamp','–')[:16]}\n"
                   f"Kayıt sayısı: {len(recs)}\n"
                   f"Çıktı: {saved}")
            result_var.set(msg)
            result_lbl.configure(fg=OK)
            messagebox.showinfo("Tamamlandı", f"{len(recs)} kayıt çözüldü.\n\n{saved}")
        except Exception as e:
            msg = f"❌ Hata: {e}"
            result_var.set(msg)
            result_lbl.configure(fg=ERR)

    tk.Button(root, text="🔓  ŞİFREYİ ÇÖZ", command=do_decrypt,
              font=("Segoe UI", 12, "bold"), bg=ACC, fg="#020608",
              relief="flat", padx=24, pady=10, cursor="hand2"
              ).pack(pady=(4, 10))

    # Sürükle-bırak desteği (TkinterDnD varsa)
    try:
        root.drop_target_register('DND_Files')
        def on_drop(event):
            paths = root.tk.splitlist(event.data)
            for p in paths:
                if p.endswith('.tae'):
                    tae_var.set(p)
                elif p.endswith('.key'):
                    key_var.set(p)
        root.dnd_bind('<<Drop>>', on_drop)
    except Exception:
        pass  # TkinterDnD opsiyonel

    root.mainloop()


# ─── Giriş noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) >= 3:
        cli_main()
    else:
        gui_main()
