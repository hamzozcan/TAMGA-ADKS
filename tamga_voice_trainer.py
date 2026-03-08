#!/usr/bin/env python3
"""
TAMGA-ADKS Ses Eğitim Scripti
==============================
Sisteme sesli komutları öğretmek için kullanılır.
Kadın sesiyle her komutu söyler, siz tekrar edersiniz.
Kayıtlar voice_samples/ klasörüne kaydedilir.

Kullanım:
  python3 tamga_voice_trainer.py           # Türkçe eğitim
  python3 tamga_voice_trainer.py --lang en # İngilizce eğitim
  python3 tamga_voice_trainer.py --tekrar  # Hepsini yeniden kayıt
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ─── Bağımlılık kontrolü ────────────────────────────────────
try:
    import numpy as np
except ImportError:
    sys.exit("❌ numpy kurulu değil: pip install numpy")

try:
    import sounddevice as sd
except ImportError:
    sys.exit("❌ sounddevice kurulu değil: pip install sounddevice")

try:
    import soundfile as sf
except ImportError:
    sys.exit("❌ soundfile kurulu değil: pip install soundfile")

try:
    from scipy.signal import butter, sosfilt
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False
    print("⚠️  scipy bulunamadı — konuşma filtresi devre dışı")

try:
    import pyttsx3
    TTS_OK = True
except ImportError:
    TTS_OK = False
    print("⚠️  pyttsx3 bulunamadı — TTS devre dışı (metin ekrana yazılacak)")

# ─── Ayarlar ────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
WORDS_FILE  = BASE_DIR / "voice_training_words.json"
SAMPLE_DIR  = BASE_DIR / "voice_samples"
SAMPLE_RATE = 16000
RECORD_SECS = 3.5   # Her komut için kayıt süresi
TEKRAR      = 2     # Her komut kaç kez kaydedilsin

# ─── TTS motoru ─────────────────────────────────────────────
def init_tts(lang="tr"):
    if not TTS_OK:
        return None
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')

    # Kadın sesi bulmaya çalış
    female_keys = ['female', 'zira', 'yelda', 'filiz', 'hazel',
                   'sabina', 'monica', 'anna', 'google']
    lang_code   = 'tr' if lang == 'tr' else 'en'

    female = None
    for v in voices:
        vid = (v.id or '').lower()
        vn  = (v.name or '').lower()
        if lang_code in vid or lang_code in vn:
            if any(k in vn or k in vid for k in female_keys):
                female = v
                break
    # Herhangi bir eşleşen ses
    if not female:
        for v in voices:
            if lang_code in (v.id or '').lower() or lang_code in (v.name or '').lower():
                female = v
                break
    if female:
        engine.setProperty('voice', female.id)
        print(f"🎙️  TTS sesi: {female.name}")
    else:
        print("⚠️  Uygun TTS sesi bulunamadı, varsayılan kullanılıyor")

    engine.setProperty('rate', 155)
    engine.setProperty('volume', 1.0)
    return engine


def say(engine, text):
    """Metni seslendir (TTS yoksa ekrana yaz)."""
    print(f"  🔊 {text}")
    if engine:
        engine.say(text)
        engine.runAndWait()


# ─── Ses filtresi ────────────────────────────────────────────
def bandpass_filter(audio: np.ndarray, lo=300, hi=3400, sr=16000) -> np.ndarray:
    """Konuşma bandı filtreleme (300–3400 Hz). Gürültüyü azaltır."""
    if not SCIPY_OK:
        return audio
    sos = butter(4, [lo, hi], btype='bandpass', fs=sr, output='sos')
    return sosfilt(sos, audio).astype(np.float32)


def spectral_gate(audio: np.ndarray, sr=16000, noise_secs=0.25) -> np.ndarray:
    """Basit gürültü kapısı: ilk N saniyeyi gürültü profili olarak kullan."""
    n_noise = int(noise_secs * sr)
    if len(audio) <= n_noise:
        return audio
    noise_floor = np.abs(audio[:n_noise]).mean() * 2.5
    gated = audio.copy()
    gated[np.abs(gated) < noise_floor] = 0.0
    return gated


# ─── Kayıt ───────────────────────────────────────────────────
def record_audio(secs=RECORD_SECS, sr=SAMPLE_RATE) -> np.ndarray:
    """Mikrofonu kayıt et, konuşma bandı filtresi uygula."""
    frames = int(sr * secs)
    print(f"  ⏺  Kaydediliyor... ({secs:.1f} saniye)")
    audio = sd.rec(frames, samplerate=sr, channels=1, dtype='float32')
    sd.wait()
    audio = audio.flatten()
    audio = bandpass_filter(audio, 300, 3400, sr)
    audio = spectral_gate(audio, sr)
    # Normalize
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.92
    return audio


# ─── Ana akış ────────────────────────────────────────────────
def train(lang="tr", force=False):
    if not WORDS_FILE.exists():
        sys.exit(f"❌ {WORDS_FILE} bulunamadı. Lütfen sistemi çalıştırın.")

    words_data = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    words      = words_data.get(lang, [])
    if not words:
        sys.exit(f"❌ '{lang}' dili için komut bulunamadı.")

    out_dir = SAMPLE_DIR / lang
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = init_tts(lang)

    banner = (
        "╔══════════════════════════════════════════════════╗\n"
        "║      TAMGA-ADKS — SES EĞİTİM MODU               ║\n"
        "║  Afet Sahası Kimlik Sistemi Ses Tanıma Eğitimi   ║\n"
        "╚══════════════════════════════════════════════════╝"
    )
    print("\n" + banner)
    print(f"\n  Dil: {'Türkçe' if lang == 'tr' else 'English'}")
    print(f"  Komut sayısı: {len(words)}")
    print(f"  Her komut için tekrar: {TEKRAR}")
    print(f"  Kayıt süresi: {RECORD_SECS} saniye\n")

    intro = ("Ses eğitimine hoş geldiniz. "
             "Her komuttan sonra mikrofon açılacak. "
             "Komutu net ve yüksek sesle söyleyin." if lang == "tr" else
             "Welcome to voice training. "
             "After each prompt, the microphone will open. "
             "Speak the command clearly and loudly.")
    say(engine, intro)
    time.sleep(0.5)

    completed = 0
    skipped   = 0

    for word in words:
        cmd_id  = word['id']
        phrase  = word['phrase']
        desc    = word.get('desc', '')
        example = word.get('example', phrase)

        print(f"\n  ─── {phrase.upper()} ───")
        if desc:
            print(f"  {desc}")

        for n in range(1, TEKRAR + 1):
            out_path = out_dir / f"{cmd_id}_{n}.wav"

            if out_path.exists() and not force:
                print(f"  ✅ Mevcut: {out_path.name} (atlanıyor, --tekrar ile yeniden kayıt)")
                skipped += 1
                continue

            if lang == "tr":
                prompt = f"Komut: {phrase}. Tekrar {n}. Hazır olunca söyleyin: {example}"
            else:
                prompt = f"Command: {phrase}. Take {n}. Say when ready: {example}"

            say(engine, prompt)
            time.sleep(0.3)

            try:
                audio = record_audio(RECORD_SECS, SAMPLE_RATE)
                sf.write(str(out_path), audio, SAMPLE_RATE, subtype='PCM_16')
                print(f"  💾 Kaydedildi: {out_path.name}")

                confirm = "Kaydedildi." if lang == "tr" else "Recorded."
                say(engine, confirm)
                completed += 1
                time.sleep(0.4)

            except Exception as e:
                print(f"  ❌ Hata: {e}")

    # Özet
    print(f"\n{'─'*52}")
    print(f"  ✅ Tamamlanan kayıt : {completed}")
    print(f"  ⏭️  Atlanan (mevcut): {skipped}")
    print(f"  📁 Kayıt dizini     : {out_dir}")
    print(f"{'─'*52}\n")

    done_msg = (f"Eğitim tamamlandı. {completed} ses kaydedildi. "
                "Sistem artık komutlarınızı daha iyi tanıyacak." if lang == "tr" else
                f"Training complete. {completed} samples recorded. "
                "The system will now recognize your commands better.")
    say(engine, done_msg)


# ─── Giriş noktası ───────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TAMGA-ADKS Ses Eğitim Scripti",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--lang",   choices=["tr", "en"], default="tr",
                        help="Eğitim dili (varsayılan: tr)")
    parser.add_argument("--tekrar", action="store_true",
                        help="Mevcut kayıtları üzerine yaz")
    args = parser.parse_args()

    try:
        train(lang=args.lang, force=args.tekrar)
    except KeyboardInterrupt:
        print("\n\n⚠️  Eğitim kullanıcı tarafından durduruldu.")
        sys.exit(0)
