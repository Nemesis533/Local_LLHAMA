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

    def __init__(
        self, base_path, voice_dir, language_models=None, whisper_model="turbo"
    ):
        """
        @brief Initialize audio components manager.
        @param base_path Base path for sound files.
        @param voice_dir Directory containing TTS voice model files.
        @param language_models Dictionary mapping language codes to TTS model filenames.
        @param whisper_model Whisper model name to use (e.g., 'turbo', 'medium', 'small').
        """
        from ..audio_input import (
            AudioRecorderClass,
            AudioTranscriptionClass,
            NoiseFloorMonitor,
            WakeWordListener,
        )
        from ..audio_output import SoundPlayer, TextToSpeech
        from ..shared_logger import LogLevel

        log_prefix = "[Audio Manager]"
        print(f"{log_prefix} [{LogLevel.INFO.name}] Initializing audio components...")

        self.noise_floor = 0
        self._noise_floor_lock = threading.Lock()

        # Initialize audio components
        print(f"{log_prefix} [{LogLevel.INFO.name}] Creating noise floor monitor...")
        self.noise_floor_monitor = NoiseFloorMonitor()

        print(f"{log_prefix} [{LogLevel.INFO.name}] Initializing wake word listener...")
        self.awaker = WakeWordListener(self.noise_floor_monitor)

        print(f"{log_prefix} [{LogLevel.INFO.name}] Initializing audio recorder...")
        self.recorder = AudioRecorderClass(noise_floor_monitor=self.noise_floor_monitor)

        print(
            f"{log_prefix} [{LogLevel.INFO.name}] Initializing audio transcriptor (loading Whisper model '{whisper_model}' - this may take 10-30 seconds)..."
        )
        self.transcriptor = AudioTranscriptionClass(model_name=whisper_model)
        self.transcriptor.init_model()  # Auto-detect device
        print(
            f"{log_prefix} [{LogLevel.INFO.name}] Whisper model '{whisper_model}' loaded successfully"
        )

        print(f"{log_prefix} [{LogLevel.INFO.name}] Initializing sound player...")
        self.sound_player = SoundPlayer(base_path)
        # Small delay to allow pygame's audio system to fully initialize
        time.sleep(0.5)

        print(
            f"{log_prefix} [{LogLevel.INFO.name}] Initializing text-to-speech engine..."
        )
        self.speaker = TextToSpeech(
            voice_dir=voice_dir, language_models=language_models
        )
        print(
            f"{log_prefix} [{LogLevel.INFO.name}] All audio components initialized successfully"
        )

    def set_noise_floor(self, value):
        """
        @brief Thread-safe setter for noise floor.
        @param value Noise floor value to set
        """
        with self._noise_floor_lock:
            self.noise_floor = value

    def get_noise_floor(self):
        """
        @brief Thread-safe getter for noise floor.
        @return Current noise floor value
        """
        with self._noise_floor_lock:
            return self.noise_floor

    def pause_wake_word(self):
        """
        @brief Pause wake word detection and wait for cleanup.
        """
        self.awaker.pause()
        time.sleep(0.5)

    def resume_wake_word(self):
        """
        @brief Resume wake word detection if paused.
        """
        if not self.awaker.pause_event.is_set():
            self.awaker.resume()

    def record_and_transcribe(self):
        """
        @brief Record audio and return transcription.
        @return Transcribed text from audio
        """
        noise_floor_val = self.get_noise_floor()
        return self.recorder.record_audio(self.transcriptor, noise_floor_val)

    def speak_text(self, text, language):
        """
        @brief Convert text to speech and play it.
        @param text Text to speak
        @param language Language code for TTS
        """
        self.speaker.speak(text, language)

    def cleanup(self):
        """
        @brief Clean up audio components.
        """
        for attr in ("awaker", "transcriptor", "speaker"):
            if hasattr(self, attr):
                delattr(self, attr)
                setattr(self, attr, None)
