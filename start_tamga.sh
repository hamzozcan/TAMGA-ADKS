#!/bin/bash
# TAMGA-ADKS Otomatik Başlatma Betiği

# Çalışma dizinine git
cd /home/adks/TAMGA-ADKS

# Önceki süreçleri temizle
pkill -f import_folium_backup.py
pkill -f orange_pi_search_server.py

# Ekran değişkenini ayarla (GUI için gerekli)
export DISPLAY=:0

# Varsa sanal ortamı etkinleştir (yoksa normal python3 kullanır)
if [ -d "venv" ]; then
    PYTHON_CMD="./venv/bin/python3"
else
    PYTHON_CMD="python3"
fi

# Sunucuyu arka planda başlat
nohup $PYTHON_CMD orange_pi_search_server.py > /home/adks/TAMGA-ADKS/server_boot.log 2>&1 &

# İstemciyi (Arayüzü) başlat
# Masaüstü ortamının (Wayland/X11) hazır olması için kısa bir bekleme
sleep 15
nohup $PYTHON_CMD import_folium_backup.py > /home/adks/TAMGA-ADKS/client_boot.log 2>&1 &
