import time
import threading
import logging
import os
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class DisplayManager:
    def __init__(self, config_manager, vlc_player=None, fb_path='/dev/fb1'):
        self.config = config_manager
        self.vlc_player = vlc_player
        self.fb_path = fb_path
        self.width = 480
        self.height = 320
        self.running = False
        self.thread = None
        
        self.current_display_track = None
        self.last_volume = None
        self.last_song_progress = None
        self.is_playing_ad = False
        self.ad_track_name = None
        self.ad_start_time = 0
        self.ad_duration = 0
        self.last_update_time = 0
        
        if not os.path.exists(fb_path):
            logger.warning(f"framebuffer {fb_path} not found. display disabled.")
            self.available = False
        else:
            self.available = True
            
        if self.available:
            self._init_fonts()

    def _init_fonts(self):
        try:
            base = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
            self.font_header = ImageFont.truetype(f"{base}-Bold.ttf", 16)
            self.font_hero = ImageFont.truetype(f"{base}-Bold.ttf", 24)
            self.font_sub = ImageFont.truetype(f"{base}.ttf", 18)
            self.font_mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 22)
            self.font_small = ImageFont.truetype(f"{base}.ttf", 14)
            logger.info("fonts loaded successfully")
        except Exception as e:
            logger.error(f"failed to load fonts: {e}, using defaults")
            self.font_header = ImageFont.load_default()
            self.font_hero = ImageFont.load_default()
            self.font_sub = ImageFont.load_default()
            self.font_mono = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def _pack_rgb565(self, image):
        pixels = image.getdata()
        return b''.join([
            int(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).to_bytes(2, 'little')
            for r, g, b in pixels
        ])

    def start(self):
        if not self.available: 
            return
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        logger.info("display manager started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def set_ad_playing(self, is_playing, ad_name=None, ad_duration=0):
        self.is_playing_ad = is_playing
        if is_playing:
            self.ad_track_name = ad_name
            self.ad_start_time = time.time()
            self.ad_duration = ad_duration
            logger.info(f"display: now playing ad - {ad_name}")
        else:
            self.ad_track_name = None
            self.ad_start_time = 0
            self.ad_duration = 0
            logger.info("display: ad finished")

    def _get_current_track_info(self):
        if self.is_playing_ad and self.ad_track_name:
            try:
                ad_name = self.ad_track_name
                if '/' in ad_name:
                    ad_name = ad_name.split('/')[-1]
                if '.' in ad_name:
                    ad_name = ad_name.rsplit('.', 1)[0]
                ad_name = ad_name.replace('ad_', '').replace('_', ' ').strip()
                if ad_name:
                    return f"ad: {ad_name.title()}"
                else:
                    return "advertisement"
            except:
                return "advertisement"
        
        if self.vlc_player and self.vlc_player.current_track_path:
            try:
                track_path = self.vlc_player.current_track_path
                filename = os.path.basename(track_path)
                if '.' in filename:
                    filename = filename.rsplit('.', 1)[0]
                filename = filename.replace('main_', '').replace('_', ' ').strip()
                filename = ' '.join(word.capitalize() for word in filename.split())
                return filename if filename else "now playing"
            except Exception as e:
                logger.debug(f"error extracting track name: {e}")
        
        if self.config.main_playlist and self.config.current_track_index < len(self.config.main_playlist):
            try:
                url = self.config.main_playlist[self.config.current_track_index]
                name = url.split('/')[-1]
                if '.' in name:
                    name = name.rsplit('.', 1)[0]
                name = name.replace('_', ' ').replace('main ', '').strip()
                name = ' '.join(word.capitalize() for word in name.split())
                return name if name else "next track"
            except:
                pass
        
        return "ready to play"

    def _get_song_progress(self):
        if not self.vlc_player or not self.vlc_player.player:
            return None, None
        
        try:
            if self.vlc_player.player.is_playing():
                current_ms = self.vlc_player.player.get_time()
                length_ms = self.vlc_player.player.get_length()
                
                if current_ms >= 0 and length_ms > 0:
                    current_sec = current_ms / 1000
                    length_sec = length_ms / 1000
                    return current_sec, length_sec
        except Exception as e:
            logger.debug(f"error getting song progress: {e}")
        
        return None, None

    def _format_time(self, seconds):
        if seconds is None or seconds < 0:
            return "--:--"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _update_loop(self):
        last_ad_timer_value = self.config.total_playback_time_since_last_ad
        force_update_count = 0
        
        while self.running:
            try:
                current_track_display = self._get_current_track_info()
                current_vol = self.config.volume
                current_pos, total_len = self._get_song_progress()
                current_ad_timer = self.config.total_playback_time_since_last_ad
                
                track_changed = current_track_display != self.current_display_track
                volume_changed = current_vol != self.last_volume
                progress_changed = (current_pos, total_len) != self.last_song_progress
                ad_timer_changed = current_ad_timer != last_ad_timer_value
                
                force_update_count += 1
                force_update = force_update_count >= 30
                
                if (track_changed or volume_changed or progress_changed or 
                    ad_timer_changed or force_update):
                    
                    if track_changed:
                        logger.info(f"display: track changed from '{self.current_display_track}' to '{current_track_display}'")
                    
                    self._render_full_screen(current_track_display)
                    self.current_display_track = current_track_display
                    self.last_song_progress = (current_pos, total_len)
                    last_ad_timer_value = current_ad_timer
                    
                    if force_update:
                        force_update_count = 0
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"display error: {e}")
                time.sleep(5)

    def _render_full_screen(self, track_name):
        self.last_volume = self.config.volume
        
        image = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(image)

        draw.rectangle([(0, 0), (self.width, 35)], fill="#1a1a2e")
        
        device_id = self.config.mac_address or "unknown"
        draw.text((10, 8), f"id: {device_id}", font=self.font_header, fill="#00d9ff")
        
        vol_text = f"vol: {self.last_volume}"
        vol_width = draw.textlength(vol_text, font=self.font_header)
        draw.text((self.width - vol_width - 10, 8), vol_text, font=self.font_header, fill="#ffffff")
        
        words = track_name.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if draw.textlength(test_line, font=self.font_hero) < (self.width - 30):
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        y = 55
        for line in lines[:3]:
            text_width = draw.textlength(line, font=self.font_hero)
            draw.text(((self.width - text_width) // 2, y), line, font=self.font_hero, fill="#ffd700")
            y += 32

        progress_y = 165
        bar_width = self.width - 40
        bar_height = 12
        bar_x = 20
        
        current_pos, total_len = self._get_song_progress()
        
        if current_pos is not None and total_len is not None and total_len > 0:
            draw.rectangle([(bar_x, progress_y), (bar_x + bar_width, progress_y + bar_height)], 
                          fill="#333333", outline="#555555", width=1)
            
            progress_ratio = min(current_pos / total_len, 1.0)
            filled_width = int(bar_width * progress_ratio)
            if filled_width > 0:
                draw.rectangle([(bar_x, progress_y), (bar_x + filled_width, progress_y + bar_height)], 
                              fill="#00d9ff")
            
            time_y = progress_y + 18
            elapsed_text = self._format_time(current_pos)
            total_text = self._format_time(total_len)
            remaining_sec = total_len - current_pos
            remaining_text = self._format_time(remaining_sec)
            
            draw.text((bar_x, time_y), elapsed_text, font=self.font_small, fill="#aaaaaa")
            
            remaining_label = f"- {remaining_text}"
            remaining_width = draw.textlength(remaining_label, font=self.font_sub)
            draw.text(((self.width - remaining_width) // 2, time_y - 2), 
                     remaining_label, font=self.font_sub, fill="#ffffff")
            
            total_width = draw.textlength(total_text, font=self.font_small)
            draw.text((self.width - bar_x - total_width, time_y), 
                     total_text, font=self.font_small, fill="#aaaaaa")
        else:
            draw.rectangle([(bar_x, progress_y), (bar_x + bar_width, progress_y + bar_height)], 
                          fill="#222222", outline="#444444", width=1)
            no_song_text = "- ready to play -"
            text_width = draw.textlength(no_song_text, font=self.font_small)
            draw.text(((self.width - text_width) // 2, progress_y + 18), 
                     no_song_text, font=self.font_small, fill="#666666")

        footer_y = 240
        draw.rectangle([(0, footer_y), (self.width, self.height)], fill="#0f0f1e")
        draw.line((0, footer_y, self.width, footer_y), fill="#333333", width=2)
        
        if self.is_playing_ad:
            self._draw_ad_progress(draw, footer_y)
        else:
            self._draw_ad_countdown(draw, footer_y)

        try:
            with open(self.fb_path, 'wb') as f:
                f.write(self._pack_rgb565(image))
        except Exception as e:
            logger.debug(f"framebuffer write error: {e}")

    def _draw_ad_countdown(self, draw, y_offset):
        elapsed = self.config.total_playback_time_since_last_ad
        interval = self.config.playback_interval * 60
        
        # Calculate remaining time (allowing negative values for Overtime)
        remaining = interval - elapsed
        
        # Calculate absolute values for display formatting
        abs_remaining = abs(remaining)
        countdown_mins = int(abs_remaining // 60)
        countdown_secs = int(abs_remaining % 60)
        
        if remaining < 0:
            # OVERTIME MODE (Negative Time)
            timer_text = f"-{countdown_mins}:{countdown_secs:02d}"
            color = "#ff3333" # Urgent Red
            label_text = "ad pending..."
        else:
            # NORMAL COUNTDOWN MODE
            timer_text = f"{countdown_mins}:{countdown_secs:02d}"
            label_text = "next ad break in:"
            
            if remaining > 120:
                color = "#00ff88" # Green
            elif remaining > 60:
                color = "#ffaa00" # Orange
            else:
                color = "#ff3333" # Red
        
        label_width = draw.textlength(label_text, font=self.font_sub)
        draw.text(((self.width - label_width) // 2, y_offset + 15), 
                 label_text, font=self.font_sub, fill="#888888")
        
        timer_width = draw.textlength(timer_text, font=self.font_mono)
        draw.text(((self.width - timer_width) // 2, y_offset + 40), 
                 timer_text, font=self.font_mono, fill=color)

    def _draw_ad_progress(self, draw, y_offset):
        if self.ad_duration > 0:
            current_time = time.time() - self.ad_start_time
            progress_ratio = min(current_time / self.ad_duration, 1.0)
            remaining = max(0, self.ad_duration - current_time)
        else:
            progress_ratio = 0
            remaining = 0
        
        remaining_mins = int(remaining // 60)
        remaining_secs = int(remaining % 60)
        timer_text = f"{remaining_mins}:{remaining_secs:02d}"
        
        label_text = "advertisement:"
        label_width = draw.textlength(label_text, font=self.font_sub)
        draw.text(((self.width - label_width) // 2, y_offset + 15), 
                 label_text, font=self.font_sub, fill="#888888")
        
        timer_width = draw.textlength(timer_text, font=self.font_mono)
        draw.text(((self.width - timer_width) // 2, y_offset + 40), 
                 timer_text, font=self.font_mono, fill="#ff4444")
        
        bar_y = y_offset + 70
        bar_width = self.width - 40
        bar_height = 8
        bar_x = 20
        
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], 
                      fill="#333333", outline="#555555", width=1)
        
        if progress_ratio > 0:
            filled_width = int(bar_width * progress_ratio)
            draw.rectangle([(bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height)], 
                          fill="#ff4444")
