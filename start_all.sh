#!/bin/bash

# TAMGA-ADKS Start Script
# Launches both the Search Server and the Main GUI

echo "🚀 TAMGA-ADKS Baslatiliyor..."
cd "$(dirname "$0")"

# 1. Sunucuyu arka planda baslat
echo "📡 Sunucu baslatiliyor (orange_pi_search_server.py)..."
python3 orange_pi_search_server.py > server.log 2>&1 &
SERVER_PID=$!

# Sunucunun hazir olmasi icin kisa bir sure bekle
sleep 3

# 2. GUI'yi baslat
echo "🖥️ GUI baslatiliyor (import_folium.py)..."
export DISPLAY=:0
python3 import_folium.py

# GUI kapandiginda sunucuyu da kapat
echo "🛑 GUI kapatildi, sunucu durduruluyor..."
kill $SERVER_PID

echo "✅ Tamamlandi."
