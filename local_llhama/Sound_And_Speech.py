# === System Imports ===
import os
import pygame
from enum import Enum
import numpy as np
from pathlib import Path
import pyaudio
import wave
import time
from collections import deque
import whisper  
from openwakeword.model import Model
import threading
from piper import SynthesisConfig, PiperVoice
from enum import Enum

# === Custom Imports ===
from .Shared_Logger import LogLevel

# Use PulseAudio for SDL audio driver
os.environ['SDL_AUDIODRIVER'] = 'pulse'

# ----------------------------------------------------------------------------- 
# Enum to represent different sound actions by name
# ----------------------------------------------------------------------------- 
class SoundActions(Enum):
    system_awake = 1      # Sound when system wakes up
    action_closing = 2    # Sound when an action closes
    system_error = 3      # Sound for system errors

class SoundPlayer:
    """
    @brief Handles loading, playing, stopping, and volume control for sounds using pygame.
    """
    def __init__(self, base_path):
        """
        @brief Initialize the pygame mixer, volume, sound cache, and sound file mappings.
        """
        self.class_prefix_message = "[SoundPlayer]"
        self.cleanup()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)  # Init mixer with standard settings
        pygame.mixer.set_num_channels(16)  # Allow up to 16 concurrent sounds

        self.volume = 1.0  # Default max volume
        self.loaded_sounds = {}  # Cache loaded pygame Sound objects
        self.base_path = base_path
        self.sounds_root_folder = f"{self.base_path}/sounds/"  # Base folder for sound files

        # Map action names to filenames of sound files
        self.sounds_dictionary = {
            "system_awake": "system_awake.mp3",
            "action_closing": "action_closing.mp3",
            "system_error": "system_error.mp3"
        }

    def cleanup(self):
        try:
            if pygame.mixer.get_init():  # Only cleanup if mixer was initialized
                pygame.mixer.stop()
                pygame.mixer.quit()
        except pygame.error:
            # Ignore errors if mixer was never initialized or already quit
            pass

    def load_sound(self, sound_name):
        """
        @brief Load a sound by name if not already loaded.
        @param sound_name The name key of the sound (matching sounds_dictionary keys).
        @return pygame.mixer.Sound object or None if failed to load.
        """
        if sound_name not in self.loaded_sounds:
            audio_path = f"{self.sounds_root_folder}{self.sounds_dictionary[sound_name]}"
            try:
                # Load sound file and cache it
                self.loaded_sounds[sound_name] = pygame.mixer.Sound(audio_path)
            except pygame.error as e:
                print(f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to load sound '{sound_name}': {e}")
                return None
        return self.loaded_sounds[sound_name]

    def play(self, sound_to_play, volume: float = 1.0, wait_for_finish=True):
        """
        @brief Play a sound with optional volume and blocking until done.
        @param sound_to_play SoundActions enum member specifying which sound to play.
        @param volume Playback volume between 0.0 and 1.0.
        @param wait_for_finish Whether to block execution until sound playback completes.
        """
        # Clamp volume between 0.0 and 1.0
        self.volume = max(0.0, min(volume, 1.0))

        # Load the sound object by name
        sound = self.load_sound(sound_to_play.name)
        if not sound:
            return  # Loading failed, skip playback

        # Set the volume and start playing the sound
        sound.set_volume(self.volume)
        channel = sound.play()

        # Optionally block until sound finishes playing
        if wait_for_finish and channel:
            while channel.get_busy():
                pygame.time.Clock().tick(10)  # Sleep a bit to reduce CPU usage

    def stop(self):
        """
        @brief Immediately stop all currently playing sounds.
        """
        pygame.mixer.stop()

    def set_volume(self, volume: float):
        """
        @brief Set the global playback volume and update currently playing sounds.
        @param volume Volume level between 0.0 and 1.0.
        @throws ValueError if volume is out of range.
        """
        if 0.0 <= volume <= 1.0:
            self.volume = volume

            # Update volume on all active channels
            for i in range(pygame.mixer.get_num_channels()):
                channel = pygame.mixer.Channel(i)
                if channel.get_busy():
                    channel.set_volume(self.volume)
        else:
            raise ValueError("Volume must be between 0.0 and 1.0")


class TextToSpeech:
    """
    Text-to-Speech using Piper with real-time streaming playback and LLM language mapping.
    """

    LANG_VOICE_INITIALS = {
        "en": "en",
        "fr": "fr",
        "de": "de",
        "it": "it",
        "es": "es",
        "ru": "ru"
    }

    def __init__(self, voice_dir: str):
        self.voice_dir = Path(voice_dir)
        if not self.voice_dir.exists():
            raise FileNotFoundError(f"Voice directory not found: {voice_dir}")
        self.class_prefix_message = "[TextToSpeech]"
        self.p = pyaudio.PyAudio()
        self.voice = None

    def preprocess_text(self, text: str) -> str:
        return text.strip()

    def select_voice_by_lang(self, lang_tag: str):
        if lang_tag not in self.LANG_VOICE_INITIALS:
            raise ValueError(f"Unsupported language tag: {lang_tag}")

        prefix = self.LANG_VOICE_INITIALS[lang_tag]
        matching_files = list(self.voice_dir.glob(f"{prefix}_*.onnx"))

        if not matching_files:
            raise FileNotFoundError(f"No voice found for language '{lang_tag}' in {self.voice_dir}")

        voice_file = matching_files[0]
        self.voice = PiperVoice.load(voice_file)
        print(f"{self.class_prefix_message} Loaded voice: {voice_file.name}")

    def speak(self, text: str, lang_tag: str):
        text = self.preprocess_text(text)
        if not text:
            raise ValueError(f"{self.class_prefix_message} Empty or invalid text")

        self.select_voice_by_lang(lang_tag)

        # Synthesis configuration for natural voice
        syn_config = SynthesisConfig(
            volume=0.5,          # half as loud
            length_scale=1.0,    # slower, more natural
            noise_scale=1.0,     # natural variation
            noise_w_scale=1.0,   # more speaking variation
            normalize_audio=False
        )

        stream = None

        # Stream audio in real-time
        for i, chunk in enumerate(self.voice.synthesize(text, syn_config=syn_config)):
            if stream is None:
                stream = self.p.open(
                    format=self.p.get_format_from_width(chunk.sample_width),
                    channels=chunk.sample_channels,
                    rate=chunk.sample_rate,
                    output=True,
                )
            stream.write(chunk.audio_int16_bytes)

        if stream:
            stream.stop_stream()
            stream.close()

    def __del__(self):
        self.p.terminate()


class AudioTranscriptionClass:
    """
    @class AudioTranscriptionClass
    @brief Handles audio transcription using OpenAI's Whisper model.
    """

    def __init__(self):
        self.class_prefix_message = "[AudioTranscriptionClass]"
        self.model_name = "medium"  # Name of the Whisper model to use
        self.model = None           # Will hold the loaded Whisper model

    def init_model(self, device):
        """
        @brief Loads the Whisper model onto the specified device.

        @param device: The device to load the model on ('cpu', 'cuda', etc.).
        """
        self.model = whisper.load_model(self.model_name, device=device)
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Whisper model '{self.model_name}' loaded on {device}.")

    def transcribe_audio(self, filename):
        """
        @brief Transcribes the audio from the given file using Whisper.

        @param filename: Path to the audio file to transcribe.
        @return: The transcribed text, or an empty string if the file is not found.
        """
        if not os.path.exists(filename):
            print(f"{self.class_prefix_message} [{LogLevel.ERROR.name}] File {filename} not found!")
            return ""

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing {filename} with Whisper...")
        result = self.model.transcribe(filename)
        transcription = result["text"]

        os.remove(filename)  # Cleanup
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Transcription completed and temporary file removed.")
        return transcription


class AudioRecorderClass:
    """
    @class AudioRecorderClass
    @brief Records audio from a microphone and transcribes it using Whisper.
    """

    def __init__(self, noise_floor_monitor, duration=10, sample_rate=16000, channels=1, chunk_size=1024):
        self.class_prefix_message = "[AudioRecorderClass]"
        self.duration = duration
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        self.noise_floor_multiplier = 0.95
        self.noise_threshold = 0
        self.silence_window_seconds = 2
        self.max_chunks = int(self.sample_rate / self.chunk_size * self.silence_window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)

    def get_silence(self):
        if not self.rms_values:
            return 0.0
        return sum(self.rms_values) / len(self.rms_values)

    def record_audio(self, transcriptor: AudioTranscriptionClass, noise_floor):
        p = pyaudio.PyAudio()

        stream = p.open(format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size)
        
        self.noise_threshold = noise_floor * self.noise_floor_multiplier
        frames = []

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording started, listening for at least 3 seconds and up to {self.duration} seconds...")

        start_time = time.time()
        min_recording_duration = 2

        while True:
            data = stream.read(self.chunk_size)
            frames.append(data)

            current_rms = self.noise_floor_monitor.rms_to_dbfs(
                self.noise_floor_monitor._calculate_rms(data)
            )
            self.rms_values.append(current_rms)
            measured_rms = self.get_silence()
            elapsed_time = time.time() - start_time

            if elapsed_time >= min_recording_duration:
                if measured_rms < self.noise_threshold and len(self.rms_values) >= (self.max_chunks - 1):
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] RMS ({measured_rms:.2f}) dropped below noise threshold ({self.noise_threshold:.2f}), stopping recording.")
                    break

            if elapsed_time > self.duration:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording duration of {self.duration} seconds reached.")
                break

        stream.stop_stream()
        stream.close()
        p.terminate()

        filename = "temp_audio.wav"
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(frames))

        transcription = transcriptor.transcribe_audio(filename)
        return transcription


class NoiseFloorMonitor:
    """
    @class NoiseFloorMonitor
    @brief Monitors and calculates the noise floor (RMS) in an audio stream.
    """

    def __init__(self, rate=16000, chunk_size=1024, window_seconds=5):
        self.class_prefix_message = "[NoiseFloorMonitor]"
        self.rate = rate
        self.chunk_size = chunk_size
        self.window_seconds = window_seconds
        self.max_chunks = int(self.rate / self.chunk_size * self.window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)
        self.noise_floor_multiplier = 1.05

    def _calculate_rms(self, data):
        audio_data = np.frombuffer(data, dtype=np.int16)
        if audio_data.size == 0:
            return 0.0
        squared = audio_data.astype(np.float32) ** 2
        mean_squared = np.mean(squared)
        if np.isnan(mean_squared) or np.isinf(mean_squared):
            return 0.0
        return np.sqrt(mean_squared)

    def update_and_get_average_rms(self, data):
        rms = self._calculate_rms(data) 
        self.rms_values.append(self.rms_to_dbfs(rms))
        return float(np.mean(self.rms_values))
    
    def get_noise_floor(self):
        if not self.rms_values:
            return 0.0
        return self.noise_floor_multiplier * sum(self.rms_values) / len(self.rms_values)
    
    def rms_to_dbfs(self, rms, ref=32768.0):
        if rms == 0:
            return -float('inf')
        return 20 * np.log10(rms / ref)


class WakeWordListener:
    """
    @class WakeWordListener
    @brief Listens to the microphone and detects a predefined wake word using OpenWakeWord.
    """

    def __init__(self, noise_floor_monitor):
        self.class_prefix_message = "[WakeWordListener]"
        self.wakeword_thr = 0.70
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        self.stop_event = threading.Event()

    def listen_for_wake_word(self, result_queue):
        while not self.stop_event.is_set():
            owwModel = Model(inference_framework="tflite")
            CHUNK = 1280

            audio = pyaudio.PyAudio()
            mic_stream = audio.open(format=pyaudio.paInt16,
                                    channels=1,
                                    rate=16000,
                                    input=True,
                                    frames_per_buffer=CHUNK)

            cooldown_time = 2
            ignore_rms_window = 3
            last_detection_time = 0

            while True:
                audio_data = mic_stream.read(CHUNK)
                np_audio = np.frombuffer(audio_data, dtype=np.int16)
                prediction = owwModel.predict(np_audio)

                current_time = time.time()

                if (current_time - last_detection_time) > ignore_rms_window:
                    self.noise_floor_monitor.update_and_get_average_rms(audio_data)

                for mdl in owwModel.prediction_buffer.keys():
                    scores = list(owwModel.prediction_buffer[mdl])
                    last_scores = scores[-5:]
                    avg_score = sum(last_scores) / len(last_scores) if last_scores else 0

                    if avg_score >= self.wakeword_thr and (current_time - last_detection_time) > cooldown_time:
                        last_detection_time = current_time
                        while not result_queue.empty():
                            result_queue.get()
                        noise_floor = self.noise_floor_monitor.get_noise_floor()
                        result_queue.put(noise_floor)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detected, noise floor sent to queue.")
                        break
