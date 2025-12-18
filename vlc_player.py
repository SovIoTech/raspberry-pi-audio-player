import vlc
import time
import logging
import subprocess
import re
from pathlib import Path

logger = logging.getLogger(__name__)

class VLCPlayer:
    def __init__(self, config_manager, api_client):
        self.config = config_manager
        self.api = api_client
        self.player = None
        self.instance = None
        self.current_track_path = None
        self.pause_position = 0
        self.was_paused = False
    
    def _detect_audio_device(self):
        try:
            result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
            output = result.stdout
            
            headphone_patterns = [
                (r'card (\d+):.*Headphones', 'headphones'),
                (r'card (\d+):.*bcm2835', 'bcm2835 analog'),
                (r'card (\d+):.*Analog', 'analog'),
                (r'card (\d+):.*PCH', 'pch audio'),
                (r'card (\d+):.*snd_rpi_\w+', 'raspberry pi sound card'),
                (r'card (\d+):.*USB Audio', 'usb audio'),
            ]
            
            hdmi_patterns = [
                r'HDMI',
                r'hdmi',
                r'vc4hdmi',
                r'vc4-hdmi',
            ]
            
            for pattern, description in headphone_patterns:
                match = re.search(pattern, output, re.IGNORECASE)
                if match:
                    card_num = match.group(1)
                    line = match.group(0)
                    if not any(hdmi in line for hdmi in hdmi_patterns):
                        device = f'hw:{card_num},0'
                        logger.info(f"auto-detected {description} at card {card_num}")
                        return device
            
            lines = output.strip().split('\n')
            for line in lines:
                if 'card' in line and 'device' in line:
                    if any(hdmi in line for hdmi in hdmi_patterns):
                        continue
                    match = re.search(r'card (\d+):', line)
                    if match:
                        card_num = match.group(1)
                        device = f'hw:{card_num},0'
                        logger.info(f"using non-hdmi device at card {card_num}")
                        return device
            
            logger.info("no specific audio device detected, using default card 0")
            return 'hw:0,0'
            
        except Exception as e:
            logger.warning(f"audio device detection failed: {e}, using default")
            return 'hw:0,0'
    
    def init_vlc(self):
        alsa_device = self._detect_audio_device()
        
        vlc_args = [
            '--no-video',
            '--quiet',
            '--network-caching=3000',
            '--file-caching=3000',
            '--gain=1.0',
            '--aout=alsa',
            f'--alsa-audio-device={alsa_device}',
        ]
        
        try:
            self.instance = vlc.Instance(*vlc_args)
            logger.info(f"vlc instance created with device: {alsa_device}")
            self.player = self.instance.media_player_new()
            
            if self.player:
                logger.info("vlc player created successfully")
                self.set_volume_smooth(self.config.volume)
                
                try:
                    test_file = "/usr/share/sounds/alsa/Front_Center.wav"
                    if Path(test_file).exists():
                        media = self.instance.media_new(test_file)
                        self.player.set_media(media)
                        self.player.play()
                        time.sleep(0.05)
                        if self.player.is_playing():
                            self.player.stop()
                            logger.info("audio test successful")
                except:
                    logger.debug("audio test skipped or failed")
                
                return True
            else:
                logger.error("failed to create vlc player")
                return False
                
        except Exception as e:
            logger.error(f"failed to initialize vlc with {alsa_device}: {e}")
            try:
                fallback_args = ['--no-video', '--quiet', '--aout=alsa', '--alsa-audio-device=default']
                self.instance = vlc.Instance(*fallback_args)
                self.player = self.instance.media_player_new()
                logger.info("using fallback vlc configuration with 'default' device")
                self.set_volume_smooth(self.config.volume)
                return True
            except Exception as e2:
                logger.error(f"fallback vlc also failed: {e2}")
                return False
    
    def set_volume_smooth(self, volume_level):
        try:
            volume_level = str(volume_level)
            self.config.volume = volume_level
            
            if self.player:
                vol = int(volume_level) * 10
                vol = max(10, min(100, vol))
                self.player.audio_set_volume(vol)
                logger.info(f"volume set to {volume_level}/10 ({vol}%)")
        except Exception as e:
            logger.error(f"failed to set volume: {e}")
    
    def play_track(self, filepath, start_position=0):
        if not filepath:
            logger.error("no filepath provided")
            return False
        
        file_path_obj = Path(filepath)
        if not file_path_obj.exists():
            logger.error(f"track not found: {filepath}")
            return False
        
        if not self.player:
            logger.error("vlc player not initialized")
            return False
        
        try:
            if self.player.is_playing():
                self.player.stop()
                time.sleep(0.05)
            
            media = self.instance.media_new(filepath)
            self.player.set_media(media)
            
            result = self.player.play()
            if result != 0:
                return False
            
            if start_position > 0:
                time.sleep(0.1)
                for attempt in range(3):
                    try:
                        self.player.set_time(int(start_position * 1000))
                        break
                    except:
                        time.sleep(0.05)
            
            for _ in range(20):
                if self.player.is_playing():
                    action = "resuming" if start_position > 0 else "playing"
                    logger.info(f"{action}: {Path(filepath).name}" + 
                               (f" from {int(start_position)}s" if start_position > 0 else ""))
                    self.current_track_path = filepath
                    return True
                time.sleep(0.1)
            
            return False
            
        except Exception as e:
            logger.error(f"play error: {e}")
            return False
    
    def play_next_track(self):
        cached_tracks = self.config.get_cached_tracks('main')
        if not cached_tracks:
            logger.warning("no cached tracks available")
            return False
        
        if self.config.current_track_index >= len(cached_tracks):
            logger.info(f"track index {self.config.current_track_index} out of bounds, resetting to 0")
            self.config.current_track_index = 0
        
        original_index = self.config.current_track_index
        tracks_tried = 0
        
        while tracks_tried < len(cached_tracks):
            track = cached_tracks[self.config.current_track_index]
            
            if not Path(track).exists():
                logger.warning(f"track missing, skipping: {Path(track).name}")
                self.config.current_track_index = (self.config.current_track_index + 1) % len(cached_tracks)
                tracks_tried += 1
                continue
            
            if self.play_track(track):
                self.pause_position = 0
                self.was_paused = False
                self.config.current_track_index = (self.config.current_track_index + 1) % len(cached_tracks)
                self.config.save_state()
                logger.info(f"playing track {Path(track).name} (index: {original_index})")
                return True
            else:
                logger.warning(f"failed to play track: {Path(track).name}")
                self.config.current_track_index = (self.config.current_track_index + 1) % len(cached_tracks)
                tracks_tried += 1
                continue
        
        logger.error(f"no playable tracks found after checking all {len(cached_tracks)} cached tracks")
        self.config.current_track_index = original_index
        return False
    
    def play_ad(self):
        cached_ads = self.config.get_cached_tracks('ad')
        if not cached_ads:
            return False
        
        if self.config.current_ad_index >= len(cached_ads):
            self.config.current_ad_index = 0
        
        ad_track = cached_ads[self.config.current_ad_index]
        
        success = self.play_track(ad_track)
        if success:
            self.config.current_ad_index += 1
            self.config.save_state()
        return success
    
    def resume_from_pause(self):
        if not self.was_paused or not self.current_track_path or self.pause_position <= 0:
            return False
        
        logger.info(f"resuming {Path(self.current_track_path).name} from {int(self.pause_position)}s")
        success = self.play_track(self.current_track_path, self.pause_position)
        if success:
            self.was_paused = False
        return success
    
    def resume(self):
        try:
            if self.player:
                self.player.pause()
                return True
        except Exception as e:
            logger.error(f"failed to resume: {e}")
        return False
    
    def pause(self):
        try:
            if self.player and self.player.is_playing():
                self.pause_position = self.player.get_time() / 1000
                self.player.pause()
                self.was_paused = True
                logger.info(f"playback paused at {int(self.pause_position)}s")
                return True
        except Exception as e:
            logger.error(f"failed to pause: {e}")
        return False
    
    def stop(self):
        if self.player:
            self.player.stop()
    
    def is_playing(self):
        try:
            return self.player and self.player.is_playing()
        except:
            return False
    
    def wait_for_playback(self):
        try:
            while self.is_playing():
                time.sleep(0.5)
        except:
            pass
    
    def cleanup(self):
        if self.player:
            try:
                self.player.stop()
                self.player.release()
            except:
                pass