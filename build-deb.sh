#!/bin/bash
#
# Raspberry Pi Audio Player - DEB Package Builder
# Run with: ./build-deb.sh

set -e

VERSION="1.0.0"
PACKAGE_NAME="audio-player"
ARCH="all"
MAINTAINER="Masuod Ghafoor <masuod.ghafoor85@gmail.com>"
DESCRIPTION="Background audio player service for Raspberry Pi"

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

# Copy application files
echo "Copying application files..."
cp player.py vlc_player.py api_client.py config_manager.py "${BUILD_DIR}/opt/audio-player/"
chmod +x "${BUILD_DIR}/opt/audio-player/player.py"

# Copy documentation
cp README.md "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/"
cp requirements.txt "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/"

# Create systemd service file
echo "Creating systemd service..."
cat > "${BUILD_DIR}/etc/systemd/system/audio-player.service" << 'EOF'
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

# Create control file
echo "Creating control file..."
cat > "${DEBIAN_DIR}/control" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.7), python3-pip, vlc, libvlc-dev, alsa-utils, logrotate
Maintainer: ${MAINTAINER}
Description: ${DESCRIPTION}
 A background audio player service for Raspberry Pi that plays music with ads,
 controlled via WordPress API. Features include sequential playback, ad system,
 remote control, heartbeat monitoring, and network resilience.
Homepage: https://github.com/SovIoTech/raspberry-pi-audio-player
EOF

# Create postinst script (runs after installation)
echo "Creating postinst script..."
cat > "${DEBIAN_DIR}/postinst" << 'EOF'
#!/bin/bash
set -e

echo "Configuring audio-player..."

# Create directories
mkdir -p /var/lib/audio-player/audio_cache
mkdir -p /var/log/audio-player

# Set permissions
chown -R root:root /opt/audio-player
chown -R root:root /var/lib/audio-player
chown -R root:root /var/log/audio-player
chmod 755 /opt/audio-player
chmod 755 /var/lib/audio-player
chmod 755 /var/log/audio-player

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install --break-system-packages --ignore-installed --root-user-action=ignore python-vlc==3.0.21203 requests==2.32.3 || true

# Configure API secrets if not exists
SECRET_FILE="/var/lib/audio-player/secret_config.json"
if [ ! -f "$SECRET_FILE" ]; then
    echo ""
    echo "=============================="
    echo "Configure API Secret"
    echo "=============================="
    
    read -p "Enter API base URL: " API_BASE_URL
    read -p "Enter API token: " API_TOKEN
    
    cat <<EOFCONF > "$SECRET_FILE"
{
    "api_base_url": "$API_BASE_URL",
    "auth_token": "$API_TOKEN"
}
EOFCONF
    
    chmod 600 "$SECRET_FILE"
    echo "API secret saved successfully!"
fi

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable audio-player.service

# Start the service automatically
echo "Starting audio-player service..."
systemctl start audio-player.service

echo ""
echo "========================================="
echo "Installation completed successfully!"
echo "========================================="
echo "Service status:"
systemctl status audio-player.service --no-pager -l || true
echo ""
echo "View live logs with:"
echo "  sudo journalctl -u audio-player -f"
echo ""
echo "Control the service with:"
echo "  sudo systemctl stop audio-player"
echo "  sudo systemctl restart audio-player"
echo "========================================="

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/postinst"

# Create prerm script (runs before removal)
echo "Creating prerm script..."
cat > "${DEBIAN_DIR}/prerm" << 'EOF'
#!/bin/bash
set -e

# Stop and disable service
systemctl stop audio-player.service || true
systemctl disable audio-player.service || true

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/prerm"

# Create postrm script (runs after removal)
echo "Creating postrm script..."
cat > "${DEBIAN_DIR}/postrm" << 'EOF'
#!/bin/bash
set -e

if [ "$1" = "purge" ]; then
    # Remove data and logs on purge
    rm -rf /var/lib/audio-player
    rm -rf /var/log/audio-player
    echo "All configuration and data files removed."
fi

# Reload systemd
systemctl daemon-reload || true

exit 0
EOF

chmod 755 "${DEBIAN_DIR}/postrm"

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

# Create changelog
echo "Creating changelog..."
cat > "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/changelog" << EOF
audio-player (${VERSION}) stable; urgency=low

  * Initial release
  * Sequential playback with ad support
  * Remote control via API
  * Network resilience
  * Auto-restart capability

 -- ${MAINTAINER}  $(date -R)
EOF

gzip -9 "${BUILD_DIR}/usr/share/doc/${PACKAGE_NAME}/changelog"

# Build the package
echo "Building DEB package..."
dpkg-deb --build "${BUILD_DIR}"

# Move to output directory
mkdir -p dist
mv "build/${PACKAGE_NAME}_${VERSION}.deb" "dist/"

echo ""
echo "========================================="
echo "Build Complete!"
echo "========================================="
echo "Package: dist/${PACKAGE_NAME}_${VERSION}.deb"
echo ""
echo "Install with:"
echo "  sudo dpkg -i dist/${PACKAGE_NAME}_${VERSION}.deb"
echo "  sudo apt-get install -f  # Fix dependencies if needed"
echo ""
echo "Uninstall with:"
echo "  sudo apt-get remove ${PACKAGE_NAME}"
echo "  sudo apt-get purge ${PACKAGE_NAME}  # Remove config files too"
echo "========================================="
