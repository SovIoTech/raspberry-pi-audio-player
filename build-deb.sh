#!/bin/bash
#
# Raspberry Pi Audio Player - DEB Package Builder
# Run with: ./build-deb.sh

set -e

VERSION="1.0.4"
PACKAGE_NAME="audio-player"
ARCH="all"
MAINTAINER="Masuod Ghafoor <masuod.ghafoor85@gmail.com>"
DESCRIPTION="Background audio player service for Raspberry Pi with LCD Display"

BUILD_DIR="build/${PACKAGE_NAME}_${VERSION}"
DEBIAN_DIR="${BUILD_DIR}/DEBIAN"

echo "========================================="
echo "Building DEB Package v${VERSION}"
echo "========================================="

# Clean previous builds
rm -rf build/
mkdir -p "${DEBIAN_DIR}"

# Create directory structure
mkdir -p "${BUILD_DIR}/opt/audio-player"
mkdir -p "${BUILD_DIR}/etc/systemd/system"
mkdir -p "${BUILD_DIR}/etc/logrotate.d"
mkdir -p "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}"
mkdir -p "${BUILD_DIR}/var/lib/audio-player"

# Copy ALL application files
echo "Copying application files..."
cp player.py vlc_player.py api_client.py config_manager.py display_manager.py "${BUILD_DIR}/opt/audio-player/"
chmod +x "${BUILD_DIR}/opt/audio-player/player.py"

# Copy scripts (for manual use if needed)
cp install.sh uninstall.sh "${BUILD_DIR}/opt/audio-player/"
chmod +x "${BUILD_DIR}/opt/audio-player/install.sh"
chmod +x "${BUILD_DIR}/opt/audio-player/uninstall.sh"

# Copy documentation
cp README.md "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/"
cp requirements.txt "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/"

# Create empty secret config template
echo "Creating secret config template..."
cat > "${BUILD_DIR}/var/lib/audio-player/secret_config.json" << 'EOF'
{
    "api_base_url": "",
    "auth_token": ""
}
EOF

# Create empty state/config files
touch "${BUILD_DIR}/var/lib/audio-player/config.json"
touch "${BUILD_DIR}/var/lib/audio-player/state.json"
touch "${BUILD_DIR}/var/lib/audio-player/mac_address.txt"

# Create audio_cache directory
mkdir -p "${BUILD_DIR}/var/lib/audio-player/audio_cache"

# Create systemd service file (updated for LCD display)
echo "Creating systemd service..."
cat > "${BUILD_DIR}/etc/systemd/system/audio-player.service" << 'EOF'
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

# Create logrotate config
echo "Creating logrotate config..."
cat > "${BUILD_DIR}/etc/logrotate.d/audio-player" << 'EOF'
/var/log/audio-player/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 root root
}
EOF

# Create control file (updated dependencies)
echo "Creating control file..."
cat > "${DEBIAN_DIR}/control" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.7), python3-pip, vlc, libvlc-dev, alsa-utils, logrotate, python3-pil, fbset
Recommends: python3-pil
Maintainer: ${MAINTAINER}
Description: ${DESCRIPTION}
 A background audio player service for Raspberry Pi that plays music with ads,
 controlled via WordPress API. Features include:
  * Sequential playback with ad system
  * 3.5" LCD display support (320x480) with auto-configuration
  * Supports multiple LCD types: tft35a, Waveshare, MHS-35 (mhs35-show)
  * Remote control via API commands
  * Heartbeat monitoring and status reporting
  * Network resilience with offline cache
  * Display shows song name, progress, and ad countdown
  * Volume control and playback state management
Homepage: https://github.com/SovIoTech/raspberry-pi-audio-player
EOF

# Create postinst script with integrated LCD setup including MHS-35
echo "Creating postinst script..."
cat > "${DEBIAN_DIR}/postinst" << 'EOF'
#!/bin/bash
set -e

echo "========================================="
echo "Configuring audio-player v${VERSION}"
echo "========================================="

# --- 1. Ensure directories exist ---
mkdir -p /var/lib/audio-player/audio_cache
mkdir -p /var/log/audio-player

# --- 2. Set permissions ---
chown -R root:root /opt/audio-player
chown -R root:root /var/lib/audio-player
chown -R root:root /var/log/audio-player
chmod 755 /opt/audio-player
chmod 755 /var/lib/audio-player
chmod 755 /var/log/audio-player
chmod 755 /opt/audio-player/*.sh
chmod 600 /var/lib/audio-player/secret_config.json || true

# --- 3. Install Python dependencies ---
echo "Installing Python dependencies..."
pip3 install --break-system-packages --ignore-installed --root-user-action=ignore \
    python-vlc==3.0.21203 \
    requests==2.32.3 \
    Pillow || true

# --- 4. Configure API secrets ---
echo ""
echo "=============================="
echo "API Configuration"
echo "=============================="
SECRET_FILE="/var/lib/audio-player/secret_config.json"
if [ -f "$SECRET_FILE" ]; then
    current_config=$(cat "$SECRET_FILE" | tr -d ' \n\r')
    if [ "$current_config" = '{"api_base_url":"","auth_token":""}' ] || [ "$current_config" = '{}' ]; then
        echo "API credentials not configured."
        echo "You can configure them later by editing:"
        echo "  sudo nano $SECRET_FILE"
        echo ""
    else
        echo "? API credentials already configured"
    fi
fi

# --- 5. INTEGRATED LCD SETUP with MHS-35 support ---
echo ""
echo "=============================="
echo "LCD Display Setup"
echo "=============================="

LCD_CONFIGURED=false
NEEDS_REBOOT=false
INSTALLED_MHS35=false

# Determine config file location
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    CONFIG_FILE=""
    echo "Warning: Cannot find config.txt, LCD may not work"
fi

# Check if LCD is already configured
if [ -e /dev/fb1 ]; then
    echo "? LCD detected at /dev/fb1"
    LCD_CONFIGURED=true
    
    if command -v fbset &> /dev/null; then
        if fbset -i -fb /dev/fb1 2>/dev/null | grep -q "480x320"; then
            echo "? LCD resolution confirmed: 480x320"
        fi
    fi
fi

# Check for existing MHS-35 installation
if [ -f "/usr/local/bin/mhs35-show" ] || [ -d "/home/pi/lcd_show" ]; then
    echo "? MHS-35 LCD driver already installed"
    LCD_CONFIGURED=true
    INSTALLED_MHS35=true
fi

# Interactive LCD setup if not configured
if [ "$LCD_CONFIGURED" = false ] && [ -n "$CONFIG_FILE" ]; then
    echo ""
    echo "Would you like to configure a 3.5\" LCD display for the audio player?"
    echo "If you don't have an LCD, you can skip this."
    echo ""
    read -p "Configure LCD now? (y/N): " SETUP_LCD
    
    if [ "$SETUP_LCD" = "y" ] || [ "$SETUP_LCD" = "Y" ]; then
        echo ""
        echo "Select your LCD type:"
        echo "1) Auto (recommended) - tft35a, 90° rotation, 48MHz"
        echo "2) Waveshare 3.5\" LCD"
        echo "3) MHS-35 LCD (uses mhs35-show driver)"
        echo "4) Skip LCD setup"
        echo ""
        read -p "Choice [1-4]: " LCD_CHOICE
        
        case $LCD_CHOICE in
            1|"")
                echo "Configuring LCD with tft35a driver..."
                
                # Backup config
                if [ ! -f "${CONFIG_FILE}.backup-audio-player" ]; then
                    cp "$CONFIG_FILE" "${CONFIG_FILE}.backup-audio-player"
                    echo "Backup created: ${CONFIG_FILE}.backup-audio-player"
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
                echo "# 3.5\" LCD Configuration (auto-configured by audio-player)" >> "$CONFIG_FILE"
                echo "dtoverlay=tft35a:rotate=90,speed=48000000,fps=30" >> "$CONFIG_FILE"
                
                echo "? LCD configuration added to $CONFIG_FILE"
                NEEDS_REBOOT=true
                LCD_CONFIGURED=true
                ;;
                
            2)
                echo "Configuring Waveshare LCD..."
                
                if [ ! -f "${CONFIG_FILE}.backup-audio-player" ]; then
                    cp "$CONFIG_FILE" "${CONFIG_FILE}.backup-audio-player"
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
                LCD_CONFIGURED=true
                ;;
                
            3)
                echo "Configuring MHS-35 LCD..."
                echo "This will install the mhs35-show driver from GitHub."
                echo ""
                read -p "Continue with MHS-35 installation? (y/N): " CONFIRM_MHS
                
                if [ "$CONFIRM_MHS" = "y" ] || [ "$CONFIRM_MHS" = "Y" ]; then
                    # Install MHS-35 driver
                    echo "Installing MHS-35 LCD driver..."
                    
                    # Clone or download mhs35-show
                    if [ ! -d "/home/pi/lcd_show" ]; then
                        echo "Cloning mhs35-show repository..."
                        cd /home/pi
                        git clone https://github.com/kanosakilcdshow/lcd_show.git 2>/dev/null || \
                        git clone https://github.com/waveshare/LCD-show.git lcd_show 2>/dev/null || \
                        echo "Could not clone repository, manual installation may be needed"
                    fi
                    
                    if [ -d "/home/pi/lcd_show" ]; then
                        echo "Setting up MHS-35 driver..."
                        cd /home/pi/lcd_show
                        
                        # Make scripts executable
                        chmod -R 755 .
                        
                        # Run MHS-35 setup
                        if [ -f "MHS35-show" ]; then
                            ./MHS35-show
                            INSTALLED_MHS35=true
                            LCD_CONFIGURED=true
                            NEEDS_REBOOT=true
                            echo "? MHS-35 driver installed and configured"
                        elif [ -f "mhs35-show" ]; then
                            ./mhs35-show
                            INSTALLED_MHS35=true
                            LCD_CONFIGURED=true
                            NEEDS_REBOOT=true
                            echo "? MHS-35 driver installed and configured"
                        else
                            echo "? MHS-35 script not found in lcd_show directory"
                            echo "You may need to manually install the driver"
                        fi
                    else
                        echo "? Could not find or create lcd_show directory"
                        echo "Manual driver installation required:"
                        echo "  cd /home/pi"
                        echo "  git clone https://github.com/kanosakilcdshow/lcd_show.git"
                        echo "  cd lcd_show"
                        echo "  chmod -R 755 ."
                        echo "  ./MHS35-show  # or ./mhs35-show"
                    fi
                else
                    echo "MHS-35 installation cancelled."
                fi
                ;;
                
            4|*)
                echo "Skipping LCD setup."
                ;;
        esac
    fi
fi

# --- 6. System update and package installation ---
echo ""
echo "Updating package lists and installing system dependencies..."
apt-get update || true
apt-get install -y --no-install-recommends \
    python3-pil \
    fbset \
    git \
    wiringpi || true

# --- 7. Systemd setup ---
echo "Setting up systemd service..."
systemctl daemon-reload
systemctl enable audio-player.service

# --- 8. Final instructions ---
echo ""
echo "========================================="
echo "Installation completed!"
echo "========================================="

if [ "$NEEDS_REBOOT" = true ]; then
    echo ""
    echo "IMPORTANT: REBOOT REQUIRED for LCD changes"
    echo "The LCD configuration has been added to your system."
    echo "You must reboot for the LCD to work properly."
    echo ""
    read -p "Reboot now? (y/N): " DO_REBOOT
    
    if [ "$DO_REBOOT" = "y" ] || [ "$DO_REBOOT" = "Y" ]; then
        echo "Rebooting in 5 seconds..."
        sleep 5
        reboot
    else
        echo ""
        echo "Please reboot manually when ready:"
        echo "  sudo reboot"
        echo "After reboot, the service will start automatically."
    fi
else
    echo "Starting audio player service..."
    systemctl restart audio-player.service
    
    echo ""
    echo "Service status:"
    systemctl status audio-player.service --no-pager -l || true
    
    if [ "$LCD_CONFIGURED" = true ]; then
        echo "? LCD is configured and ready"
        if [ "$INSTALLED_MHS35" = true ]; then
            echo "? MHS-35 driver installed at /home/pi/lcd_show"
        fi
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
if [ "$INSTALLED_MHS35" = true ]; then
    echo "MHS-35 LCD commands:"
    echo "  cd /home/pi/lcd_show"
    echo "  ./MHS35-show    # Reconfigure MHS-35"
    echo "  ./LCD-show      # Switch to other LCD"
    echo "  ./LCD-hdmi      # Switch back to HDMI"
    echo ""
fi
echo "To configure API credentials:"
echo "  sudo nano /var/lib/audio-player/secret_config.json"
echo ""
echo "To uninstall:"
echo "  sudo apt-get remove audio-player"
echo "  sudo apt-get purge audio-player  # Remove config files too"
echo "========================================="

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/postinst"

# Create prerm script
echo "Creating prerm script..."
cat > "${DEBIAN_DIR}/prerm" << 'EOF'
#!/bin/bash
set -e

echo "Stopping audio-player service..."
systemctl stop audio-player.service || true
systemctl disable audio-player.service || true

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/prerm"

# Create postrm script with MHS-35 cleanup support
echo "Creating postrm script..."
cat > "${DEBIAN_DIR}/postrm" << 'EOF'
#!/bin/bash
set -e

# Function to remove LCD configuration
remove_lcd_config() {
    local config_file="$1"
    
    if [ ! -f "$config_file" ]; then
        return
    fi
    
    echo "Removing LCD configuration from $config_file..."
    
    # Create a temp file for the cleaned config
    TEMP_FILE=$(mktemp)
    
    # Remove audio-player LCD configuration section
    awk '
    BEGIN { in_audio_player_section = 0 }
    /# 3.5" LCD Configuration \(auto-configured by audio-player\)/ { in_audio_player_section = 1; next }
    /^dtoverlay=(tft35a|waveshare35a)/ && in_audio_player_section { next }
    /^#.*|^$/ && in_audio_player_section { next }
    !/^$/ { in_audio_player_section = 0; print }
    ' "$config_file" | sed '/^$/N;/^\n$/D' > "$TEMP_FILE"
    
    # Also remove specific overlay lines if they exist (even outside our section)
    sed -i '/dtoverlay=tft35a/d' "$TEMP_FILE"
    sed -i '/dtoverlay=waveshare35a/d' "$TEMP_FILE"
    
    # Remove SPI if it was only added for LCD
    if grep -q "^dtparam=spi=on$" "$TEMP_FILE" && ! grep -q "spidev\|spi0" "$TEMP_FILE"; then
        sed -i '/^dtparam=spi=on$/d' "$TEMP_FILE"
    fi
    
    # Replace original config with cleaned version
    mv "$TEMP_FILE" "$config_file"
    echo "? LCD configuration removed"
}

# Function to restore config from backup
restore_config_backup() {
    local backup_file="$1"
    local config_file="$2"
    
    if [ -f "$backup_file" ]; then
        echo "Restoring original configuration from backup..."
        cp "$backup_file" "$config_file"
        rm -f "$backup_file"
        echo "? Original configuration restored"
        return 0
    else
        echo "No backup file found at $backup_file"
        return 1
    fi
}

# Function to handle MHS-35 cleanup
cleanup_mhs35() {
    echo ""
    echo "MHS-35 LCD Driver Cleanup"
    echo "=========================="
    
    if [ -d "/home/pi/lcd_show" ]; then
        echo "MHS-35 driver found at /home/pi/lcd_show"
        echo ""
        echo "What would you like to do?"
        echo "1) Keep MHS-35 driver (for other uses)"
        echo "2) Switch back to HDMI output"
        echo "3) Remove MHS-35 driver completely"
        echo "4) Skip MHS-35 cleanup (default)"
        echo ""
        
        MHS_CHOICE="4"
        if [ -t 0 ]; then
            read -t 30 -p "Choice [1-4] (default: 4): " MHS_CHOICE || true
        fi
        
        case $MHS_CHOICE in
            1)
                echo "Keeping MHS-35 driver."
                ;;
            2)
                echo "Switching back to HDMI output..."
                cd /home/pi/lcd_show 2>/dev/null && ./LCD-hdmi 2>/dev/null || \
                echo "Could not switch to HDMI, you may need to do it manually"
                echo "You can run: cd /home/pi/lcd_show && ./LCD-hdmi"
                ;;
            3)
                echo "Removing MHS-35 driver..."
                # First switch back to HDMI if possible
                cd /home/pi/lcd_show 2>/dev/null && ./LCD-hdmi 2>/dev/null || true
                # Remove the directory
                rm -rf /home/pi/lcd_show 2>/dev/null || true
                echo "? MHS-35 driver removed"
                ;;
            4|"")
                echo "Skipping MHS-35 cleanup."
                ;;
            *)
                echo "Invalid choice. Skipping MHS-35 cleanup."
                ;;
        esac
    fi
}

# Determine config file location
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
    BACKUP_FILE="/boot/firmware/config.txt.backup-audio-player"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
    BACKUP_FILE="/boot/config.txt.backup-audio-player"
else
    CONFIG_FILE=""
    BACKUP_FILE=""
fi

# Interactive LCD cleanup during remove (not purge)
if [ "$1" = "remove" ] || [ "$1" = "upgrade" ]; then
    echo ""
    echo "========================================="
    echo "Audio Player Removal - LCD Configuration"
    echo "========================================="
    
    # Check for MHS-35 installation
    if [ -d "/home/pi/lcd_show" ] || [ -f "/usr/local/bin/mhs35-show" ]; then
        cleanup_mhs35
    fi
    
    if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
        # Check for audio-player LCD configuration
        if grep -q "# 3.5\" LCD Configuration (auto-configured by audio-player)" "$CONFIG_FILE" || \
           grep -q "dtoverlay=tft35a\|dtoverlay=waveshare35a" "$CONFIG_FILE"; then
            
            echo ""
            echo "Traditional LCD Configuration"
            echo "=============================="
            echo "Audio-player LCD configuration detected."
            echo ""
            echo "What would you like to do with the LCD configuration?"
            echo "1) Keep LCD configuration (if you want to use LCD for other purposes)"
            echo "2) Remove only audio-player LCD configuration"
            echo "3) Restore original config from backup"
            echo "4) Skip LCD configuration changes (default)"
            echo ""
            
            # Try to read from stdin, fallback to default
            LCD_CHOICE="4"
            if [ -t 0 ]; then
                # We have a terminal, can read input
                read -t 30 -p "Choice [1-4] (default: 4): " LCD_CHOICE || true
            fi
            
            case $LCD_CHOICE in
                1)
                    echo "Keeping LCD configuration."
                    ;;
                2)
                    remove_lcd_config "$CONFIG_FILE"
                    echo "? LCD configuration removed"
                    echo ""
                    echo "Note: A reboot may be required for changes to take effect."
                    echo "You can reboot with: sudo reboot"
                    ;;
                3)
                    if restore_config_backup "$BACKUP_FILE" "$CONFIG_FILE"; then
                        echo "? Original configuration restored"
                        echo ""
                        echo "Note: A reboot may be required for changes to take effect."
                        echo "You can reboot with: sudo reboot"
                    fi
                    ;;
                4|"")
                    echo "Skipping LCD configuration changes."
                    ;;
                *)
                    echo "Invalid choice. Skipping LCD configuration changes."
                    ;;
            esac
        else
            echo "No audio-player LCD configuration found."
        fi
    fi
fi

# Data removal during purge
if [ "$1" = "purge" ]; then
    echo ""
    echo "========================================="
    echo "Purging Audio Player - Complete Cleanup"
    echo "========================================="
    
    # Handle MHS-35 cleanup during purge
    if [ -d "/home/pi/lcd_show" ] || [ -f "/usr/local/bin/mhs35-show" ]; then
        echo "MHS-35 LCD driver detected."
        echo "Would you like to switch back to HDMI? (y/N): "
        
        SWITCH_HDMI="n"
        if [ -t 0 ]; then
            read -t 30 -p "Switch to HDMI? (y/N): " SWITCH_HDMI || true
        fi
        
        if [ "$SWITCH_HDMI" = "y" ] || [ "$SWITCH_HDMI" = "Y" ]; then
            cd /home/pi/lcd_show 2>/dev/null && ./LCD-hdmi 2>/dev/null || \
            echo "Could not switch to HDMI automatically"
        fi
        
        echo "Would you like to remove the MHS-35 driver? (y/N): "
        REMOVE_MHS="n"
        if [ -t 0 ]; then
            read -t 30 -p "Remove MHS-35 driver? (y/N): " REMOVE_MHS || true
        fi
        
        if [ "$REMOVE_MHS" = "y" ] || [ "$REMOVE_MHS" = "Y" ]; then
            rm -rf /home/pi/lcd_show 2>/dev/null || true
            rm -f /usr/local/bin/mhs35-show 2>/dev/null || true
            echo "? MHS-35 driver removed"
        fi
    fi
    
    # Ask about traditional LCD configuration during purge
    if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
        if grep -q "# 3.5\" LCD Configuration (auto-configured by audio-player)" "$CONFIG_FILE" || \
           grep -q "dtoverlay=tft35a\|dtoverlay=waveshare35a" "$CONFIG_FILE"; then
            
            echo "Traditional LCD configuration detected."
            echo "Would you like to remove the LCD configuration? (y/N): "
            
            REMOVE_LCD="n"
            if [ -t 0 ]; then
                read -t 30 -p "Remove LCD configuration? (y/N): " REMOVE_LCD || true
            fi
            
            if [ "$REMOVE_LCD" = "y" ] || [ "$REMOVE_LCD" = "Y" ]; then
                remove_lcd_config "$CONFIG_FILE"
                echo "? LCD configuration removed"
            else
                echo "Keeping LCD configuration."
            fi
        fi
    fi
    
    # Remove data and logs
    echo "Removing data files..."
    rm -rf /var/lib/audio-player 2>/dev/null || true
    rm -rf /var/log/audio-player 2>/dev/null || true
    
    # Remove backup files
    rm -f /boot/config.txt.backup-audio-player 2>/dev/null || true
    rm -f /boot/firmware/config.txt.backup-audio-player 2>/dev/null || true
    
    echo "? All configuration and data files removed"
fi

# Reload systemd
systemctl daemon-reload || true

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/postrm"

# Create conffiles
echo "Creating conffiles..."
cat > "${DEBIAN_DIR}/conffiles" << 'EOF'
/var/lib/audio-player/secret_config.json
/etc/systemd/system/audio-player.service
/etc/logrotate.d/audio-player
EOF

# Create copyright file
echo "Creating copyright file..."
cat > "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/copyright" << 'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: audio-player
Source: https://github.com/SovIoTech/raspberry-pi-audio-player

Files: *
Copyright: 2024 SovIoTech
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
EOF

# Create changelog (updated version)
echo "Creating changelog..."
cat > "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/changelog" << EOF
audio-player (${VERSION}) stable; urgency=low

  * Version 1.0.4 - MHS-35 LCD Support
  * Added MHS-35 LCD driver installation option
  * Automatically clones and sets up mhs35-show repository
  * Supports chmod -R 755 lcd_show and ./MHS35-show
  * Integrated MHS-35 cleanup during uninstallation
  * Multiple GitHub repository fallbacks for mhs35-show
  * Added wiringpi dependency for MHS-35 compatibility
  * Better handling of different LCD driver types

 -- ${MAINTAINER}  $(date -R)
EOF

gzip -9 "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/changelog"

# Set permissions
find "${BUILD_DIR}" -type f -name "*.json" -exec chmod 600 {} \;
find "${BUILD_DIR}" -type d -exec chmod 755 {} \;

# Build the package
echo "Building DEB package..."
dpkg-deb --build --root-owner-group "${BUILD_DIR}"

# Move to output directory
mkdir -p dist
mv "build/${PACKAGE_NAME}_${VERSION}.deb" "dist/"

# Create checksum
echo "Creating checksum..."
cd dist && sha256sum "${PACKAGE_NAME}_${VERSION}.deb" > "${PACKAGE_NAME}_${VERSION}.deb.sha256" && cd ..

echo ""
echo "========================================="
echo "Build Complete!"
echo "========================================="
echo "Package: dist/${PACKAGE_NAME}_${VERSION}.deb"
echo "Checksum: dist/${PACKAGE_NAME}_${VERSION}.deb.sha256"
echo ""
echo "New in v${VERSION}:"
echo "  ? MHS-35 LCD driver integration"
echo "  ? Automatic mhs35-show repository setup"
echo "  ? chmod -R 755 lcd_show and ./MHS35-show"
echo "  ? Multiple repository fallbacks"
echo "  ? Complete MHS-35 cleanup during uninstall"
echo ""
echo "LCD Installation Options:"
echo "  1) tft35a driver (default)"
echo "  2) Waveshare driver"
echo "  3) MHS-35 driver (mhs35-show)"
echo ""
echo "Installation:"
echo "  sudo dpkg -i dist/audio-player_1.0.4.deb"
echo "  sudo apt-get install -f"
echo ""
echo "During installation, choose option 3 for MHS-35 LCD!"
echo "========================================="