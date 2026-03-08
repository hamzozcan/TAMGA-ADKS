#!/bin/bash
# OPi Deployment Script (Run on RPi)
TARGET_IP="192.168.1.50"
USER="orangepi"
PASS="orangepi"
# Fallback to root/1234 if needed
# USER="root"
# PASS="1234"

echo "Deploying to Orange Pi at $TARGET_IP..."

# 1. Create directory
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$TARGET_IP "mkdir -p ~/TAMGA-ADKS/data/templates"

# 2. Copy Server File
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no /home/adks/TAMGA-ADKS/orange_pi_search_server.py $USER@$TARGET_IP:~/TAMGA-ADKS/

# 3. Copy Templates
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r /home/adks/TAMGA-ADKS/templates/* $USER@$TARGET_IP:~/TAMGA-ADKS/templates/

# 4. Install Dependencies (if internet available, otherwise we hope they are there)
# Assuming apt is configured or pip is available
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$TARGET_IP "sudo apt-get update && sudo apt-get install -y python3-flask python3-requests"

# 5. Start Server
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$TARGET_IP "nohup python3 ~/TAMGA-ADKS/orange_pi_search_server.py > /tmp/server.log 2>&1 &"

echo "Deployment via $USER completed."
