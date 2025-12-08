#!/usr/bin/env python3
"""
Raspberry Pi Audio Player - Main entry point
"""

import sys
import os
import threading
import time
import logging
import socket
from pathlib import Path

from vlc_player import VLCPlayer
from api_client import APIClient
from config_manager import ConfigManager

IS_DOCKER = Path('/.dockerenv').exists()

if IS_DOCKER:
    BASE_DIR = Path("/usr/src/app")
    PERSISTENT_DIR = Path("/data")
else:
    BASE_DIR = Path.cwd()
    PERSISTENT_DIR = BASE_DIR / "data"

IS_SERVICE = Path('/opt/audio-player/player.py').exists()

if IS_SERVICE:
    # Service mode paths
    BASE_DIR = Path("/opt/audio-player")
    PERSISTENT_DIR = Path("/var/lib/audio-player")
    LOG_DIR = Path("/var/log/audio-player")
    
    # Create directories with proper permissions
    PERSISTENT_DIR.mkdir(exist_ok=True, parents=True)
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    
    # Log files in service location
    log_file = LOG_DIR / "player.log"
    error_log_file = LOG_DIR / "player-error.log"
else:
    # Manual mode paths (your existing code)
    BASE_DIR = Path.cwd()
    PERSISTENT_DIR = BASE_DIR / "data"
    LOG_DIR = BASE_DIR
    
    # Create directories
    PERSISTENT_DIR.mkdir(exist_ok=True, parents=True)
    
    # Log files in current directory
    log_file = LOG_DIR / "player.log"
    error_log_file = LOG_DIR / "player-error.log"

# BASE_DIR.mkdir(exist_ok=True, parents=True)
PERSISTENT_DIR.mkdir(exist_ok=True, parents=True)

TEST_MODE = False
TEST_SERVER_PORT = 9999
TEST_AD_INTERVAL = 1

log_file = BASE_DIR / "player.log"
error_log_file = BASE_DIR / "player-error.log"

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='a'),
        logging.FileHandler(error_log_file, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"running in {'service' if IS_SERVICE else 'local'} mode")
logger.info(f"base dir: {BASE_DIR}")
logger.info(f"persistent dir: {PERSISTENT_DIR}")
logger.info(f"log dir: {LOG_DIR}")

class AudioPlayer:
    def __init__(self):
        """initialize the audio player components."""
        self.config = ConfigManager(BASE_DIR, PERSISTENT_DIR)
        self.api = APIClient(self.config)
        self.vlc_player = VLCPlayer(self.config, self.api)
        
        self.is_playing = False
        self.is_paused = False
        self.stop_flag = False
        self.should_refresh = False
        
        self.pending_commands = []
        self.is_playing_ad = False
        
        self.command_thread = None
        self.heartbeat_thread = None
        self.stop_event = threading.Event()
        
        logger.info("audio player initialized")
    
    def check_network(self):
        """check if network is available."""
        return self.api.check_network()
    
    def get_current_status(self):
        """get current player status."""
        if self.is_playing_ad:
            return "playing_ad"
        elif self.is_playing and not self.is_paused:
            return "playing_track"
        elif self.is_paused:
            return "paused"
        else:
            return "stopped"
    
    def handle_command(self, command):
        """handle commands from api with proper deferral and execution."""
        logger.info(f"processing command: {command}")
        
        if self.is_playing_ad:
            logger.info(f"deferring '{command}' until ad completes")
            self.pending_commands.append(command)
            status = f"{command}_deferred|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
            return
        
        if command == "play":
            if self.is_paused:
                self.vlc_player.resume()
                self.is_paused = False
                self.is_playing = True
                logger.info("playback resumed from pause")
            elif not self.is_playing:
                self.is_playing = True
                logger.info("playback started")
            else:
                logger.info("already playing")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "pause":
            if self.is_playing and not self.is_paused:
                self.vlc_player.pause()
                self.is_paused = True
                self.is_playing = False
                logger.info("playback paused")
            else:
                logger.info("already paused or not playing")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "stop":
            self.vlc_player.stop()
            self.is_playing = False
            self.is_paused = False
            self.config.current_track_index = 0
            self.config.total_playback_time_since_last_ad = 0
            self.config.save_state()
            logger.info("playback stopped")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "next":
            self.vlc_player.stop()
            cached_tracks = self.config.get_cached_tracks('main')
            if cached_tracks:
                if self.config.current_track_index >= len(cached_tracks):
                    self.config.current_track_index = 0
            self.config.save_state()
            time.sleep(0.05)
            logger.info("skipping to next track")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "previous":
            self.vlc_player.stop()
            cached_tracks = self.config.get_cached_tracks('main')
            if cached_tracks:
                self.config.current_track_index = max(0, self.config.current_track_index - 2)
                if self.config.current_track_index < 0:
                    self.config.current_track_index = len(cached_tracks) - 1
            self.config.save_state()
            time.sleep(0.05)
            logger.info("going to previous track")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "refresh":
            logger.info("refresh requested - updating content")
            self.should_refresh = True
            self.config.total_playback_time_since_last_ad = 0
            self.config.save_state()
            logger.info("playback timer reset due to refresh")
            
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
        
        elif command == "reboot":
            logger.warning("reboot command received - rebooting in 10 seconds")
            status = f"{command}_executed|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
            
            def schedule_reboot():
                time.sleep(10)
                logger.critical("system rebooting now")
                import subprocess
                try:
                    subprocess.run(['reboot'], check=True)
                except Exception as e:
                    logger.error(f"failed to reboot: {e}")
            
            reboot_thread = threading.Thread(target=schedule_reboot, daemon=True)
            reboot_thread.start()
            time.sleep(2)
        
        else:
            logger.warning(f"unknown command: {command}")
            status = f"{command}_unknown|{self.get_current_status()}"
            threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True).start()
    
    def process_pending_commands(self):
        """process deferred commands, removing duplicate plays and keeping only important ones."""
        if not self.pending_commands:
            return
        
        cleaned_commands = []
        has_stop = False
        has_next = False
        has_prev = False
        has_pause = False
        play_count = 0
        
        for cmd in self.pending_commands:
            if cmd == "stop":
                has_stop = True
                cleaned_commands = ["stop"]
                break
            elif cmd == "next":
                has_next = True
                cleaned_commands.append(cmd)
            elif cmd == "previous":
                has_prev = True
                cleaned_commands.append(cmd)
            elif cmd == "pause":
                has_pause = True
                cleaned_commands.append(cmd)
            elif cmd == "play":
                play_count += 1
        
        if not has_stop and not has_next and not has_prev and play_count > 0:
            cleaned_commands.insert(0, "play")
        
        if cleaned_commands:
            logger.info(f"processing {len(cleaned_commands)} deferred command(s) (filtered from {len(self.pending_commands)})")
            for cmd in cleaned_commands:
                logger.info(f"executing deferred command: {cmd}")
                self.handle_command(cmd)
                time.sleep(0.1)
        
        self.pending_commands.clear()
    
    def command_poller_safe(self):
        """poll for commands from api."""
        logger.info("command poller started")
        
        while not self.stop_event.is_set():
            try:
                if self.check_network():
                    data = self.api.make_api_request_safe('command', method='GET', cache_bust=True)
                    if data and 'command' in data:
                        command = data['command'].lower()
                        
                        if command != 'none':
                            logger.info(f"command received: '{command}'")
                            self.handle_command(command)
            
            except Exception as e:
                logger.debug(f"poller error: {e}")
            
            for _ in range(10):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
    
    def heartbeat_sender(self):
        """send periodic heartbeat with status."""
        logger.info("heartbeat sender started")
        
        while not self.stop_event.is_set():
            try:
                status = self.get_current_status()
                result = self.api.send_heartbeat(status)
                if result:
                    logger.info(f"heartbeat sent: {status}")
                else:
                    logger.debug(f"heartbeat failed: {status}")
            except Exception as e:
                logger.debug(f"heartbeat error: {e}")
            
            for _ in range(10):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
    
    def log_time_progress(self, playback_time):
        """log time progress every minute."""
        playback_minutes = int(playback_time / 60)
        
        if playback_minutes > self.config.last_minute_log:
            self.config.last_minute_log = playback_minutes
            minutes_until_ad = max(0, self.config.playback_interval - playback_minutes)
            
            logger.info(f"[timer] {playback_minutes} min playback | {minutes_until_ad} min until ad")
            
            if minutes_until_ad <= 1:
                seconds_until_ad = max(0, (self.config.playback_interval * 60) - playback_time)
                logger.info(f"[timer] ad in {int(seconds_until_ad)} seconds")
   
    def play_ad(self):
        """play an ad and handle state properly."""
        if not self.config.ads_enabled:
            return
        
        cached_ads = self.config.get_cached_tracks('ad')
        if not cached_ads:
            logger.debug("no ads available")
            self.config.total_playback_time_since_last_ad = 0
            self.config.save_state()
            return
        
        playback_minutes = int(self.config.total_playback_time_since_last_ad / 60)
        logger.info(f"playing ad after {playback_minutes} minutes of playback")
        
        self.is_playing_ad = True
        
        main_was_paused = self.vlc_player.was_paused
        main_pause_position = self.vlc_player.pause_position
        main_track_path = self.vlc_player.current_track_path
        
        logger.info(f"saved state before ad: was_paused={main_was_paused}, position={int(main_pause_position) if main_pause_position else 0}s, track={main_track_path}")
        
        if self.vlc_player.play_ad():
            logger.info("ad started")
            
            self.vlc_player.wait_for_playback()
            
            self.is_playing_ad = False
            self.config.total_playback_time_since_last_ad = 0
            self.config.last_minute_log = 0
            self.config.save_state()
            logger.info("ad completed, timer reset")
            
            self.vlc_player.was_paused = main_was_paused
            self.vlc_player.pause_position = main_pause_position
            self.vlc_player.current_track_path = main_track_path
            
            logger.info(f"restored state after ad: was_paused={self.vlc_player.was_paused}, position={int(self.vlc_player.pause_position) if self.vlc_player.pause_position else 0}s, track={self.vlc_player.current_track_path}")
            
            if self.pending_commands:
                logger.info("processing deferred commands")
                self.process_pending_commands()
    
    def start_audio_loop(self):
        """main audio playback loop."""
        logger.info("starting audio playback loop")
        
        time.sleep(1)
        self.is_playing = True
        
        self.config.total_playback_time_since_last_ad = 0
        self.config.save_state()
        logger.info("playback timer reset")
        
        self.config.last_minute_log = 0
        
        while not self.stop_flag:
            try:
                self.api.check_volume_update()
                
                if self.should_refresh:
                    logger.info("performing refresh...")
                    self.api.sync_tracks_safe()
                    self.should_refresh = False
                
                if self.is_playing and not self.is_paused and not self.vlc_player.is_playing():
                    if self.vlc_player.was_paused and self.vlc_player.pause_position > 0 and self.vlc_player.current_track_path:
                        if self.vlc_player.resume_from_pause():
                            logger.info("resumed from pause position")
                            self.vlc_player.was_paused = False
                            self.wait_for_current_playback()
                            continue
                        else:
                            logger.warning("resume failed, playing next track")
                    
                    if self.vlc_player.play_next_track():
                        self.wait_for_current_playback()
                    else:
                        logger.warning("failed to play track, retrying in 3s")
                        time.sleep(3)
                
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"audio loop error: {e}")
                time.sleep(3)
    
    def wait_for_current_playback(self):
        """wait for current playback to complete and track time."""
        try:
            while self.vlc_player.is_playing():
                if self.stop_flag or self.should_refresh:
                    break
                
                if not self.is_paused:
                    current_time = time.time()
                    if self.config.last_playback_check_time > 0:
                        elapsed = current_time - self.config.last_playback_check_time
                        self.config.total_playback_time_since_last_ad += elapsed
                    self.config.last_playback_check_time = current_time
                    
                    self.log_time_progress(self.config.total_playback_time_since_last_ad)
                    
                    if (self.config.ads_enabled and 
                        self.config.total_playback_time_since_last_ad >= (self.config.playback_interval * 60)):
                        
                        playback_minutes = int(self.config.total_playback_time_since_last_ad / 60)
                        logger.info(f"[ad time] {playback_minutes} minutes - playing ad")
                        
                        saved_track_path = self.vlc_player.current_track_path
                        saved_pause_pos = 0
                        
                        if self.vlc_player.player and self.vlc_player.player.is_playing():
                            try:
                                track_position = self.vlc_player.player.get_time() / 1000.0
                                saved_pause_pos = track_position
                                logger.info(f"paused track at {int(track_position)}s (track position) before ad")
                            except:
                                logger.warning("could not get track position, will start fresh after ad")
                        
                        self.vlc_player.stop()
                        time.sleep(0.1)
                        
                        self.vlc_player.was_paused = True
                        self.vlc_player.pause_position = saved_pause_pos
                        self.vlc_player.current_track_path = saved_track_path
                        
                        self.play_ad()
                        return
                
                time.sleep(0.5)
                
        except Exception as e:
            logger.debug(f"player monitoring error: {e}")
        finally:
            self.config.last_playback_check_time = 0
    
    def cleanup(self):
        """cleanup resources."""
        logger.info("cleaning up...")
        self.stop_flag = True
        self.stop_event.set()
        
        try:
            status = "shutdown"
            heartbeat_thread = threading.Thread(target=self.api.send_heartbeat, args=(status,), daemon=True)
            heartbeat_thread.start()
            heartbeat_thread.join(timeout=1)
        except:
            pass
        
        self.vlc_player.cleanup()
        
        if self.command_thread:
            self.command_thread.join(timeout=2)
        
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        
        logger.info("cleanup completed")
    
    def run(self):
        """main run method."""
        try:
            self.config.load_mac_address()
            
            if not self.vlc_player.init_vlc():
                logger.error("failed to initialize vlc")
                return
            
            if self.api.setup_device():
                logger.info("device setup successful")
                self.vlc_player.set_volume_smooth(self.config.volume)
                
                if TEST_MODE:
                    self.config.playback_interval = TEST_AD_INTERVAL
                    logger.info(f"TEST MODE: ad interval set to {TEST_AD_INTERVAL} minute(s)")
            else:
                logger.warning("device setup failed, continuing with limited functionality")
            
            self.config.load_state()
            
            download_thread = threading.Thread(target=self.api.download_all_tracks, daemon=True)
            download_thread.start()
            
            self.command_thread = threading.Thread(target=self.command_poller_safe, daemon=True)
            self.command_thread.start()
            
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_sender, daemon=True)
            self.heartbeat_thread.start()
            
            logger.info("starting main audio playback loop...")
            self.start_audio_loop()
            
        except KeyboardInterrupt:
            logger.info("shutdown requested by user")
        except Exception as e:
            logger.error(f"fatal error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.cleanup()
            logger.info("player shutdown complete")

if __name__ == "__main__":
    os.chdir(str(BASE_DIR))
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        TEST_MODE = True
        logger.info("test mode enabled")
    
    player = AudioPlayer()
    player.run()