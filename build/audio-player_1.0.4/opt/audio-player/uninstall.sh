#!/bin/bash

# Raspberry Pi Audio Player Uninstall Script
# Run with: sudo ./uninstall.sh

set -e

echo "========================================="
echo "Raspberry Pi Audio Player Uninstall"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Function to restore config.txt from backup
restore_config_backup() {
    local backup_file="$1"
    local config_file="$2"
    
    if [ -f "$backup_file" ]; then
        echo "Restoring original configuration from backup..."
        cp "$backup_file" "$config_file"
        rm -f "$backup_file"
        echo "? Original configuration restored: $config_file"
        return 0
    else
        echo "No backup found: $backup_file"
        return 1
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

# Remove LCD driver overlays from config
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    echo ""
    echo "Removing LCD driver configurations..."
    
    # Check if we have audio-player installed LCD config
    if grep -q "# 3.5\" LCD Configuration (auto-configured by audio-player installer)" "$CONFIG_FILE"; then
        echo "Found audio-player LCD configuration, removing..."
        
        # Create a temp file for the cleaned config
        TEMP_FILE=$(mktemp)
        
        # Remove the LCD configuration section
        awk '
        BEGIN { in_audio_player_section = 0 }
        /# 3.5" LCD Configuration \(auto-configured by audio-player installer\)/ { in_audio_player_section = 1; next }
        /^dtoverlay=(tft35a|waveshare35a)/ && in_audio_player_section { next }
        /^#.*|^$/ && in_audio_player_section { next }
        !/^$/ { in_audio_player_section = 0; print }
        ' "$CONFIG_FILE" | sed '/^$/N;/^\n$/D' > "$TEMP_FILE"
        
        # Replace original config with cleaned version
        mv "$TEMP_FILE" "$CONFIG_FILE"
        echo "? LCD configuration removed from $CONFIG_FILE"
        
        # Also remove specific overlay lines if they exist
        sed -i '/dtoverlay=tft35a/d' "$CONFIG_FILE"
        sed -i '/dtoverlay=waveshare35a/d' "$CONFIG_FILE"
        sed -i '/^dtparam=spi=on$/d' "$CONFIG_FILE"
        
        echo "? All LCD-related overlays removed"
    else
        echo "No audio-player specific LCD configuration found"
    fi
    
    # Restore from backup if available
    if [ -f "$BACKUP_FILE" ]; then
        echo ""
        echo "LCD configuration backup found. Would you like to:"
        echo "1) Restore the original configuration (recommended if you didn't have LCD before)"
        echo "2) Keep current configuration"
        echo "3) View backup file contents"
        echo ""
        read -p "Choice [1-3]: " RESTORE_CHOICE
        
        case $RESTORE_CHOICE in
            1)
                restore_config_backup "$BACKUP_FILE" "$CONFIG_FILE"
                ;;
            2)
                echo "Keeping current configuration"
                ;;
            3)
                echo ""
                echo "=== Backup file contents ==="
                cat "$BACKUP_FILE"
                echo "=== End backup file contents ==="
                echo ""
                read -p "Restore this backup? (y/N): " VIEW_CHOICE
                if [[ "$VIEW_CHOICE" =~ ^[Yy]$ ]]; then
                    restore_config_backup "$BACKUP_FILE" "$CONFIG_FILE"
                fi
                ;;
        esac
    fi
fi

# Unload LCD kernel modules if loaded
echo ""
echo "Checking for loaded LCD drivers..."
if lsmod | grep -q "fb_ili9486\|fbtft"; then
    echo "LCD drivers are loaded. They will be unloaded on next reboot."
    echo "To unload immediately, run:"
    echo "  sudo modprobe -r fb_ili9486 fbtft"
fi

# Stop and disable service
echo ""
echo "Stopping audio player service..."
systemctl stop audio-player.service 2>/dev/null || true
systemctl disable audio-player.service 2>/dev/null || true

# Remove service file
echo "Removing service file..."
rm -f /etc/systemd/system/audio-player.service
systemctl daemon-reload

# Remove application files
echo "Removing application files..."
rm -rf /opt/audio-player

# Remove log rotation
echo "Removing log rotation..."
rm -f /etc/logrotate.d/audio-player

# Ask about data removal
echo ""
read -p "Remove configuration and data files (including secrets)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Removing data files..."
    rm -rf /var/lib/audio-player 2>/dev/null || true
    rm -rf /var/log/audio-player 2>/dev/null || true
    echo "? Data files removed"
else
    echo "Data files preserved in:"
    echo "  /var/lib/audio-player"
    echo "  /var/log/audio-player"
fi

# Check for any remaining Python packages from install
echo ""
echo "Checking for installed Python packages..."
if pip3 show python-vlc 2>/dev/null | grep -q "Version:"; then
    echo "Python packages installed by audio-player:"
    pip3 list | grep -E "(python-vlc|requests|Pillow)" || true
    echo ""
    read -p "Remove these Python packages? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing Python packages..."
        pip3 uninstall -y python-vlc requests Pillow 2>/dev/null || true
        echo "? Python packages removed"
    fi
fi

# Final message
echo ""
echo "========================================="
echo "Uninstall completed!"
echo "========================================="
echo ""
echo "Important:"
echo "1. If LCD was configured, a REBOOT may be required for changes to take effect"
echo "2. Any system packages installed (VLC, alsa-utils, etc.) were NOT removed"
echo "3. To remove system packages, run:"
echo "   sudo apt-get remove vlc libvlc-dev alsa-utils python3-pil fbset"
echo ""
echo "To complete LCD removal, reboot your Raspberry Pi:"
echo "  sudo reboot"
echo ""
echo "========================================="