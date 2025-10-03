# === System Imports ===
import os
import pygame
from enum import Enum
import numpy as np
import re
import pyaudio
import wave
import time
from collections import deque
import whisper  
from openwakeword.model import Model
import threading
import pyttsx3


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
                print(f"[Error] Failed to load sound '{sound_name}': {e}")
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
    @class TextToSpeech
    @brief A lightweight local text-to-speech utility class using pyttsx3.

    Runs fully offline, cross-platform, and much faster than ML-based models.
    """

    def __init__(self,base_path="", rate: int = 180, volume: float = 1.0, voice: str = None):
        """
        @brief Constructor that initializes the TTS engine.

        @param rate: Speech rate (default: 180 words per minute).
        @param volume: Volume level between 0.0 and 1.0 (default: 1.0).
        @param voice: Optional voice name to select (e.g., "female", "male", "english").
        """
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", max(0.0, min(volume, 1.0)))

        # Set a specific voice if requested
        if voice:
            voices = self.engine.getProperty("voices")
            selected = None
            for v in voices:
                if voice.lower() in v.name.lower():
                    selected = v.id
                    break
            if selected:
                self.engine.setProperty("voice", selected)
            else:
                print(f"[WARN] Requested voice '{voice}' not found. Using default.")

    def preprocess_text(self, text: str) -> str:
        """
        @brief Preprocesses the input text to remove unsupported characters.

        Removes non-ASCII characters for cleaner synthesis.

        @param text: The raw input text.
        @return: Cleaned/preprocessed text.
        """
        return re.sub(r"[^\x00-\x7F]+", "", text)

    def set_playback_volume(self, volume: float):
        """
        @brief Adjusts the playback volume.

        @param volume: Volume scaling factor between 0.0 and 1.0.
        """
        volume = max(0.0, min(volume, 1.0))
        self.engine.setProperty("volume", volume)

    def speak(self, text: str):
        """
        @brief Converts input text to speech and plays it.

        @param text: The input text string to be synthesized and spoken.
        """
        text = self.preprocess_text(text)
        if not text.strip():
            print("[INFO] Empty or invalid text, nothing to speak.")
            return

        self.engine.say(text)
        self.engine.runAndWait()

class AudioTranscriptionClass:
    """
    @class AudioTranscriptionClass
    @brief Handles audio transcription using OpenAI's Whisper model.
    """

    def __init__(self):
        self.model_name = "medium"  # Name of the Whisper model to use
        self.model = None           # Will hold the loaded Whisper model

    def init_model(self, device):
        """
        @brief Loads the Whisper model onto the specified device.

        @param device: The device to load the model on ('cpu', 'cuda', etc.).
        """
        self.model = whisper.load_model(self.model_name, device=device)

    def transcribe_audio(self, filename):
        """
        @brief Transcribes the audio from the given file using Whisper.

        @param filename: Path to the audio file to transcribe.
        @return: The transcribed text, or an empty string if the file is not found.
        """
        if not os.path.exists(filename):
            print(f"Error: File {filename} not found!")
            return ""

        print(f"Processing {filename} with Whisper...")
        result = self.model.transcribe(filename)
        transcription = result["text"]

        os.remove(filename)  # Cleanup
        return transcription

class AudioRecorderClass:
    """
    @class AudioRecorderClass
    @brief Records audio from a microphone and transcribes it using Whisper.

    Handles noise floor detection, silence detection, and real-time RMS monitoring to 
    determine when to stop recording.
    """

    def __init__(self, noise_floor_monitor, duration=10, sample_rate=16000, channels=1, chunk_size=1024):
        """
        @brief Constructor for AudioRecorderClass.

        Initializes recording parameters and sets up RMS buffers for silence detection.

        @param noise_floor_monitor: Instance of NoiseFloorMonitor for background noise analysis.
        @param duration: Maximum recording duration in seconds.
        @param sample_rate: Sampling rate in Hz.
        @param channels: Number of input audio channels.
        @param chunk_size: Number of frames per buffer (block size).
        """
        self.duration = duration                          # Max duration to record
        self.sample_rate = sample_rate                    # Sampling rate
        self.channels = channels                          # Mono or stereo
        self.chunk_size = chunk_size                      # Size of each buffer chunk
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        self.noise_floor_multiplier = 0.95              # Threshold multiplier for silence detection
        self.noise_threshold = 0                          # Will be set based on detected noise floor
        self.silence_window_seconds = 2                   # Time to average for silence detection
        self.max_chunks = int(self.sample_rate / self.chunk_size * self.silence_window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)   # Recent RMS values for silence detection

    def get_silence(self):
        """
        @brief Calculates the average RMS over the recent silence window.

        @return: Mean of RMS values stored in the buffer.
        """
        if not self.rms_values:
            return 0.0
        return sum(self.rms_values) / len(self.rms_values)

    def record_audio(self, transcriptor: AudioTranscriptionClass, noise_floor):
        """
        @brief Records audio from the microphone until silence is detected or duration expires.

        Uses RMS level comparison to noise threshold for early stopping. Once recorded, 
        it saves the audio as a WAV file and transcribes it using the provided Whisper-based transcriptor.

        @param transcriptor: Instance of AudioTranscriptionClass used to transcribe audio.
        @param noise_floor: Baseline noise floor value to set silence threshold.
        @return: Transcribed text from recorded audio.
        """
        p = pyaudio.PyAudio()

        stream = p.open(format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size)
        
        self.noise_threshold = noise_floor * self.noise_floor_multiplier
        frames = []

        print(f"Recording started, listening for at least 3 seconds and up to {self.duration} seconds...")

        start_time = time.time()
        min_recording_duration = 2  # Minimum time before evaluating silence

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
                    print(f"RMS ({measured_rms:.2f}) dropped below noise threshold ({self.noise_threshold:.2f}), stopping recording.")
                    break

            if elapsed_time > self.duration:
                print(f"Recording duration of {self.duration} seconds reached.")
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

    Maintains a running buffer of RMS values to estimate background noise over time.
    """

    def __init__(self, rate=16000, chunk_size=1024, window_seconds=5):
        """
        @brief Constructor for NoiseFloorMonitor.

        Initializes parameters for sampling rate, chunk size, and averaging window.
        
        @param rate: The sampling rate of the audio in Hz.
        @param chunk_size: Number of samples per audio chunk.
        @param window_seconds: Number of seconds to average RMS over.
        """
        self.rate = rate                          # Audio sampling rate
        self.chunk_size = chunk_size              # Size of each audio chunk
        self.window_seconds = window_seconds      # Duration of RMS averaging window
        self.max_chunks = int(self.rate / self.chunk_size * self.window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)  # Buffer for recent RMS values
        self.noise_floor_multiplier = 1.05

    def _calculate_rms(self, data):
        """
        @brief Calculates the Root Mean Square (RMS) value from raw audio bytes.

        @param data: Byte string of audio data.
        @return: RMS value as a float.
        """
        audio_data = np.frombuffer(data, dtype=np.int16)
        if audio_data.size == 0:
            return 0.0
        squared = audio_data.astype(np.float32) ** 2
        mean_squared = np.mean(squared)
        if np.isnan(mean_squared) or np.isinf(mean_squared):
            return 0.0
        return np.sqrt(mean_squared)

    def update_and_get_average_rms(self, data):
        """
        @brief Updates the RMS buffer with new audio data and returns the running average in dBFS.

        @param data: Byte string of audio data.
        @return: Running average RMS in decibels relative to full scale (dBFS).
        """
        rms = self._calculate_rms(data) 
        self.rms_values.append(self.rms_to_dbfs(rms))
        return float(np.mean(self.rms_values))
    
    def get_noise_floor(self):
        """
        @brief Returns the current estimated noise floor in dBFS.

        @return: Average of the stored RMS values in dBFS.
        """
        if not self.rms_values:
            return 0.0
        return self.noise_floor_multiplier*sum(self.rms_values) / len(self.rms_values)
    
    def rms_to_dbfs(self, rms, ref=32768.0):
        """
        @brief Converts an RMS value to dBFS (decibels relative to full scale).

        @param rms: The RMS value to convert.
        @param ref: The reference value for 0 dBFS. Default is 32768.0 (max 16-bit PCM).
        @return: dBFS value as a float.
        """
        if rms == 0:
            return -float('inf')
        return 20 * np.log10(rms / ref)

class WakeWordListener:
    """
    @class WakeWordListener
    @brief Listens to the microphone and detects a predefined wake word using OpenWakeWord.

    Continuously streams audio, analyzes it in real time, and triggers when the wake word is detected.
    """

    def __init__(self, noise_floor_monitor):
        """
        @brief Constructor for WakeWordListener.

        @param noise_floor_monitor: Instance of NoiseFloorMonitor to track RMS levels for ambient noise.
        """
        self.wakeword_thr = 0.70  # Confidence threshold for wake word detection
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        self.stop_event = threading.Event()

    def listen_for_wake_word(self, result_queue):
        while not self.stop_event.is_set():
            """
            @brief Continuously listens to audio input and triggers when a wake word is detected.

            Uses OpenWakeWord for prediction and compares the average score to the threshold.
            Sends the current noise floor to the result queue upon detection.

            @param result_queue: Queue to communicate detection result (e.g., noise floor) back to main thread.
            """
            

            owwModel = Model(inference_framework="tflite")
            CHUNK = 1280

            audio = pyaudio.PyAudio()
            mic_stream = audio.open(format=pyaudio.paInt16,
                                    channels=1,
                                    rate=16000,
                                    input=True,
                                    frames_per_buffer=CHUNK)

            cooldown_time = 2             # Minimum time between detections
            ignore_rms_window = 3         # Time in seconds to ignore RMS updates after detection
            last_detection_time = 0       # Timestamp of the last wake word detection

            while True:
                audio_data = mic_stream.read(CHUNK)
                np_audio = np.frombuffer(audio_data, dtype=np.int16)
                prediction = owwModel.predict(np_audio)

                current_time = time.time()

                # Update noise floor only if not recently triggered
                if (current_time - last_detection_time) > ignore_rms_window:
                    self.noise_floor_monitor.update_and_get_average_rms(audio_data)

                for mdl in owwModel.prediction_buffer.keys():
                    scores = list(owwModel.prediction_buffer[mdl])
                    last_scores = scores[-5:]  # Get last 5 predictions
                    avg_score = sum(last_scores) / len(last_scores) if last_scores else 0

                    if avg_score >= self.wakeword_thr and (current_time - last_detection_time) > cooldown_time:
                        last_detection_time = current_time

                        # Clear previous results
                        while not result_queue.empty():
                            result_queue.get()

                        noise_floor = self.noise_floor_monitor.get_noise_floor()
                        result_queue.put(noise_floor)
                        break