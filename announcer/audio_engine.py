"""
Real-time streaming audio playback engine using sounddevice, soundfile, numpy, and scipy.
Features:
- Continuous low-latency audio streaming via PortAudio (sounddevice).
- True real-time Cabin PA Speaker DSP filter: adjusting presence, mode, or toggling
  the filter updates the currently playing audio INSTANTLY chunk-by-chunk.
- Separate announcement and boarding music playback streams with auto-ducking.
- No overlap / overrunning: starting a new announcement cleanly crossfades / interrupts
  previous announcements.
"""

import os
import math
import time
import threading
import logging
import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf
    import scipy.signal as signal
    AUDIO_STREAM_AVAILABLE = True
except ImportError:
    AUDIO_STREAM_AVAILABLE = False

logger = logging.getLogger("CabinAnnouncer.Audio")

class AudioEngine:
    def __init__(self, sample_rate=44100, master_vol=0.8, announcement_vol=1.0, music_vol=0.5):
        self.sample_rate = sample_rate
        self.master_vol = float(master_vol)
        self.announcement_vol = float(announcement_vol)
        self.music_vol = float(music_vol)
        self._lock = threading.Lock()
        
        # Cabin PA Filter settings
        self.pa_filter_enabled = True
        self.pa_filter_mode = "cabin"  # "cabin", "intercom", "clean"
        self.pa_filter_intensity = 0.90  # 0.0 to 1.0
        self.filter_music = False

        # Precompute filter coefficients for 44.1kHz
        self._init_filters()

        # Buffers and playback state
        # Audio data is stored as float32 numpy array with shape (N, 2)
        self._announcement_buf = None
        self._announcement_cursor = 0
        self.current_announcement_file = None

        self._music_buf = None
        self._music_cursor = 0
        self._music_loop = True
        self.current_music_file = None

        # Cache decoded audio arrays in memory: path -> (data, sr)
        self._audio_cache = {}

        # Stream setup
        self.stream = None
        self.initialized = False
        self._init_stream()

    def _init_filters(self):
        """Initializes SOS biquad filters and state vectors for chunk processing."""
        sr = self.sample_rate
        # Cabin mode: 350Hz - 4200Hz
        self.sos_cabin = signal.butter(4, [350, 4200], btype='bandpass', fs=sr, output='sos')
        self.zi_cabin = signal.sosfilt_zi(self.sos_cabin)
        self.zi_cabin = np.repeat(self.zi_cabin[:, :, np.newaxis], 2, axis=2)

        # Intercom mode: 450Hz - 3600Hz
        self.sos_intercom = signal.butter(4, [450, 3600], btype='bandpass', fs=sr, output='sos')
        self.zi_intercom = signal.sosfilt_zi(self.sos_intercom)
        self.zi_intercom = np.repeat(self.zi_intercom[:, :, np.newaxis], 2, axis=2)

        # Presence peak filters
        b, a = signal.iirpeak(2100, 1.8, fs=sr)
        self.peak_b_cabin = b
        self.peak_a_cabin = a

        b_i, a_i = signal.iirpeak(2400, 2.2, fs=sr)
        self.peak_b_intercom = b_i
        self.peak_a_intercom = a_i

    def _init_stream(self):
        if not AUDIO_STREAM_AVAILABLE:
            logger.error("sounddevice/soundfile not available. Audio playback disabled.")
            return

        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=2,
                blocksize=1024,
                callback=self._audio_callback
            )
            self.stream.start()
            self.initialized = True
            logger.info("Real-time AudioEngine stream started successfully.")
        except Exception as e:
            logger.error(f"Failed to start sounddevice OutputStream: {e}")
            self.initialized = False

    def _load_audio_file(self, file_path):
        """Loads and converts any audio file (.ogg, .wav, etc.) into a 44.1kHz float32 stereo array."""
        if file_path in self._audio_cache:
            return self._audio_cache[file_path]

        try:
            data, sr = sf.read(file_path, dtype='float32')
            # Ensure 2 channels (stereo)
            if data.ndim == 1:
                data = np.column_stack((data, data))
            elif data.shape[1] > 2:
                data = data[:, :2]

            # Resample to stream sample rate if different
            if sr != self.sample_rate:
                gcd = math.gcd(self.sample_rate, sr)
                up = self.sample_rate // gcd
                down = sr // gcd
                data = signal.resample_poly(data, up, down, axis=0)

            # Limit cache size to 60 loaded files
            if len(self._audio_cache) > 60:
                self._audio_cache.clear()

            self._audio_cache[file_path] = data
            return data
        except Exception as e:
            logger.error(f"Error loading audio file {file_path}: {e}")
            return None

    def _audio_callback(self, outdata, frames, time_info, status):
        """
        Real-time audio callback called by PortAudio every ~23ms.
        Processes chunks and dynamically applies real-time filters and volumes.
        """
        # Start with silence
        outdata.fill(0)

        with self._lock:
            # 1. Process Boarding Music (if playing)
            music_active = False
            if self._music_buf is not None and self._music_cursor < len(self._music_buf):
                rem = len(self._music_buf) - self._music_cursor
                chunk_len = min(frames, rem)
                m_chunk = self._music_buf[self._music_cursor : self._music_cursor + chunk_len]
                self._music_cursor += chunk_len

                # Loop if enabled
                if self._music_cursor >= len(self._music_buf) and self._music_loop:
                    self._music_cursor = 0

                # Auto-ducking: if an announcement is also playing, reduce music volume
                ducking = 0.35 if (self._announcement_buf is not None and self._announcement_cursor < len(self._announcement_buf)) else 1.0
                effective_m_vol = self.master_vol * self.music_vol * ducking

                if chunk_len < frames:
                    outdata[:chunk_len] += m_chunk * effective_m_vol
                else:
                    outdata[:] += m_chunk * effective_m_vol
                music_active = True
            elif self._music_buf is not None and self._music_cursor >= len(self._music_buf):
                self._music_buf = None
                self.current_music_file = None

            # 2. Process Cabin Announcement (if playing)
            if self._announcement_buf is not None and self._announcement_cursor < len(self._announcement_buf):
                rem = len(self._announcement_buf) - self._announcement_cursor
                chunk_len = min(frames, rem)
                raw_chunk = self._announcement_buf[self._announcement_cursor : self._announcement_cursor + chunk_len].copy()
                self._announcement_cursor += chunk_len

                # Pad chunk to 'frames' length for filter continuity if near EOF
                if chunk_len < frames:
                    padded_chunk = np.pad(raw_chunk, ((0, frames - chunk_len), (0, 0)))
                else:
                    padded_chunk = raw_chunk

                # REAL-TIME CABIN PA DSP FILTERING
                if self.pa_filter_enabled and self.pa_filter_mode != "clean":
                    intensity = self.pa_filter_intensity
                    if self.pa_filter_mode == "intercom":
                        filtered, self.zi_intercom = signal.sosfilt(self.sos_intercom, padded_chunk, zi=self.zi_intercom, axis=0)
                        # Harmonic drive
                        drive = 1.35
                        filtered = np.tanh(filtered * drive) / np.tanh(drive)
                    else:  # "cabin" overhead speaker mode
                        filtered, self.zi_cabin = signal.sosfilt(self.sos_cabin, padded_chunk, zi=self.zi_cabin, axis=0)
                        # Cabin speaker warmth & soft-clip
                        drive = 1.25
                        filtered = np.tanh(filtered * drive) / np.tanh(drive)

                    # Wet / Dry real-time mix
                    processed = (1.0 - intensity) * padded_chunk + intensity * filtered
                else:
                    processed = padded_chunk

                # Apply master & announcement volume
                effective_a_vol = self.master_vol * self.announcement_vol
                final_chunk = processed[:chunk_len] * effective_a_vol

                outdata[:chunk_len] += final_chunk
            elif self._announcement_buf is not None and self._announcement_cursor >= len(self._announcement_buf):
                self._announcement_buf = None
                self.current_announcement_file = None

        # Prevent digital clipping
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def set_master_volume(self, vol):
        """Immediately adjusts master volume in real time."""
        with self._lock:
            self.master_vol = max(0.0, min(1.0, float(vol)))

    def set_announcement_volume(self, vol):
        """Immediately adjusts announcement volume in real time."""
        with self._lock:
            self.announcement_vol = max(0.0, min(1.0, float(vol)))

    def set_music_volume(self, vol):
        """Immediately adjusts boarding music volume in real time."""
        with self._lock:
            self.music_vol = max(0.0, min(1.0, float(vol)))

    def set_pa_filter(self, enabled=True, mode="cabin", intensity=0.90, filter_music=False):
        """Immediately updates cabin speaker DSP filter parameters in real time."""
        with self._lock:
            self.pa_filter_enabled = bool(enabled)
            self.pa_filter_mode = mode
            self.pa_filter_intensity = max(0.0, min(1.0, float(intensity)))
            self.filter_music = bool(filter_music)

    def is_announcement_playing(self):
        with self._lock:
            return (self._announcement_buf is not None and self._announcement_cursor < len(self._announcement_buf))

    def is_music_playing(self):
        with self._lock:
            return (self._music_buf is not None and self._music_cursor < len(self._music_buf))

    def play_announcement(self, sound_path, chime_path=None, interrupt=True):
        """
        Plays a cabin announcement audio file.
        Interrupts any previously playing announcement cleanly without overrunning.
        """
        if not self.initialized:
            logger.warning("AudioEngine not ready.")
            return False

        if not os.path.exists(sound_path):
            logger.error(f"File not found: {sound_path}")
            return False

        def _loader():
            audio_data = self._load_audio_file(sound_path)
            if audio_data is None:
                return

            chime_data = None
            if chime_path and os.path.exists(chime_path):
                chime_data = self._load_audio_file(chime_path)

            with self._lock:
                if chime_data is not None:
                    # Prepend chime to announcement
                    combined = np.vstack((chime_data, audio_data))
                else:
                    combined = audio_data

                # Replace current announcement cleanly without overlapping
                self._announcement_buf = combined
                self._announcement_cursor = 0
                self.current_announcement_file = sound_path
                # Reset filter memory state
                self._init_filters()
                logger.info(f"Started announcement: {os.path.basename(sound_path)} (Length: {len(combined)/self.sample_rate:.1f}s)")

        t = threading.Thread(target=_loader, daemon=True)
        t.start()
        return True

    def play_boarding_music(self, sound_path, loop=True):
        """Starts background boarding music."""
        if not self.initialized:
            return False
        if not os.path.exists(sound_path):
            return False

        def _loader():
            audio_data = self._load_audio_file(sound_path)
            if audio_data is None:
                return
            with self._lock:
                self._music_buf = audio_data
                self._music_cursor = 0
                self._music_loop = loop
                self.current_music_file = sound_path
                logger.info(f"Started boarding music: {os.path.basename(sound_path)}")

        t = threading.Thread(target=_loader, daemon=True)
        t.start()
        return True

    def stop_announcement(self):
        with self._lock:
            self._announcement_buf = None
            self._announcement_cursor = 0
            self.current_announcement_file = None

    def stop_music(self):
        with self._lock:
            self._music_buf = None
            self._music_cursor = 0
            self.current_music_file = None

    def stop_all(self):
        with self._lock:
            self._announcement_buf = None
            self._announcement_cursor = 0
            self.current_announcement_file = None
            self._music_buf = None
            self._music_cursor = 0
            self.current_music_file = None
