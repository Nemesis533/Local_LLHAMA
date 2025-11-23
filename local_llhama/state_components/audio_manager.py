"""
Audio Component Manager

Manages all audio-related components including recording, transcription, and playback.
"""

import threading
import time


class AudioComponentManager:
    """
    @brief Manages all audio-related components including recording, transcription, and playback.
    """
    def __init__(self, device, base_path, voice_dir):
        from ..Audio_Output import SoundPlayer, TextToSpeech
        from ..Audio_Input import WakeWordListener, AudioRecorderClass, NoiseFloorMonitor, AudioTranscriptionClass
        
        self.device = device
        self.noise_floor = 0
        self._noise_floor_lock = threading.Lock()

        # Initialize audio components
        self.noise_floor_monitor = NoiseFloorMonitor()
        self.awaker = WakeWordListener(self.noise_floor_monitor)
        self.recorder = AudioRecorderClass(noise_floor_monitor=self.noise_floor_monitor)
        self.transcriptor = AudioTranscriptionClass()
        self.transcriptor.init_model(device)
        
        self.sound_player = SoundPlayer(base_path)
        # Small delay to allow pygame's audio system to fully initialize
        time.sleep(0.5)
        self.speaker = TextToSpeech(voice_dir=voice_dir)

    def set_noise_floor(self, value):
        """Thread-safe setter for noise floor."""
        with self._noise_floor_lock:
            self.noise_floor = value

    def get_noise_floor(self):
        """Thread-safe getter for noise floor."""
        with self._noise_floor_lock:
            return self.noise_floor

    def pause_wake_word(self):
        """Pause wake word detection and wait for cleanup."""
        self.awaker.pause()
        time.sleep(0.5)

    def resume_wake_word(self):
        """Resume wake word detection if paused."""
        if not self.awaker.pause_event.is_set():
            self.awaker.resume()

    def record_and_transcribe(self):
        """Record audio and return transcription."""
        noise_floor_val = self.get_noise_floor()
        return self.recorder.record_audio(self.transcriptor, noise_floor_val)

    def speak_text(self, text, language):
        """Convert text to speech and play it."""
        self.speaker.speak(text, language)

    def cleanup(self):
        """Clean up audio components."""
        for attr in ("awaker", "transcriptor", "speaker"):
            if hasattr(self, attr):
                delattr(self, attr)
                setattr(self, attr, None)
