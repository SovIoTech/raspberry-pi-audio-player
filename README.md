# Raspberry Pi Audio Player with LCD Display

A background audio player service for Raspberry Pi that plays music with ads, controlled via WordPress API, featuring real-time LCD display support for 3.5" SPI screens.

## Quick Install (Recommended)

### Method 1: DEB Package (Easiest)

```bash
# Download the latest release
wget https://github.com/SovIoTech/raspberry-pi-audio-player/releases/download/v1.0.4/audio-player_1.0.4.deb

# Install
sudo dpkg -i audio-player_1.0.4.deb

# Fix dependencies if needed
sudo apt-get install -f
```

During installation, you'll be prompted to configure an optional 3.5" LCD display. Choose from:
- **tft35a driver** (recommended, 90° rotation, 48MHz)
- **Waveshare driver** (alternative 3.5" LCD support)
- **MHS-35 driver** (uses mhs35-show repository)
- **Skip LCD** (audio-only operation)

### Method 2: Install Script

```bash
git clone https://github.com/SovIoTech/raspberry-pi-audio-player.git
cd raspberry-pi-audio-player
sudo ./install.sh
```

## Features

### ?? Core Playback
- **Sequential Playback**: Tracks and ads play in order, not random
- **Ad System**: Ads play after configurable intervals (default: 6 minutes)
- **Command Control**: Remote control via WordPress API
- **Heartbeat Monitoring**: Status updates every 10 seconds
- **Resume Support**: Paused tracks resume after ads
- **Command Deferral**: Commands during ads wait until ad completes
- **Network Resilience**: Works offline with cached content
- **Volume Control**: Remote volume adjustment
- **Auto-Restart**: Service restarts on failure and boot
- **Log Management**: Automatic log rotation (7-day retention)

### ??? LCD Display Features
- **3.5" SPI LCD Support**: Real-time visual feedback on 320x480 displays
- **Multiple Driver Support**: tft35a, Waveshare, MHS-35 compatible
- **Dynamic Display Updates**: 
  - Song name with 3-line word wrapping (golden color)
  - Progress bar with elapsed/remaining/total time (blue fill)
  - Next ad countdown timer (color-coded: green/yellow/red by urgency)
  - Ad playback progress when ads are playing
  - Volume level indicator
  - Device ID (MAC address) in header
- **Smart Rendering**: Only updates when content changes (0.5s interval)
- **Performance Optimized**: Efficient framebuffer access with RGB565 pixel packing

## Building DEB Package (For Developers)

```bash
# Make the build script executable
chmod +x build-deb.sh

# Build the package
./build-deb.sh

# Package will be created in dist/ directory
```

## Service Management

```bash
# Start the service
sudo systemctl start audio-player

# Stop the service
sudo systemctl stop audio-player

# Restart the service
sudo systemctl restart audio-player

# Check status
sudo systemctl status audio-player

# View logs
sudo journalctl -u audio-player -f
```

## Files Location

- **Application**: `/opt/audio-player/`
- **Data**: `/var/lib/audio-player/`
- **Logs**: `/var/log/audio-player/`
- **Service**: `/etc/systemd/system/audio-player.service`
- **Secrets**: `/var/lib/audio-player/secret_config.json`
- **Display**: `/dev/fb1` (LCD framebuffer when configured)

## Configuration

### API Secrets

The first time you install, you'll be prompted to enter:
- API base URL (e.g., `https://your-domain.com/wp-json/api/v1`)
- API authentication token

These are stored securely in `/var/lib/audio-player/secret_config.json` with restricted permissions (600).

To reconfigure after installation:
```bash
sudo nano /var/lib/audio-player/secret_config.json
sudo systemctl restart audio-player
```

### LCD Configuration

LCD settings are configured during installation. To reconfigure:
```bash
# Reconfigure the package (will prompt for LCD setup again)
sudo dpkg-reconfigure audio-player
```

## Commands Supported

- `play` - Start/resume playback
- `pause` - Pause playback (saves position)
- `stop` - Stop playback (resets to beginning)
- `next` - Skip to next track
- `previous` - Go to previous track
- `refresh` - Update tracks and configuration
- `reboot` - Reboot the Raspberry Pi

## Ad System

- Plays ads after configurable interval (default: 6 minutes)
- Sequential ad playback (not random)
- Timer starts immediately when player starts
- Main track pauses before ad and resumes after (fixed state saving)
- Commands during ads are deferred until ad completes
- Duplicate commands are filtered (multiple "play" commands become one)
- Ad progress displayed on LCD during playback

## Heartbeat System

- Sends status every 10 seconds when idle
- Immediate response when commands are received
- Status format: `command_executed|status` or `command_deferred|status`
- Status values: `playing_track`, `playing_ad`, `paused`, `stopped`

## Network Resilience

- Continues playback when network is down
- Retries downloads and API calls
- Uses cached configuration when offline
- Automatic reconnection when network returns

## LCD Display Details

The LCD display shows:

**Header Section:**
- Device MAC address (left)
- Volume level (right)

**Song Information:**
- Song name wrapped across 3 lines
- Golden color text for visibility

**Progress Bar:**
- Blue progress indicator
- Elapsed time / Remaining time / Total duration

**Footer Section:**
- **During Songs**: Next ad countdown with color coding
  - Green: >3 minutes until ad
  - Yellow: 1-3 minutes until ad
  - Red: <1 minute until ad
- **During Ads**: Ad progress bar and remaining time

## Testing

```bash
cd /opt/audio-player
sudo python3 player.py --test
```

## Troubleshooting

### Check Logs

```bash
# Real-time logs
sudo journalctl -u audio-player -f

# Last 100 lines
sudo journalctl -u audio-player -n 100

# Log files
sudo tail -f /var/log/audio-player/player.log
sudo tail -f /var/log/audio-player/player-error.log
```

### Common Issues

1. **No sound**:
   ```bash
   alsamixer
   speaker-test -t sine -f 440 -c 2
   ```

2. **LCD not displaying**:
   ```bash
   # Check if framebuffer exists
   ls -l /dev/fb1
   
   # Check LCD driver installation
   dmesg | grep -i spi
   
   # Reconfigure LCD
   sudo dpkg-reconfigure audio-player
   ```

3. **Network issues**:
   ```bash
   ping google.com
   ```

4. **API errors**:
   Check your secret configuration:
   ```bash
   sudo cat /var/lib/audio-player/secret_config.json
   ```

5. **Service not starting**:
   ```bash
   sudo systemctl status audio-player
   sudo journalctl -u audio-player --no-pager
   ```

### Manual Testing

```bash
sudo systemctl stop audio-player
cd /opt/audio-player
sudo python3 player.py
```

## Uninstall

### DEB Package
```bash
# Interactive uninstall (prompts for LCD cleanup options)
sudo apt-get remove audio-player

# Remove package and all configuration/data
sudo apt-get purge audio-player
```

Uninstall options include:
- Keep or remove LCD configuration
- Selective data cleanup (config, cache, logs)
- Python package management options

### Install Script
```bash
sudo ./uninstall.sh
```

## Configuration Files

- `/var/lib/audio-player/secret_config.json` - API credentials (secure)
- `/var/lib/audio-player/config.json` - Device configuration
- `/var/lib/audio-player/state.json` - Playback state
- `/var/lib/audio-player/mac_address.txt` - Device MAC address
- `/var/lib/audio-player/audio_cache/` - Downloaded tracks

## Deploy to Multiple Raspberry Pis

### Using DEB Package
```bash
# Copy the .deb file to each Pi
scp dist/audio-player_1.0.4.deb pi@raspberry-pi-ip:~

# SSH into each Pi and install
ssh pi@raspberry-pi-ip
sudo dpkg -i audio-player_1.0.4.deb
sudo apt-get install -f
```

### Using Git
```bash
ssh pi@raspberry-pi-ip
git clone https://github.com/SovIoTech/raspberry-pi-audio-player.git
cd raspberry-pi-audio-player
sudo ./install.sh
```

## File Structure

```
raspberry-pi-audio-player/
+-- README.md
+-- requirements.txt
+-- build-deb.sh          # DEB package builder (v1.0.4)
+-- install.sh            # Install script
+-- uninstall.sh          # Uninstall script
+-- player.py             # Main application (enhanced timer logic)
+-- display_manager.py    # LCD rendering system (NEW)
+-- vlc_player.py         # VLC player module
+-- api_client.py         # API communication
+-- config_manager.py     # Configuration management
```

## Package Management

```bash
# List package info
dpkg -l audio-player

# List package files
dpkg -L audio-player

# Check package status
dpkg -s audio-player

# Reconfigure package (includes LCD setup)
sudo dpkg-reconfigure audio-player
```

## Development

### Testing Changes
```bash
sudo systemctl stop audio-player
cd /opt/audio-player
sudo python3 player.py
```

### Building New Version
```bash
# Update VERSION in build-deb.sh
nano build-deb.sh

# Build new package
./build-deb.sh

# Test installation
sudo dpkg -i dist/audio-player_1.0.4.deb
```

### Python Syntax Check
```bash
python3 -m py_compile *.py
```

### Testing LCD Display
```bash
# Check framebuffer access
sudo python3 -c "import display_manager; dm = display_manager.DisplayManager(); print('LCD OK')"
```

## Supported Hardware

### Raspberry Pi Models
- All models with audio output
- Tested on Pi 3, Pi 4, Pi Zero W

### LCD Displays
- 3.5" SPI LCD (320x480 resolution)
- tft35a compatible displays
- Waveshare 3.5" LCD
- MHS-35 displays

### Audio Output
- 3.5mm jack
- HDMI audio
- USB audio devices

## Support

For issues, check:
1. Service status: `sudo systemctl status audio-player`
2. Logs: `sudo journalctl -u audio-player -f`
3. Network: `ping google.com`
4. Audio: `speaker-test -t sine -f 440`
5. LCD: `ls -l /dev/fb1`
6. Secrets: `sudo cat /var/lib/audio-player/secret_config.json`

## Dependencies

**System Packages:**
- Python 3.7+
- python3-pip
- VLC media player
- libvlc-dev
- alsa-utils
- logrotate

**Python Packages:**
- python-vlc==3.0.21203
- requests==2.32.3

**Optional (for LCD):**
- LCD drivers (tft35a, Waveshare, or MHS-35)
- Framebuffer support

## Technical Details

### Display Manager
- Direct framebuffer access (`/dev/fb1`)
- RGB565 pixel format for compatibility
- Custom font rendering engine
- Real-time updates every 0.5 seconds
- Smart caching to minimize CPU usage

### Audio Player Logic
- Immediate ad timer start (fixes v1.0.3 issue)
- Proper state saving for song resume
- Ad deferral queue system
- Network failure handling with retries
- VLC auto-detection and configuration

## License

MIT License

## Contributing

1. Fork the repository
2. Create your feature branch
3. Test your changes thoroughly
4. Build and test the DEB package
5. Ensure LCD functionality works (if applicable)
6. Submit a pull request

## Changelog

### Version 1.0.4 (Current)
- MHS-35 LCD driver support added
- Interactive LCD cleanup during uninstall
- Bug fixes for display freezing
- Enhanced package builder

### Version 1.0.3
- Interactive LCD removal during uninstall
- Improved package management
- Bug fixes for state saving

### Version 1.0.2
- Integrated LCD setup in package installation
- Improved configuration management
- Bug fixes

### Version 1.0.1
- LCD display support added
- Display manager module created
- Real-time visual feedback

### Version 1.0.0 (Initial Release)
- Sequential playback with ad support
- Remote control via WordPress API
- Network resilience
- Auto-restart capability
- DEB package installer
- Heartbeat monitoring
- Log rotation

## Known Issues

- LCD display requires manual driver installation for some display models
- First-time LCD setup may require system reboot
- VLC backend occasionally needs restart after network loss (auto-handled by service)

## Future Enhancements

- Multiple display size support
- Touchscreen input support
- Additional LCD driver compatibility
- Enhanced statistics and reporting
- Playlist management improvements

## Credits

Developed for commercial audio distribution on Raspberry Pi devices with professional-grade reliability and visual feedback.