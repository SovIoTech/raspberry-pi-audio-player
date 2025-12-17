"""
enhanced display manager - handles generic spi 3.5" lcd (320x480)
shows song name, progress, time remaining, and next ad countdown
"""
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
        
        # track display state
        self.last_track_name = None
        self.last_volume = None
        self.last_song_progress = None
        self.is_playing_ad = False
        self.ad_track_name = None
        self.ad_start_time = 0
        self.ad_duration = 0
        
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
        except:
            # fallback to default fonts
            self.font_header = ImageFont.load_default()
            self.font_hero = ImageFont.load_default()
            self.font_sub = ImageFont.load_default()
            self.font_mono = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def _pack_rgb565(self, image):
        """manual rgb565 packing to bypass pil errors on debian"""
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
        """set ad playback state for display updates"""
        self.is_playing_ad = is_playing
        if is_playing:
            self.ad_track_name = ad_name
            self.ad_start_time = time.time()
            self.ad_duration = ad_duration
        else:
            self.ad_track_name = None
            self.ad_start_time = 0
            self.ad_duration = 0

    def _get_track_name(self):
        """get current track name from playlist"""
        if self.is_playing_ad and self.ad_track_name:
            # during ad playback, show ad name
            try:
                name = self.ad_track_name.split('/')[-1].rsplit('.', 1)[0].replace('_', ' ').replace('ad_', '')
                return 'AD: ' + ' '.join(word.capitalize() for word in name.split())
            except:
                return "ADVERTISEMENT"
        
        if self.config.main_playlist and self.config.current_track_index < len(self.config.main_playlist):
            try:
                url = self.config.main_playlist[self.config.current_track_index]
                name = url.split('/')[-1].rsplit('.', 1)[0].replace('_', ' ').replace('main ', '')
                return ' '.join(word.capitalize() for word in name.split())
            except:
                pass
        return "waiting for content..."

    def _get_song_progress(self):
        """get current song position and duration from vlc player"""
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
        """format seconds to mm:ss"""
        if seconds is None or seconds < 0:
            return "--:--"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _update_loop(self):
        """main display update loop"""
        last_ad_timer_value = self.config.total_playback_time_since_last_ad
        
        while self.running:
            try:
                # get current state
                current_track = self._get_track_name()
                current_vol = self.config.volume
                current_pos, total_len = self._get_song_progress()
                current_ad_timer = self.config.total_playback_time_since_last_ad
                
                # check if anything changed
                progress_changed = (current_pos, total_len) != self.last_song_progress
                ad_timer_changed = current_ad_timer != last_ad_timer_value
                
                if (current_track != self.last_track_name or 
                    current_vol != self.last_volume or 
                    progress_changed or
                    ad_timer_changed):
                    
                    self._render_full_screen()
                    self.last_song_progress = (current_pos, total_len)
                    last_ad_timer_value = current_ad_timer
                
                time.sleep(0.5)  # update twice per second
                
            except Exception as e:
                logger.error(f"display error: {e}")
                time.sleep(5)

    def _render_full_screen(self):
        """render complete display screen"""
        self.last_track_name = self._get_track_name()
        self.last_volume = self.config.volume
        
        image = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(image)

        # === header bar ===
        draw.rectangle([(0, 0), (self.width, 35)], fill="#1a1a2e")
        
        # device id with dashes in mac address
        draw.text((10, 8), f"id: {self.config.mac_address}", font=self.font_header, fill="#00d9ff")
        
        # volume indicator
        vol_text = f"vol: {self.last_volume}"
        vol_width = draw.textlength(vol_text, font=self.font_header)
        draw.text((self.width - vol_width - 10, 8), vol_text, font=self.font_header, fill="#ffffff")
        
        # === song/ad name (word wrapped) ===
        words = self.last_track_name.split()
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
        
        # draw up to 3 lines
        y = 55
        for line in lines[:3]:
            text_width = draw.textlength(line, font=self.font_hero)
            draw.text(((self.width - text_width) // 2, y), line, font=self.font_hero, fill="#ffd700")
            y += 32

        # === progress bar ===
        progress_y = 165
        bar_width = self.width - 40
        bar_height = 12
        bar_x = 20
        
        current_pos, total_len = self._get_song_progress()
        
        if current_pos is not None and total_len is not None and total_len > 0:
            # progress bar background
            draw.rectangle([(bar_x, progress_y), (bar_x + bar_width, progress_y + bar_height)], 
                          fill="#333333", outline="#555555", width=1)
            
            # progress bar filled portion
            progress_ratio = min(current_pos / total_len, 1.0)
            filled_width = int(bar_width * progress_ratio)
            if filled_width > 0:
                draw.rectangle([(bar_x, progress_y), (bar_x + filled_width, progress_y + bar_height)], 
                              fill="#00d9ff")
            
            # time labels
            time_y = progress_y + 18
            elapsed_text = self._format_time(current_pos)
            total_text = self._format_time(total_len)
            remaining_sec = total_len - current_pos
            remaining_text = self._format_time(remaining_sec)
            
            # elapsed time (left)
            draw.text((bar_x, time_y), elapsed_text, font=self.font_small, fill="#aaaaaa")
            
            # time remaining (center)
            remaining_label = f"- {remaining_text}"
            remaining_width = draw.textlength(remaining_label, font=self.font_sub)
            draw.text(((self.width - remaining_width) // 2, time_y - 2), 
                     remaining_label, font=self.font_sub, fill="#ffffff")
            
            # total time (right)
            total_width = draw.textlength(total_text, font=self.font_small)
            draw.text((self.width - bar_x - total_width, time_y), 
                     total_text, font=self.font_small, fill="#aaaaaa")
        else:
            # no song playing - show empty bar
            draw.rectangle([(bar_x, progress_y), (bar_x + bar_width, progress_y + bar_height)], 
                          fill="#222222", outline="#444444", width=1)
            no_song_text = "- ready to play -"
            text_width = draw.textlength(no_song_text, font=self.font_small)
            draw.text(((self.width - text_width) // 2, progress_y + 18), 
                     no_song_text, font=self.font_small, fill="#666666")

        # === footer - dynamic content ===
        footer_y = 240
        draw.rectangle([(0, footer_y), (self.width, self.height)], fill="#0f0f1e")
        draw.line((0, footer_y, self.width, footer_y), fill="#333333", width=2)
        
        if self.is_playing_ad:
            # show ad progress instead of countdown
            self._draw_ad_progress(draw, footer_y)
        else:
            # show next ad countdown
            self._draw_ad_countdown(draw, footer_y)

        # write to framebuffer
        try:
            with open(self.fb_path, 'wb') as f:
                f.write(self._pack_rgb565(image))
        except Exception as e:
            logger.debug(f"framebuffer write error: {e}")

    def _draw_ad_countdown(self, draw, y_offset):
        """draw the ad countdown timer"""
        elapsed = self.config.total_playback_time_since_last_ad
        interval = self.config.playback_interval * 60
        remaining = max(0, interval - elapsed)
        
        # ADDED: Debug logging for ad countdown
        logger.debug(f"Ad countdown: elapsed={elapsed:.1f}s, interval={interval}s, remaining={remaining:.1f}s, "
                    f"interval_minutes={self.config.playback_interval}")
        
        # format countdown
        countdown_mins = int(remaining // 60)
        countdown_secs = int(remaining % 60)
        timer_text = f"{countdown_mins}:{countdown_secs:02d}"
        
        # color based on urgency
        if remaining > 120:  # > 2 minutes
            color = "#00ff88"
        elif remaining > 60:  # > 1 minute
            color = "#ffaa00"
        else:  # < 1 minute
            color = "#ff3333"
        
        # label
        label_text = "next ad break in:"
        label_width = draw.textlength(label_text, font=self.font_sub)
        draw.text(((self.width - label_width) // 2, y_offset + 15), 
                 label_text, font=self.font_sub, fill="#888888")
        
        # countdown timer
        timer_width = draw.textlength(timer_text, font=self.font_mono)
        draw.text(((self.width - timer_width) // 2, y_offset + 40), 
                 timer_text, font=self.font_mono, fill=color)

    def _draw_ad_progress(self, draw, y_offset):
        """draw ad progress when ad is playing"""
        if self.ad_duration > 0:
            current_time = time.time() - self.ad_start_time
            progress_ratio = min(current_time / self.ad_duration, 1.0)
            remaining = max(0, self.ad_duration - current_time)
        else:
            progress_ratio = 0
            remaining = 0
        
        # format time remaining
        remaining_mins = int(remaining // 60)
        remaining_secs = int(remaining % 60)
        timer_text = f"{remaining_mins}:{remaining_secs:02d}"
        
        # label
        label_text = "advertisement:"
        label_width = draw.textlength(label_text, font=self.font_sub)
        draw.text(((self.width - label_width) // 2, y_offset + 15), 
                 label_text, font=self.font_sub, fill="#888888")
        
        # time remaining
        timer_width = draw.textlength(timer_text, font=self.font_mono)
        draw.text(((self.width - timer_width) // 2, y_offset + 40), 
                 timer_text, font=self.font_mono, fill="#ff4444")
        
        # ad progress bar
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
