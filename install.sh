#!/bin/bash
#
# Raspberry Pi Audio Player - Installation Script
# Run with: sudo ./install.sh

set -e

echo "========================================="
echo "Raspberry Pi Audio Player Installation"
echo "========================================="

# --- 1. Root check ----------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    echo "Please run using sudo."
    exit 1
fi

# --- 2. Detect non-root user safely ----------------------------------------
if [ -n "$SUDO_USER" ]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER=$(logname 2>/dev/null || whoami)
fi
echo "Installing files for user: $INSTALL_USER"

# --- 3. System update -------------------------------------------------------
echo "Updating package lists..."
set +e
apt-get update
set -e

# --- 4. Install system packages --------------------------------------------
echo "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    vlc \
    libvlc-dev \
    alsa-utils \
    logrotate

# --- 5. Install Python packages --------------------------------------------
echo "Installing Python dependencies..."
pip3 install --break-system-packages --ignore-installed --root-user-action=ignore -r requirements.txt

# --- 6a. Configure API secrets ---------------------------------------------
SECRET_DIR="/var/lib/audio-player"
SECRET_FILE="$SECRET_DIR/secret_config.json"

# ensure directory exists
mkdir -p "$SECRET_DIR"
chown "$INSTALL_USER":"$INSTALL_USER" "$SECRET_DIR"

if [ ! -f "$SECRET_FILE" ]; then
    echo
    echo "=============================="
    echo "Configure API Secret"
    echo "=============================="
    
    # Ask for API base URL and token (visible input)
    read -p "Enter API base URL: " API_BASE_URL
    read -p "Enter API token: " API_TOKEN
    
    # Save secrets to file
    cat <<EOF > "$SECRET_FILE"
{
    "api_base_url": "$API_BASE_URL",
    "auth_token": "$API_TOKEN"
}
EOF

    # Secure the file so only root can read/write
    chmod 600 "$SECRET_FILE"
    echo "API secret saved successfully!"
else
    echo "Secret configuration already exists, skipping input."
fi


# --- 6. Directory setup -----------------------------------------------------
echo "Creating directories..."
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /opt/audio-player
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /var/lib/audio-player/audio_cache
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /var/log/audio-player

# --- 7. Copy main application files ----------------------------------------
echo "Deploying application files..."
cp player.py vlc_player.py api_client.py config_manager.py /opt/audio-player/
chmod +x /opt/audio-player/player.py

# --- 8. Generate systemd service dynamically (run as root) -----------------
echo "Generating systemd service to run as root"
cat > /etc/systemd/system/audio-player.service << EOF
[Unit]
Description=Raspberry Pi Audio Player
After=network.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/audio-player
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /opt/audio-player/player.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=audio-player

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable audio-player.service

# --- 9. Setup log rotation --------------------------------------------------
echo "Configuring log rotation..."
cat > /etc/logrotate.d/audio-player << EOF
/var/log/audio-player/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 $INSTALL_USER $INSTALL_USER
}
EOF

# --- 10. Start service ------------------------------------------------------
echo "Starting audio player service..."
systemctl restart audio-player.service

echo ""
echo "========================================="
echo "Installation Completed Successfully!"
echo "========================================="
echo "Useful commands:"
echo "  sudo systemctl start audio-player"
echo "  sudo systemctl stop audio-player"
echo "  sudo systemctl restart audio-player"
echo "  sudo systemctl status audio-player"
echo "  sudo journalctl -u audio-player -f"
echo ""
echo "To uninstall run: sudo ./uninstall.sh"
echo "========================================="
