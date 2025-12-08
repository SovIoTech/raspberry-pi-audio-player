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

# Stop and disable service
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
read -p "Remove configuration and data files (including secrets)? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Removing data files..."
    rm -rf /var/lib/audio-player
    rm -rf /var/log/audio-player
    # Remove secrets if present
    rm -f /var/lib/audio-player/secret_config.json
else
    echo "Data files preserved in:"
    echo "  /var/lib/audio-player"
    echo "  /var/log/audio-player"
fi

echo "========================================="
echo "Uninstall completed!"
echo "========================================="
