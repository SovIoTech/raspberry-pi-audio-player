# Raspberry Pi Audio Player

A background audio player service for Raspberry Pi that plays music with ads, controlled via WordPress API.

## Quick Install (Recommended)

### Method 1: DEB Package (Easiest)

```bash
# Download the latest release
wget https://github.com/SovIoTech/raspberry-pi-audio-player/releases/download/v1.0.0/audio-player_1.0.0.deb

# Install
sudo dpkg -i audio-player_1.0.0.deb

# Fix dependencies if needed
sudo apt-get install -f
```

### Method 2: Install Script

```bash
git clone https://github.com/SovIoTech/raspberry-pi-audio-player.git
cd raspberry-pi-audio-player
sudo ./install.sh
```

## Features

- **Sequential Playback**: Tracks and ads play in order, not random
- **Ad System**: Ads play after configurable intervals (default: 5 minutes)
- **Command Control**: Remote control via WordPress API
- **Heartbeat Monitoring**: Status updates every 10 seconds
- **Resume Support**: Paused tracks resume after ads
- **Command Deferral**: Commands during ads wait until ad completes
- **Network Resilience**: Works offline with cached content
- **Volume Control**: Remote volume adjustment
- **Auto-Restart**: Service restarts on failure and boot
- **Log Management**: Automatic log rotation

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

## Commands Supported

- `play` - Start/resume playback
- `pause` - Pause playback (saves position)
- `stop` - Stop playback (resets to beginning)
- `next` - Skip to next track
- `previous` - Go to previous track
- `refresh` - Update tracks and configuration
- `reboot` - Reboot the Raspberry Pi

## Ad System

- Plays ads after configurable interval (default: 5 minutes)
- Main track pauses before ad and resumes after
- Commands during ads are deferred until ad completes
- Duplicate commands are filtered (multiple "play" commands become one)

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

2. **Network issues**:
   ```bash
   ping google.com
   ```

3. **API errors**:
   Check your secret configuration:
   ```bash
   sudo cat /var/lib/audio-player/secret_config.json
   ```

4. **Service not starting**:
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
# Remove package but keep configuration
sudo apt-get remove audio-player

# Remove package and all configuration/data
sudo apt-get purge audio-player
```

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
scp dist/audio-player_1.0.0.deb pi@raspberry-pi-ip:~

# SSH into each Pi and install
ssh pi@raspberry-pi-ip
sudo dpkg -i audio-player_1.0.0.deb
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
+-- build-deb.sh          # DEB package builder
+-- install.sh            # Install script
+-- uninstall.sh          # Uninstall script
+-- player.py             # Main application
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

# Reconfigure package
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
sudo dpkg -i dist/audio-player_1.0.1.deb
```

### Python Syntax Check
```bash
python3 -m py_compile *.py
```

## Support

For issues, check:
1. Service status: `sudo systemctl status audio-player`
2. Logs: `sudo journalctl -u audio-player -f`
3. Network: `ping google.com`
4. Audio: `speaker-test -t sine -f 440`
5. Secrets: `sudo cat /var/lib/audio-player/secret_config.json`

## Dependencies

- Python 3.7+
- python3-pip
- VLC media player
- libvlc-dev
- alsa-utils
- logrotate

Python packages:
- python-vlc==3.0.21203
- requests==2.32.3

## License

MIT License

## Contributing

1. Fork the repository
2. Create your feature branch
3. Test your changes
4. Build and test the DEB package
5. Submit a pull request

## Changelog

### Version 1.0.0 (Initial Release)
- Sequential playback with ad support
- Remote control via WordPress API
- Network resilience
- Auto-restart capability
- DEB package installer
- Heartbeat monitoring
- Log rotation