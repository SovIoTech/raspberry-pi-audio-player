# Raspberry Pi Audio Player

A background audio player service for Raspberry Pi that plays music with ads, controlled via WordPress API.

## Quick Install

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

## Installation

### Automatic Installation

```bash
git clone https://github.com/yourusername/raspberry-pi-audio-player.git
cd raspberry-pi-audio-player
sudo ./install.sh
```

### Manual Installation

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip vlc libvlc-dev alsa-utils
pip3 install -r requirements.txt
sudo mkdir -p /opt/audio-player
sudo mkdir -p /var/lib/audio-player/audio_cache
sudo mkdir -p /var/log/audio-player
sudo cp player.py vlc_player.py api_client.py config_manager.py /opt/audio-player/
sudo chmod +x /opt/audio-player/player.py
sudo cp audio-player.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable audio-player.service
sudo chown -R pi:pi /opt/audio-player /var/lib/audio-player /var/log/audio-player
sudo systemctl start audio-player.service
```

## Service Management

```bash
sudo systemctl start audio-player
sudo systemctl stop audio-player
sudo systemctl restart audio-player
sudo systemctl status audio-player
sudo journalctl -u audio-player -f
```

## Files Location

- **Application**: `/opt/audio-player/`
- **Data**: `/var/lib/audio-player/`
- **Logs**: `/var/log/audio-player/`
- **Service**: `/etc/systemd/system/audio-player.service`

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
python3 player.py --test
```

## Troubleshooting

### Check Logs

```bash
sudo journalctl -u audio-player -n 100
tail -f /var/log/audio-player/player.log
tail -f /var/log/audio-player/player-error.log
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
   ```bash
   curl -I https://joes452.sg-host.com
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
python3 player.py
```

## Uninstall

```bash
sudo ./uninstall.sh
```

## Configuration Files

- `/var/lib/audio-player/config.json` - Device configuration
- `/var/lib/audio-player/state.json` - Playback state
- `/var/lib/audio-player/mac_address.txt` - Device MAC address
- `/var/lib/audio-player/audio_cache/` - Downloaded tracks

## Replicate to Multiple Raspberry Pis

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
+-- install.sh
+-- uninstall.sh
+-- audio-player.service
+-- player.py
+-- vlc_player.py
+-- api_client.py
+-- config_manager.py
```

## Development

```bash
python3 player.py
python3 -m py_compile *.py
```

## Support

For issues, check:
1. Service status: `sudo systemctl status audio-player`
2. Logs: `sudo journalctl -u audio-player -f`
3. Network: `ping google.com`
4. Audio: `speaker-test -t sine -f 440`

## License

MIT License
