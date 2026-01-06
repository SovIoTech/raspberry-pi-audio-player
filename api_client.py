"""
API communication and network handling
"""
import threading
import requests
import time
import logging
import socket
import re
import os
from urllib.parse import quote, urlparse
from pathlib import Path
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
        
        # Reference to player for checking current track
        self.player_ref = None
        
        # Track download state
        self.is_downloading_priority = False
        self.is_downloading_background = False
        
        # Clean up any leftover temp files on startup
        self._cleanup_temp_files()
    
    def set_player_reference(self, player):
        """Set reference to player for checking current track status."""
        self.player_ref = player
    
    def _cleanup_temp_files(self):
        """Clean up any leftover .tmp files from previous sessions."""
        if self.config.cache_dir.exists():
            for file in self.config.cache_dir.iterdir():
                if file.name.endswith('.tmp'):
                    try:
                        file.unlink()
                        logger.debug(f"Cleaned up temp file: {file.name}")
                    except Exception as e:
                        logger.debug(f"Failed to clean up temp file {file.name}: {e}")
    
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
                logger.debug(f"Heartbeat failed with status: {response.status_code}")
                return False
        except Exception as e:
            logger.debug(f"Heartbeat error: {e}")
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
            logger.debug(f"api request to {endpoint} failed: {e}")
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

    def _normalize_filename(self, url):
        """Helper to normalize filename from URL."""
        if not url or not isinstance(url, str):
            return "unknown.mp3"
        
        # Parse URL and get filename
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        
        if not filename:
            filename = "unknown"
        
        # Clean filename and ensure .mp3 extension
        if not filename.lower().endswith(('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac')):
            filename += '.mp3'
        
        # Remove query parameters from filename
        if '?' in filename:
            filename = filename.split('?')[0]
        
        # Clean for filesystem (safe characters only)
        filename = re.sub(r'[^\w\-_.]', '_', filename)
        
        # Truncate if too long
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:150] + ext
        
        return filename
    
    def sync_tracks_safe(self):
        """sync tracks and clean up removed ones. Returns True if currently playing track was removed."""
        logger.info("checking for new tracks and updates...")
        
        if not self.check_network():
            logger.info("no network, skipping track sync")
            return False
        
        # Get updated configuration
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
        
        # Track if current playing track was removed
        current_track_removed = False
        
        # Process main playlist
        playlist_data = self.make_api_request_safe('playlist')
        if playlist_data:
            new_playlist = playlist_data.get('play_lists', [])
            if new_playlist:
                old_playlist = self.config.main_playlist
                
                # Check if playlist actually changed
                playlist_changed = old_playlist != new_playlist
                
                self.config.main_playlist = new_playlist
                removed = self.clean_removed_tracks(old_playlist, new_playlist, 'main')
                
                # If currently playing track was removed
                if removed:
                    current_track_removed = True
                
                # Also reset if playlist order changed
                if playlist_changed:
                    logger.info("main playlist updated, resetting track index")
                    self.config.current_track_index = 0
                    self.config.save_state()
        
        # Process ads playlist with SAME robust logic
        ads_data = self.make_api_request_safe('ads')
        if ads_data:
            new_ads = ads_data.get('ads_play_lists', [])
            if new_ads:
                old_ads = self.config.ads_playlist
                
                # Check if ads playlist actually changed
                ads_changed = old_ads != new_ads
                
                self.config.ads_playlist = new_ads
                
                # Clean ads using the SAME robust method
                ads_removed = self.clean_removed_tracks(old_ads, new_ads, 'ad')
                
                # Check if we're currently playing an ad that was removed
                if ads_removed and self.player_ref and hasattr(self.player_ref, 'is_playing_ad'):
                    if self.player_ref.is_playing_ad:
                        logger.warning("Currently playing ad was removed from playlist!")
                
                # Also reset if ads playlist changed
                if ads_changed:
                    logger.info("ads playlist updated, resetting ad index")
                    self.config.current_ad_index = 0
                    self.config.save_state()
        
        self.config.save_config()
        
        # Download high priority tracks first (first few tracks)
        self.download_priority_tracks()
        
        # Start background download for remaining tracks
        threading.Thread(target=self.download_all_tracks, daemon=True).start()
        
        return current_track_removed

    def clean_removed_tracks(self, old_list, new_list, track_type):
        """
        Robust Cleanup: Deletes ANY file on disk that is not in the new playlist.
        Returns True if a currently playing track/ad was removed.
        """
        prefix = 'main_' if track_type == 'main' else 'ad_'
        
        # 1. Calculate the filenames we WANT to keep
        wanted_filenames = set()
        for url in new_list:
            if url:
                filename = self._normalize_filename(url)
                wanted_filenames.add(prefix + filename)
        
        # 2. Look at what files actually EXIST on disk
        existing_files = set()
        if self.config.cache_dir.exists():
            for file in self.config.cache_dir.iterdir():
                # Look for both .mp3 files and .tmp files
                if file.name.startswith(prefix) and (file.name.endswith('.mp3') or file.name.endswith('.tmp')):
                    existing_files.add(file.name)
        
        # 3. Calculate difference: What is on disk that shouldn't be?
        files_to_remove = existing_files - wanted_filenames
        
        # Check if currently playing track is about to be removed
        current_track_removed = False
        
        if track_type == 'main' and self.player_ref and hasattr(self.player_ref, 'vlc_player'):
            current_track = self.player_ref.vlc_player.current_track_path
            if current_track:
                current_filename = Path(current_track).name
                if current_filename in files_to_remove:
                    current_track_removed = True
                    logger.info(f"Currently playing track {current_filename} is not in new playlist")
        
        elif track_type == 'ad' and self.player_ref:
            # Check for ad
            if hasattr(self.player_ref, 'is_playing_ad') and self.player_ref.is_playing_ad:
                if hasattr(self.player_ref.vlc_player, 'current_track_path'):
                    current_track = self.player_ref.vlc_player.current_track_path
                    if current_track:
                        current_filename = Path(current_track).name
                        if current_filename in files_to_remove:
                            logger.warning(f"Currently playing AD {current_filename} is not in new playlist!")
        
        # 4. Delete the unwanted files
        if files_to_remove:
            logger.info(f"Found {len(files_to_remove)} orphaned {track_type} tracks on disk. Cleaning up...")
            for filename in files_to_remove:
                filepath = self.config.cache_dir / filename
                try:
                    if filepath.exists():
                        filepath.unlink()
                        logger.info(f"Deleted orphaned file: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to remove {filename}: {e}")
        
        return current_track_removed
    
    def download_priority_tracks(self):
        """Download first few tracks immediately for quick playback."""
        if not self.check_network() or self.is_downloading_priority:
            return
        
        self.is_downloading_priority = True
        
        try:
            # Download first 3 main tracks immediately
            priority_urls = self.config.main_playlist[:3]
            for i, url in enumerate(priority_urls):
                if url:
                    logger.info(f"Priority downloading main track {i+1}/3")
                    self.download_track_safe(url, 'main', priority=True)
            
            # Also download first 2 ads if enabled
            if self.config.ads_enabled and self.config.ads_playlist:
                priority_ads = self.config.ads_playlist[:2]
                for i, url in enumerate(priority_ads):
                    if url:
                        logger.info(f"Priority downloading ad {i+1}/2")
                        self.download_track_safe(url, 'ad', priority=True)
            
            logger.info("Priority download complete")
            
        except Exception as e:
            logger.error(f"Error in priority download: {e}")
        finally:
            self.is_downloading_priority = False
    
    def download_all_tracks(self):
        """Download all tracks in background."""
        if not self.check_network() or self.is_downloading_background:
            return
        
        self.is_downloading_background = True
        
        try:
            logger.info("Starting background download of all tracks...")
            
            # Download remaining main tracks (skip first 3 priority tracks)
            for i, url in enumerate(self.config.main_playlist):
                if url and i >= 3:  # Skip first 3 already downloaded
                    self.download_track_safe(url, 'main', priority=False)
            
            # Download remaining ads if enabled
            if self.config.ads_enabled:
                for i, url in enumerate(self.config.ads_playlist):
                    if url and i >= 2:  # Skip first 2 already downloaded
                        self.download_track_safe(url, 'ad', priority=False)
            
            logger.info("Background download completed")
            
        except Exception as e:
            logger.error(f"Error in background download: {e}")
        finally:
            self.is_downloading_background = False
    
    def download_track_safe(self, url, track_type='main', priority=False):
        """Download track if not already cached."""
        if not url or not self.check_network():
            return None
        
        # Basic URL validation
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL: {url[:50] if url else 'None'}...")
            return None
        
        filename = self._normalize_filename(url)
        prefix = 'main_' if track_type == 'main' else 'ad_'
        filename = prefix + filename
        filepath = self.config.cache_dir / filename
        
        # Check if file already exists and is valid (minimum 1KB)
        if filepath.exists():
            try:
                if filepath.stat().st_size > 1024:
                    if priority:
                        logger.info(f"✓ Cached (Skipping download): {filename}")
                    return str(filepath)
                else:
                    logger.warning(f"Removing corrupt file (too small): {filename}")
                    filepath.unlink()
            except Exception as e:
                logger.warning(f"Error checking existing file {filename}: {e}")
        
        try:
            if priority:
                logger.info(f"Downloading {track_type}: {filename}")
            else:
                logger.debug(f"Background downloading {track_type}: {filename}")
            
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Create temp file
            temp_filepath = filepath.with_suffix('.tmp')
            
            with open(temp_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    
                    # Check if this URL is still in the playlist (abort if removed)
                    if track_type == 'main' and url not in self.config.main_playlist:
                        logger.info(f"Aborting download for removed main track: {filename}")
                        f.close()
                        temp_filepath.unlink()
                        return None
                    
                    if track_type == 'ad' and url not in self.config.ads_playlist:
                        logger.info(f"Aborting download for removed ad: {filename}")
                        f.close()
                        temp_filepath.unlink()
                        return None
                    
                    f.write(chunk)
            
            # Atomic rename from .tmp to final file
            if temp_filepath.exists():
                temp_filepath.replace(filepath)
            
            if priority:
                logger.info(f"✓ Downloaded: {filename}")
            else:
                logger.debug(f"✓ Background downloaded: {filename}")
            
            return str(filepath)
            
        except Exception as e:
            logger.debug(f"Download failed for {filename}: {e}")
            
            # Cleanup temp file if it exists
            if 'temp_filepath' in locals() and temp_filepath and temp_filepath.exists():
                try:
                    temp_filepath.unlink()
                except Exception as cleanup_e:
                    logger.debug(f"Failed to clean up temp file: {cleanup_e}")
            
            # Remove any zero-byte or corrupt files
            if filepath.exists() and filepath.stat().st_size == 0:
                try:
                    filepath.unlink()
                except Exception as cleanup_e:
                    logger.debug(f"Failed to remove zero-byte file: {cleanup_e}")
            
            return None

