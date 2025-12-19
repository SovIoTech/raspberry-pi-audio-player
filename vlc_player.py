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

    # ---------------------------------------------------------
    # Audio device detection
    # ---------------------------------------------------------
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

            hdmi_patterns = ['hdmi', 'vc4hdmi', 'vc4-hdmi']

            for pattern, desc in headphone_patterns:
                match = re.search(pattern, output, re.IGNORECASE)
                if match:
                    card = match.group(1)
                    line = match.group(0)
                    if not any(h in line.lower() for h in hdmi_patterns):
                        device = f'hw:{card},0'
                        logger.info(f"auto-detected {desc} at card {card}")
                        return device

            logger.info("no specific audio device detected, using default")
            return 'hw:0,0'

        except Exception as e:
            logger.warning(f"audio device detection failed: {e}")
            return 'hw:0,0'

    # ---------------------------------------------------------
    # VLC init
    # ---------------------------------------------------------
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
            self.player = self.instance.media_player_new()
            logger.info(f"vlc initialized using {alsa_device}")
            return True

        except Exception as e:
            logger.error(f"vlc init failed: {e}")
            return False

    # ---------------------------------------------------------
    # 🔥 SINGLE AUTHORITATIVE VOLUME ENFORCEMENT
    # ---------------------------------------------------------

    def enforce_volume(self, smooth=True):
        """Apply volume reliably, retrying if VLC reports -1"""
        if not self.player:
            logger.debug("[VOLUME] player not initialized")
            return

        if not self.player.is_playing():
            logger.debug("[VOLUME] enforce skipped (player not playing)")
            return

        try:
            target = max(10, min(100, int(self.config.volume) * 10))

            # Wait/retry until VLC reports valid volume
            for attempt in range(3):  # 3 retries
                current = self.player.audio_get_volume()
                if current >= 0:
                    break
                logger.debug(f"[VOLUME] invalid volume (-1), retry {attempt+1}/3")
                time.sleep(1)  # wait 1 second between retries
            else:
                logger.warning("[VOLUME] volume still invalid after 3 retries, forcing target")
                current = target

            logger.info(f"[VOLUME] enforcing volume: target={target}%, current={current}%, smooth={smooth}")

            if not smooth or abs(current - target) < 2:
                self.player.audio_set_volume(target)
                time.sleep(0.05)
            else:
                step = 2 if target > current else -2
                for vol in range(current, target, step):
                    self.player.audio_set_volume(vol)
                    logger.debug(f"[VOLUME] ramp → {vol}%")
                    time.sleep(0.05)
                self.player.audio_set_volume(target)

            # Verify
            time.sleep(0.05)
            verified = self.player.audio_get_volume()
            if verified != target:
                logger.warning(f"[VOLUME] mismatch after set: wanted={target}% got={verified}%")
            else:
                logger.info(f"[VOLUME] volume locked at {verified}%")

        except Exception as e:
            logger.error(f"[VOLUME] enforcement failed: {e}")


    # ---------------------------------------------------------
    # Playback
    # ---------------------------------------------------------
    def play_track(self, filepath, start_position=0):
        if not filepath or not Path(filepath).exists():
            logger.error(f"track not found: {filepath}")
            return False

        try:
            if self.player.is_playing():
                self.player.stop()
                time.sleep(0.05)

            media = self.instance.media_new(filepath)
            self.player.set_media(media)
            self.player.play()

            # Wait until pipeline is live
            for _ in range(20):
                if self.player.is_playing():
                    break
                time.sleep(0.05)

            if not self.player.is_playing():
                return False

            if start_position > 0:
                self.player.set_time(int(start_position * 1000))

            self.current_track_path = filepath

            # 🔥 APPLY VOLUME HERE AND ONLY HERE
            self.enforce_volume(smooth=True)

            logger.info(
                f"playing: {Path(filepath).name}"
                + (f" from {int(start_position)}s" if start_position > 0 else "")
            )

            return True

        except Exception as e:
            logger.error(f"play error: {e}")
            return False

    def play_next_track(self):
        tracks = self.config.get_cached_tracks('main')
        if not tracks:
            return False

        if self.config.current_track_index >= len(tracks):
            self.config.current_track_index = 0

        for _ in range(len(tracks)):
            track = tracks[self.config.current_track_index]
            self.config.current_track_index = (self.config.current_track_index + 1) % len(tracks)
            self.config.save_state()

            if self.play_track(track):
                self.pause_position = 0
                self.was_paused = False
                return True

        return False

    def play_ad(self):
        ads = self.config.get_cached_tracks('ad')
        if not ads:
            return False

        if self.config.current_ad_index >= len(ads):
            self.config.current_ad_index = 0

        ad = ads[self.config.current_ad_index]
        success = self.play_track(ad)

        if success:
            self.config.current_ad_index += 1
            self.config.save_state()

        return success

    # ---------------------------------------------------------
    # Pause / Resume
    # ---------------------------------------------------------
    def pause(self):
        try:
            if self.player and self.player.is_playing():
                self.pause_position = self.player.get_time() / 1000
                self.player.pause()
                self.was_paused = True
                logger.info(f"paused at {int(self.pause_position)}s")
                return True
        except Exception as e:
            logger.error(f"pause failed: {e}")
        return False

    def resume_from_pause(self):
        if not self.was_paused or not self.current_track_path:
            return False

        return self.play_track(self.current_track_path, self.pause_position)

    def resume(self):
        try:
            if self.player:
                self.player.pause()
                return True
        except:
            pass
        return False

    # ---------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------
    def stop(self):
        if self.player:
            self.player.stop()
        self.was_paused = False
        self.pause_position = 0

    def is_playing(self):
        try:
            return self.player and self.player.is_playing()
        except:
            return False

    def wait_for_playback(self):
        while self.is_playing():
            time.sleep(0.5)

    def cleanup(self):
        if self.player:
            try:
                self.player.stop()
                self.player.release()
            except:
                pass

