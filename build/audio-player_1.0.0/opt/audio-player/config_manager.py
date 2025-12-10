"""
Configuration and state management
"""

import json
import re
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, base_dir, persistent_dir):

        """initialize secrets manager."""
        self.secret_config_file = persistent_dir / "secret_config.json"
        self.api_base_url = None
        self.auth_token = None

        """initialize configuration manager."""
        self.base_dir = base_dir
        self.persistent_dir = persistent_dir
        
        self.cache_dir = persistent_dir / "audio_cache"
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        
        self.config_file = persistent_dir / "config.json"
        self.state_file = persistent_dir / "state.json"
        self.mac_file = persistent_dir / "mac_address.txt"
        
        self.mac_address = None
        self.device_registered = False
        
        self.device_name = "Raspberry Pi Audio Player"
        self.location = "Unknown"
        self.volume = "7"
        self.audio_mode = "Normal"
        self.ads_enabled = True
        self.playback_interval = 5
        self.main_playlist = []
        self.ads_playlist = []
        
        self.current_track_index = 0
        self.current_ad_index = 0
        self.total_playback_time_since_last_ad = 0
        self.last_playback_check_time = 0
        self.last_minute_log = 0
    
    def load_mac_address(self):
        """get mac address from eth0 once at startup."""
        if self.mac_file.exists():
            try:
                with open(self.mac_file, 'r') as f:
                    saved_mac = f.read().strip()
                if saved_mac and saved_mac != '00:00:00:00:00:00':
                    self.mac_address = saved_mac
                    logger.info(f"using saved mac address: {saved_mac}")
                    return saved_mac
            except Exception as e:
                logger.warning(f"could not read saved mac: {e}")
        
        logger.info("getting mac address from eth0...")
        max_retries = 10
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                eth0_path = '/sys/class/net/eth0/address'
                if Path(eth0_path).exists():
                    with open(eth0_path, 'r') as f:
                        mac = f.read().strip()
                    
                    if mac and mac != '00:00:00:00:00:00':
                        self.mac_address = mac
                        logger.info(f"found mac address on eth0: {mac}")
                        
                        with open(self.mac_file, 'w') as f:
                            f.write(mac)
                        return mac
                
            except Exception as e:
                logger.warning(f"error reading mac: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        fallback_mac = "00:00:00:00:00:00"
        self.mac_address = fallback_mac
        logger.error(f"could not get mac from eth0, using fallback: {fallback_mac}")
        return fallback_mac

    def load_secrets(self):
        """Load sensitive configuration like API token."""
        if self.secret_config_file.exists():
            try:
                with open(self.secret_config_file, "r") as f:
                    secrets = json.load(f)
                self.api_base_url = secrets.get("api_base_url")
                self.auth_token = secrets.get("auth_token")
                logger.info("secret config loaded successfully")
                return True
            except Exception as e:
                logger.error(f"error loading secret config: {e}")
        else:
            logger.warning(f"secret config file not found: {self.secret_config_file}")
        return False

    
    def load_config(self):
        """load configuration from config.json if exists."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                self.device_name = config.get('device_name', self.device_name)
                self.location = config.get('location', self.location)
                self.volume = config.get('volume', self.volume)
                self.audio_mode = config.get('audio_mode', self.audio_mode)
                self.ads_enabled = config.get('ads', self.ads_enabled)
                
                try:
                    self.playback_interval = int(config.get('playback_interval', 5))
                except (ValueError, TypeError):
                    self.playback_interval = 5
                
                self.main_playlist = config.get('play_lists', [])
                self.ads_playlist = config.get('ads_play_lists', [])
                
                logger.info("configuration loaded from file")
                logger.info(f"volume: {self.volume}, ads: {self.ads_enabled}, interval: {self.playback_interval} minutes")
                return True
                
            except Exception as e:
                logger.error(f"error loading config: {e}")
        
        return False
    
    def save_config(self):
        """save current configuration to config.json."""
        config = {
            'device_name': self.device_name,
            'location': self.location,
            'volume': self.volume,
            'audio_mode': self.audio_mode,
            'ads': self.ads_enabled,
            'playback_interval': self.playback_interval,
            'play_lists': self.main_playlist,
            'ads_play_lists': self.ads_playlist
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("configuration saved")
        except Exception as e:
            logger.error(f"error saving config: {e}")
    
    def load_state(self):
        """load playback state from state.json if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                self.current_track_index = state.get('current_track', 0)
                self.current_ad_index = state.get('current_ad', 0)
                self.total_playback_time_since_last_ad = state.get('total_playback_time', 0)
                self.last_playback_check_time = 0

                if self.main_playlist and self.current_track_index >= len(self.main_playlist):
                    self.current_track_index = 0
                
                if self.ads_playlist and self.current_ad_index >= len(self.ads_playlist):
                    self.current_ad_index = 0
                
                logger.info(f"loaded state: track {self.current_track_index}, ad {self.current_ad_index}")
                
            except Exception as e:
                logger.error(f"error loading state: {e}")
                self.total_playback_time_since_last_ad = 0
    
    def save_state(self):
        """save current playback state to state.json."""
        state = {
            'current_track': self.current_track_index,
            'current_ad': self.current_ad_index,
            'total_playback_time': self.total_playback_time_since_last_ad
        }
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"error saving state: {e}")
    
    def get_cached_tracks(self, track_type='main'):
        """get list of cached tracks in order."""
        prefix = 'main_' if track_type == 'main' else 'ad_'
        tracks = []
        
        if self.cache_dir.exists():
            for file in self.cache_dir.iterdir():
                if file.name.startswith(prefix) and file.is_file():
                    tracks.append(str(file))
        
        return sorted(tracks)