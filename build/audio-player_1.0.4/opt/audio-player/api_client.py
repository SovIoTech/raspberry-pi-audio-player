"""
API communication and network handling
"""

import requests
import time
import logging
import socket
import re
from urllib.parse import quote
from config_manager import ConfigManager

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, config_manager):

        """initialize api client."""
        self.config = config_manager
        # load secrets from config manager

        self.config.load_secrets()
        self.api_base_url = self.config.api_base_url
        self.auth_token = self.config.auth_token
        
        self.network_available = False
        self.last_network_check = 0
        self.network_check_interval = 30
        self.api_available = False
        
        self.last_volume_update = 0
        self.volume_update_interval = 300
    
    def send_heartbeat(self, status_info):
        """send heartbeat with status to server."""
        if not self.config.mac_address:
            return False
        
        if not self.check_network():
            return False
        
        url = f"{self.api_base_url}/heartbeat"
        headers = {
            'authorization': self.auth_token,
            'Content-Type': 'application/json'
        }
        
        payload = {
            'mac': self.config.mac_address,
            'status': status_info
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=2)
            if response.status_code == 200:
                return True
            else:
                return False
        except:
            return False
    
    def check_network(self, force_check=False):
        """check if network is available."""
        current_time = time.time()
        if not force_check and current_time - self.last_network_check < self.network_check_interval:
            return self.network_available
        
        self.last_network_check = current_time
        
        try:
            socket.gethostbyname('google.com')
            self.network_available = True
            return True
        except:
            self.network_available = False
            return False
    
    def make_api_request_safe(self, endpoint, method='POST', params=None, cache_bust=False):
        """make api request without crashing playback."""
        if not self.config.mac_address:
            return None
        
        if not self.check_network():
            return None
        
        base_url = f"{self.api_base_url}/{endpoint}?mac={quote(self.config.mac_address)}"
        
        if cache_bust:
            timestamp = int(time.time() * 1000)
            url = f"{base_url}&_t={timestamp}"
        else:
            url = base_url
        
        headers = {
            'authorization': self.auth_token,
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
        
        try:
            timeout = 10
            
            if method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=params or {}, timeout=timeout)
            else:
                response = requests.get(url, headers=headers, timeout=timeout)
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('error'):
                logger.error(f"api error: {data.get('msg')}")
                return None
            
            self.api_available = True
            return data
            
        except Exception as e:
            self.api_available = False
            return None
    
    def setup_device(self):
        """setup device - register and get configuration."""
        logger.info("setting up device...")
        
        data = self.make_api_request_safe('register')
        if data:
            self.config.device_name = data.get('device_name', '')
            self.config.location = data.get('location', '')
            
            new_volume = data.get('volume', '7')
            if new_volume != self.config.volume:
                logger.info(f"volume update from server: {self.config.volume} -> {new_volume}")
                self.config.volume = new_volume
            
            self.config.audio_mode = data.get('audio_mode', 'Normal')
            self.config.ads_enabled = data.get('ads', True)
            
            try:
                self.config.playback_interval = int(data.get('playback_interval', 5))
            except (ValueError, TypeError):
                self.config.playback_interval = 5
            
            self.config.main_playlist = data.get('play_lists', [])
            self.config.ads_playlist = data.get('ads_play_lists', [])
            
            self.config.save_config()
            self.config.device_registered = True
            
            logger.info(f"device registered: {self.config.device_name}")
            logger.info(f"volume: {self.config.volume}, ads: {self.config.ads_enabled}, interval: {self.config.playback_interval} minutes")
            return True
        else:
            logger.warning("api registration failed, trying cached config...")
            if self.config.load_config():
                logger.info("using cached configuration")
                return True
            else:
                logger.error("no configuration available")
                return False
    
    def check_volume_update(self):
        """check for volume updates from server periodically."""
        current_time = time.time()
        if current_time - self.last_volume_update > self.volume_update_interval:
            self.last_volume_update = current_time
            
            if self.check_network():
                data = self.make_api_request_safe('register')
                if data:
                    new_volume = data.get('volume', self.config.volume)
                    if new_volume != self.config.volume:
                        logger.info(f"volume updated from server: {self.config.volume} -> {new_volume}")
                        self.config.volume = new_volume
    
    def sync_tracks_safe(self):
        """sync tracks and clean up removed ones."""
        logger.info("checking for new tracks and updates...")
        
        if not self.check_network():
            logger.info("no network, skipping track sync")
            return
        
        register_data = self.make_api_request_safe('register')
        if register_data:
            new_volume = register_data.get('volume', self.config.volume)
            if new_volume != self.config.volume:
                logger.info(f"volume update during sync: {self.config.volume} -> {new_volume}")
                self.config.volume = new_volume
            
            self.config.ads_enabled = register_data.get('ads', self.config.ads_enabled)
            try:
                self.config.playback_interval = int(register_data.get('playback_interval', self.config.playback_interval))
            except:
                pass
        
        playlist_data = self.make_api_request_safe('playlist')
        if playlist_data:
            new_playlist = playlist_data.get('play_lists', [])
            if new_playlist:
                old_playlist = self.config.main_playlist
                self.config.main_playlist = new_playlist
                self.clean_removed_tracks(old_playlist, new_playlist, 'main')
        
        ads_data = self.make_api_request_safe('ads')
        if ads_data:
            new_ads = ads_data.get('ads_play_lists', [])
            if new_ads:
                old_ads = self.config.ads_playlist
                self.config.ads_playlist = new_ads
                self.clean_removed_tracks(old_ads, new_ads, 'ad')
        
        self.config.save_config()
        self.download_all_tracks()
    
    def clean_removed_tracks(self, old_list, new_list, track_type):
        """delete cached tracks that are no longer in playlist."""
        prefix = 'main_' if track_type == 'main' else 'ad_'
        
        old_filenames = set()
        for url in old_list:
            if url:
                filename = url.split('/')[-1]
                if not filename.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
                    filename += '.mp3'
                filename = re.sub(r'[^\w\-_.]', '_', filename)
                old_filenames.add(prefix + filename)
        
        new_filenames = set()
        for url in new_list:
            if url:
                filename = url.split('/')[-1]
                if not filename.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
                    filename += '.mp3'
                filename = re.sub(r'[^\w\-_.]', '_', filename)
                new_filenames.add(prefix + filename)
        
        removed = old_filenames - new_filenames
        
        if removed:
            for filename in removed:
                filepath = self.config.cache_dir / filename
                if filepath.exists():
                    try:
                        filepath.unlink()
                        logger.info(f"removed old track: {filename}")
                    except Exception as e:
                        logger.warning(f"failed to remove {filename}: {e}")
    
    def download_all_tracks(self):
        """download all tracks."""
        if not self.check_network():
            return
        
        for url in self.config.main_playlist:
            if url:
                self.download_track_safe(url, 'main')
        
        if self.config.ads_enabled:
            for url in self.config.ads_playlist:
                if url:
                    self.download_track_safe(url, 'ad')
    
    def download_track_safe(self, url, track_type='main'):
        """download track if not already cached."""
        if not url or not self.check_network():
            return None
        
        filename = url.split('/')[-1]
        if not filename.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
            filename += '.mp3'
        
        filename = re.sub(r'[^\w\-_.]', '_', filename)
        prefix = 'main_' if track_type == 'main' else 'ad_'
        filename = prefix + filename
        filepath = self.config.cache_dir / filename
        
        if filepath.exists():
            return str(filepath)
        
        try:
            logger.info(f"downloading {track_type}: {filename}")
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"downloaded: {filename}")
            return str(filepath)
            
        except Exception as e:
            logger.debug(f"download failed: {e}")
            if filepath.exists():
                filepath.unlink()
            return None