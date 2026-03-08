#!/bin/bash
# Raspberry Pi Deployment Script for TAMGA-ADKS

PI_IP="192.168.1.194"
PI_USER="adks"
PI_PASS="adks"
REMOTE_DIR="~/TAMGA-ADKS"

echo "------------------------------------------------"
echo "TAMGA-ADKS Raspberry Pi Deployment"
echo "Target: $PI_USER@$PI_IP"
echo "------------------------------------------------"

# 1. Create directory on Pi
echo "[1/5] Creating directory on Pi..."
sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no $PI_USER@$PI_IP "mkdir -p $REMOTE_DIR/data"

# 2. Configure Pi Interfaces
echo "[2/5] Enabling I2C, SPI, Serial and Setting Brightness..."
sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no $PI_USER@$PI_IP << EOF
    sudo raspi-config nonint do_i2c 0
    sudo raspi-config nonint do_spi 0
    sudo raspi-config nonint do_serial 2
    
    # Enable audio and set volume
    sudo dtparam audio=on
    
    # Set display brightness to 50%
    if [ -f /sys/class/backlight/rpi_backlight/brightness ]; then
        echo 128 | sudo tee /sys/class/backlight/rpi_backlight/brightness
    fi
EOF

# 3. Transfer Files
echo "[3/5] Transferring files and folders..."
sshpass -p "$PI_PASS" scp -o StrictHostKeyChecking=no -r \
    "/home/elliot/Masaüstü/TAMGA-ADKS/templates" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/static" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/import_folium_backup.py" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/orange_pi_search_server.py" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/start_all.sh" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tamga_adks_server.service" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tick.wav" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/success.wav" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/error.wav" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tamga_logo_new.jpg" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tamga_map_new.jpg" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tamga_body_new.jpg" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/tamga_adks.desktop" \
    "/home/elliot/Masaüstü/TAMGA-ADKS/requirements.txt" \
    $PI_USER@$PI_IP:$REMOTE_DIR/

# Rename backup to main file on Pi
sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no $PI_USER@$PI_IP "mv $REMOTE_DIR/import_folium_backup.py $REMOTE_DIR/import_folium.py"

# 4. Install Dependencies
echo "[4/5] Installing dependencies on Pi..."
sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no $PI_USER@$PI_IP << EOF
    sudo apt-get update
    sudo apt-get install -y python3-pip python3-pil python3-pil.imagetk alsa-utils avahi-daemon i2c-tools python3-smbus
    
    # Add user to hardware groups
    sudo usermod -a -G audio,i2c,spi,gpio $PI_USER
    
    # Setup mDNS hostname
    sudo hostnamectl set-hostname tamga
    
    # Install Python requirements
    cd $REMOTE_DIR
    pip3 install -r requirements.txt --break-system-packages
    
    # Setup Autostart
    echo "Configuring services..."
    
    # Server service
    sudo cp $REMOTE_DIR/tamga_adks_server.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable tamga_adks_server.service
    sudo systemctl restart tamga_adks_server.service
    
    # GUI Desktop entry
    mkdir -p ~/.config/autostart
    cp $REMOTE_DIR/tamga_adks.desktop ~/.config/autostart/
    chmod +x $REMOTE_DIR/start_all.sh
EOF

echo "Deployment Complete! Web: http://tamga.local:8080"
