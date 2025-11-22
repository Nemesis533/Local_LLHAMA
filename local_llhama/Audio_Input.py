# === System Imports ===
import os
import numpy as np
import pyaudio
import wave
import time
from collections import deque
import whisper  
from openwakeword.model import Model
import threading

# === Custom Imports ===
from .Shared_Logger import LogLevel


class AudioTranscriptionClass:
    """
    @class AudioTranscriptionClass
    @brief Handles audio transcription using OpenAI's Whisper model.
    """

    def __init__(self):
        self.class_prefix_message = "[AudioTranscriptionClass]"
        self.model_name = "turbo"  # Name of the Whisper model to use
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
        self.noise_floor_multiplier = 0.5
        self.noise_threshold = 0
        self.silence_window_seconds = 2
        self.max_chunks = int(self.sample_rate / self.chunk_size * self.silence_window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)

    def get_silence(self):
        if not self.rms_values:
            return 0.0
        return sum(self.rms_values) / len(self.rms_values)

    def record_audio(self, transcriptor: AudioTranscriptionClass, noise_floor):
        p = None
        stream = None
        
        try:
            # Initialize PyAudio with error handling
            try:
                p = pyaudio.PyAudio()
            except OSError as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize PyAudio: {e}")
                return "Audio device initialization failed"
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error initializing PyAudio: {type(e).__name__}: {e}")
                return "Audio initialization error"

            # Open audio stream with error handling
            try:
                stream = p.open(format=pyaudio.paInt16,
                                channels=self.channels,
                                rate=self.sample_rate,
                                input=True,
                                frames_per_buffer=self.chunk_size)
            except OSError as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to open audio stream: {e}")
                # Don't terminate - let garbage collector handle it
                return "Failed to open microphone"
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error opening stream: {type(e).__name__}: {e}")
                # Don't terminate - let garbage collector handle it
                return "Microphone error"
            
            self.noise_threshold = noise_floor * self.noise_floor_multiplier
            frames = []

            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording started, listening for at least 3 seconds and up to {self.duration} seconds...")

            start_time = time.time()
            min_recording_duration = 2

            # Recording loop with error handling
            while True:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)

                    current_rms = self.noise_floor_monitor.rms_to_dbfs(
                        self.noise_floor_monitor._calculate_rms(data)
                    )
                    self.rms_values.append(current_rms)
                    measured_rms = self.get_silence()
                    elapsed_time = time.time() - start_time

                    if elapsed_time >= min_recording_duration:
                        if abs(measured_rms) < abs(self.noise_threshold) and len(self.rms_values) >= (self.max_chunks - 1):
                            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] RMS ({measured_rms:.2f}) dropped below noise threshold ({self.noise_threshold:.2f}), stopping recording.")
                            break

                    if elapsed_time > self.duration:
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording duration of {self.duration} seconds reached.")
                        break
                except OSError as e:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio read error: {e}")
                    # If we have some frames, try to continue
                    if len(frames) < 10:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed too early")
                        raise
                    break

            stream.stop_stream()
            stream.close()
            # Don't terminate PyAudio - it's a global shutdown that breaks other instances
            # Just let Python's garbage collector handle it
            
            # Allow time for device cleanup before other processes access it
            time.sleep(0.3)

            # Check if we got any audio data
            if not frames:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] No audio data recorded")
                return "No audio captured"

            filename = "temp_audio.wav"
            try:
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b''.join(frames))
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to save audio file: {e}")
                return "Failed to save recording"

            transcription = transcriptor.transcribe_audio(filename)
            return transcription
            
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed: {type(e).__name__}: {e}")
            return "Recording error"
        finally:
            # Ensure cleanup
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
            # Don't terminate PyAudio - it's a global shutdown
            # Just allow time for device cleanup
            time.sleep(0.3)


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
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused

    def pause(self):
        """Pause wake word detection to free audio device."""
        self.pause_event.clear()
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection paused")

    def resume(self):
        """Resume wake word detection."""
        self.pause_event.set()
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection resumed")

    def listen_for_wake_word(self, result_queue):
        while not self.stop_event.is_set():
            # Wait if paused
            if not self.pause_event.is_set():
                time.sleep(0.1)
                continue
            
            audio = None
            mic_stream = None
            
            try:
                owwModel = Model(inference_framework="tflite")
                CHUNK = 1280

                # Initialize PyAudio with error handling
                try:
                    audio = pyaudio.PyAudio()
                except OSError as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize PyAudio: {e}")
                    time.sleep(5)  # Wait before retry
                    continue
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected PyAudio error: {type(e).__name__}: {e}")
                    time.sleep(5)
                    continue

                # Open microphone stream with error handling
                try:
                    mic_stream = audio.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True,
                                            frames_per_buffer=CHUNK)
                except OSError as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to open microphone: {e}")
                    # Don't terminate - let garbage collector handle it
                    time.sleep(5)  # Wait before retry
                    continue
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected stream error: {type(e).__name__}: {e}")
                    # Don't terminate - let garbage collector handle it
                    time.sleep(5)
                    continue

                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection started")
                cooldown_time = 2
                ignore_rms_window = 3
                last_detection_time = 0

                # Main detection loop with error handling
                while not self.stop_event.is_set() and self.pause_event.is_set():
                    try:
                        audio_data = mic_stream.read(CHUNK, exception_on_overflow=False)
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
                    except OSError as e:
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio read error in wake word detection: {e}")
                        break  # Exit inner loop to reinitialize
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error in wake word detection: {type(e).__name__}: {e}")
                        break  # Exit inner loop to reinitialize
            
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Wake word listener error: {type(e).__name__}: {e}")
            finally:
                # Cleanup
                if mic_stream:
                    try:
                        mic_stream.stop_stream()
                        mic_stream.close()
                    except:
                        pass
                # Don't terminate PyAudio - it's a global shutdown
                # Allow time for device cleanup
                time.sleep(0.3)
                
                # Wait before retry if not stopping and not paused
                if not self.stop_event.is_set() and self.pause_event.is_set():
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restarting wake word detection in 3 seconds...")
                    time.sleep(3)
