#!/bin/bash
#
# Raspberry Pi Audio Player with LCD Display - Installation Script
# Run with: sudo ./install.sh

set -e

echo "========================================="
echo "Raspberry Pi Audio Player Installation"
echo "     with 3.5\" LCD Support"
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

# --- 3. Check/Configure LCD -------------------------------------------------
echo ""
echo "========================================="
echo "LCD Display Detection"
echo "========================================="

# Determine config file location
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo "Warning: Cannot find config.txt, LCD may not work"
    CONFIG_FILE=""
fi

LCD_CONFIGURED=false
LCD_DETECTED=false
NEEDS_REBOOT=false

# Check if LCD is already working
if [ -e /dev/fb1 ]; then
    echo "? LCD detected at /dev/fb1"
    LCD_DETECTED=true
    
    # Check resolution
    if command -v fbset &> /dev/null; then
        if fbset -i -fb /dev/fb1 2>/dev/null | grep -q "480x320"; then
            echo "? LCD resolution confirmed: 480x320"
            LCD_CONFIGURED=true
        fi
    fi
    
    # Check if driver is loaded
    if lsmod | grep -q "fb_ili9486\|fbtft"; then
        echo "? LCD driver loaded"
        LCD_CONFIGURED=true
    fi
fi

# If LCD not configured, offer to set it up
if [ "$LCD_CONFIGURED" = false ] && [ -n "$CONFIG_FILE" ]; then
    echo ""
    echo "LCD not detected. Would you like to configure a 3.5\" LCD?"
    read -p "Configure LCD now? (y/N): " SETUP_LCD
    
    if [ "$SETUP_LCD" = "y" ] || [ "$SETUP_LCD" = "Y" ]; then
        echo ""
        echo "Select LCD configuration:"
        echo "1) Auto (recommended) - tft35a, 90° rotation, 48MHz"
        echo "2) Waveshare 3.5\" LCD"
        echo "3) Skip LCD setup"
        echo ""
        read -p "Choice [1-3]: " LCD_CHOICE
        
        case $LCD_CHOICE in
            1|"")
                echo "Configuring LCD with tft35a driver..."
                
                # Backup config
                if [ ! -f "$CONFIG_FILE.backup-audio-player" ]; then
                    cp "$CONFIG_FILE" "$CONFIG_FILE.backup-audio-player"
                    echo "Backup created: $CONFIG_FILE.backup-audio-player"
                fi
                
                # Remove old LCD configs
                sed -i '/dtoverlay=tft35a/d' "$CONFIG_FILE"
                sed -i '/dtoverlay=waveshare35/d' "$CONFIG_FILE"
                
                # Enable SPI
                if ! grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
                    echo "dtparam=spi=on" >> "$CONFIG_FILE"
                fi
                
                # Add LCD config
                echo "" >> "$CONFIG_FILE"
                echo "# 3.5\" LCD Configuration (auto-configured by audio-player installer)" >> "$CONFIG_FILE"
                echo "dtoverlay=tft35a:rotate=90,speed=48000000,fps=30" >> "$CONFIG_FILE"
                
                echo "? LCD configuration added to $CONFIG_FILE"
                NEEDS_REBOOT=true
                ;;
                
            2)
                echo "Configuring Waveshare LCD..."
                
                if [ ! -f "$CONFIG_FILE.backup-audio-player" ]; then
                    cp "$CONFIG_FILE" "$CONFIG_FILE.backup-audio-player"
                fi
                
                sed -i '/dtoverlay=tft35a/d' "$CONFIG_FILE"
                sed -i '/dtoverlay=waveshare35/d' "$CONFIG_FILE"
                
                if ! grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
                    echo "dtparam=spi=on" >> "$CONFIG_FILE"
                fi
                
                echo "" >> "$CONFIG_FILE"
                echo "# Waveshare 3.5\" LCD" >> "$CONFIG_FILE"
                echo "dtoverlay=waveshare35a:rotate=90" >> "$CONFIG_FILE"
                
                echo "? Waveshare LCD configuration added"
                NEEDS_REBOOT=true
                ;;
                
            3|*)
                echo "Skipping LCD setup. You can configure it manually later."
                ;;
        esac
    fi
fi

# --- 4. System update -------------------------------------------------------
echo ""
echo "Updating package lists..."
set +e
apt-get update
set -e

# --- 5. Install system packages --------------------------------------------
echo "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    vlc \
    libvlc-dev \
    alsa-utils \
    logrotate \
    python3-pil \
    fbset

# --- 6. Install Python packages --------------------------------------------
echo "Installing Python dependencies..."
pip3 install --break-system-packages --ignore-installed --root-user-action=ignore \
    python-vlc==3.0.21203 \
    requests==2.32.3 \
    Pillow

# --- 7. Configure API secrets ----------------------------------------------
SECRET_DIR="/var/lib/audio-player"
SECRET_FILE="$SECRET_DIR/secret_config.json"

mkdir -p "$SECRET_DIR"
chown "$INSTALL_USER":"$INSTALL_USER" "$SECRET_DIR"

if [ ! -f "$SECRET_FILE" ]; then
    echo ""
    echo "=============================="
    echo "Configure API Secret"
    echo "=============================="
    
    read -p "Enter API base URL: " API_BASE_URL
    read -p "Enter API token: " API_TOKEN
    
    cat <<EOF > "$SECRET_FILE"
{
    "api_base_url": "$API_BASE_URL",
    "auth_token": "$API_TOKEN"
}
EOF

    chmod 600 "$SECRET_FILE"
    echo "? API secret saved successfully!"
else
    echo "Secret configuration already exists, skipping input."
fi

# --- 8. Directory setup -----------------------------------------------------
echo "Creating directories..."
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /opt/audio-player
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /var/lib/audio-player/audio_cache
install -d -o "$INSTALL_USER" -g "$INSTALL_USER" /var/log/audio-player

# --- 9. Copy application files ---------------------------------------------
echo "Deploying application files..."
cp player.py vlc_player.py api_client.py config_manager.py display_manager.py /opt/audio-player/
chmod +x /opt/audio-player/player.py

# --- 10. Generate systemd service ------------------------------------------
echo "Generating systemd service..."
cat > /etc/systemd/system/audio-player.service << EOF
[Unit]
Description=Raspberry Pi Audio Player with LCD Display
After=network.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/audio-player
Environment="PYTHONUNBUFFERED=1"
Environment="SDL_FBDEV=/dev/fb1"
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

# --- 11. Setup log rotation -------------------------------------------------
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

# --- 12. Start service ------------------------------------------------------
if [ "$NEEDS_REBOOT" = false ]; then
    echo "Starting audio player service..."
    systemctl restart audio-player.service
    
    echo ""
    echo "========================================="
    echo "Installation Completed Successfully!"
    echo "========================================="
    
    if [ "$LCD_CONFIGURED" = true ]; then
        echo "? LCD is working at /dev/fb1"
    fi
    
    echo ""
    echo "Service status:"
    systemctl status audio-player.service --no-pager || true
else
    echo ""
    echo "========================================="
    echo "Installation Complete - REBOOT REQUIRED"
    echo "========================================="
    echo ""
    echo "LCD configuration has been added."
    echo "You must reboot for the LCD to work."
    echo ""
    read -p "Reboot now? (y/N): " DO_REBOOT
    
    if [ "$DO_REBOOT" = "y" ] || [ "$DO_REBOOT" = "Y" ]; then
        echo "Rebooting in 3 seconds..."
        sleep 3
        reboot
    else
        echo ""
        echo "Please reboot manually: sudo reboot"
        echo "After reboot, the service will start automatically."
    fi
fi

echo ""
echo "Useful commands:"
echo "  sudo systemctl start audio-player"
echo "  sudo systemctl stop audio-player"
echo "  sudo systemctl restart audio-player"
echo "  sudo systemctl status audio-player"
echo "  sudo journalctl -u audio-player -f"
echo ""
echo "LCD verification:"
echo "  ls /dev/fb*"
echo "  fbset -i -fb /dev/fb1"
echo ""
echo "To uninstall: sudo ./uninstall.sh"
echo "========================================="