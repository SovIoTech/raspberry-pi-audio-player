"""
VLC player functionality
"""

import vlc
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class VLCPlayer:
    def __init__(self, config_manager, api_client):
        """initialize the vlc player."""
        self.config = config_manager
        self.api = api_client
        self.player = None
        self.instance = None
        
        self.current_track_path = None
        self.pause_position = 0
        self.was_paused = False
    
    def init_vlc(self):
        """initialize vlc instance and player."""
        vlc_args = [
            '--no-video',
            '--quiet',
            '--network-caching=3000',
            '--file-caching=3000',
            '--gain=1.0',
            '--aout=alsa',
            '--alsa-audio-device=hw:0,0',
        ]
        
        try:
            self.instance = vlc.Instance(*vlc_args)
            logger.info("vlc instance created successfully")
            
            self.player = self.instance.media_player_new()
            if self.player:
                logger.info("vlc player created successfully")
                self.set_volume_smooth(self.config.volume)
                return True
            else:
                logger.error("failed to create vlc player")
                return False
                
        except Exception as e:
            logger.error(f"failed to initialize vlc: {e}")
            try:
                self.instance = vlc.Instance('--no-video', '--quiet', '--aout=alsa')
                self.player = self.instance.media_player_new()
                logger.info("using fallback vlc configuration")
                self.set_volume_smooth(self.config.volume)
                return True
            except Exception as e2:
                logger.error(f"fallback vlc also failed: {e2}")
                return False
    
    def set_volume_smooth(self, volume_level):
        """set volume without interrupting playback."""
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
        """play a track file from a specific position."""
        if not filepath or not Path(filepath).exists():
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
        """play next track in order."""
        cached_tracks = self.config.get_cached_tracks('main')
        if not cached_tracks:
            logger.warning("no cached tracks available")
            return False
        
        if self.config.current_track_index >= len(cached_tracks):
            self.config.current_track_index = 0
        
        track = cached_tracks[self.config.current_track_index]
        if self.play_track(track):
            self.current_track_path = track
            self.pause_position = 0
            self.was_paused = False
            self.config.current_track_index += 1
            self.config.save_state()
            return True
        
        return False
    
    def play_ad(self):
        """play an ad track in order."""
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
        """resume playback from paused position."""
        if not self.was_paused or not self.current_track_path or self.pause_position <= 0:
            return False
        
        logger.info(f"resuming {Path(self.current_track_path).name} from {int(self.pause_position)}s")
        success = self.play_track(self.current_track_path, self.pause_position)
        if success:
            self.was_paused = False
        return success
    
    def resume(self):
        """resume playback using vlc pause toggle."""
        try:
            if self.player:
                self.player.pause()
                return True
        except Exception as e:
            logger.error(f"failed to resume: {e}")
        return False
    
    def pause(self):
        """pause playback and save position."""
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
        """stop playback but preserve track path for potential resume."""
        if self.player:
            self.player.stop()
    
    def is_playing(self):
        """check if player is actually playing."""
        try:
            return self.player and self.player.is_playing()
        except:
            return False
    
    def wait_for_playback(self):
        """wait for current playback to complete."""
        try:
            while self.is_playing():
                time.sleep(0.5)
        except:
            pass
    
    def cleanup(self):
        """cleanup vlc resources."""
        if self.player:
            try:
                self.player.stop()
                self.player.release()
            except:
                pass