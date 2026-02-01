# === System Imports ===
import os
import threading
import time
import wave
from collections import deque

import numpy as np
import pyaudio
import whisper
from openwakeword.model import Model

# === Custom Imports ===
from .shared_logger import LogLevel


class AudioTranscriptionClass:
    """
    @class AudioTranscriptionClass
    @brief Handles audio transcription using OpenAI's Whisper model.
    """

    def __init__(self, model_name="turbo"):
        self.class_prefix_message = "[AudioTranscriptionClass]"
        self.model_name = model_name  # Name of the Whisper model to use
        self.model = None  # Will hold the loaded Whisper model
        self.device = None  # Will be set during init_model

    def init_model(self, device=None):
        """
        @brief Loads the Whisper model onto the specified device.

        @param device: The device to load the model on ('cpu', 'cuda', etc.). If None, reads from system_settings.json or auto-detects.
        """
        # Auto-detect device if not specified
        if device is None:
            import json
            from pathlib import Path

            import torch

            # Try to load from system_settings.json
            try:
                settings_file = (
                    Path(__file__).parent / "settings" / "system_settings.json"
                )
                if settings_file.exists():
                    with open(settings_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    cuda_device = (
                        data.get("hardware", {})
                        .get("cuda_device", {})
                        .get("value", "auto")
                    )

                    if cuda_device == "auto":
                        device = "cuda" if torch.cuda.is_available() else "cpu"
                    elif cuda_device == "cpu":
                        device = "cpu"
                    else:
                        # cuda_device could be "cuda:0", "cuda:1", etc.
                        device = cuda_device if torch.cuda.is_available() else "cpu"
                else:
                    device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not load CUDA settings: {e}, using auto-detect"
                )
                device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = device
        self.model = whisper.load_model(self.model_name, device=device)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Whisper model '{self.model_name}' loaded on {device}."
        )

    def transcribe_audio(self, filename):
        """
        @brief Transcribes the audio from the given file using Whisper.

        @param filename: Path to the audio file to transcribe.
        @return: The transcribed text, or an empty string if the file is not found.
        """
        if not os.path.exists(filename):
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] File {filename} not found!"
            )
            return ""

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing {filename} with Whisper..."
        )
        result = self.model.transcribe(filename)
        transcription = result["text"]

        os.remove(filename)  # Cleanup
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Transcription completed and temporary file removed."
        )
        return transcription


class AudioRecorderClass:
    """
    @class AudioRecorderClass
    @brief Records audio from a microphone and transcribes it using Whisper.
    """

    def __init__(
        self,
        noise_floor_monitor,
        duration=10,
        sample_rate=16000,
        channels=1,
        chunk_size=1024,
    ):
        self.class_prefix_message = "[AudioRecorderClass]"
        self.duration = duration
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        
        # Load settings from system_settings.json
        self._load_settings()
        
        self.noise_threshold = 0
        self.max_chunks = int(
            self.sample_rate / self.chunk_size * self.silence_window_seconds
        )
        self.rms_values = deque(maxlen=self.max_chunks)

    def _load_settings(self):
        """Load audio settings from system_settings.json"""
        import json
        from pathlib import Path
        
        try:
            settings_file = Path(__file__).parent / "settings" / "system_settings.json"
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                audio_settings = data.get("audio", {})
                self.silence_window_seconds = audio_settings.get("silence_window_seconds", {}).get("value", 2)
                self.noise_floor_multiplier = audio_settings.get("noise_floor_multiplier", {}).get("value", 0.50)
                self.input_device_index = audio_settings.get("input_device_index", {}).get("value", None)
                
                # Load sample rate from settings
                configured_sample_rate = audio_settings.get("sample_rate", {}).get("value", 16000)
                self.sample_rate = configured_sample_rate
            else:
                # Fallback to defaults
                self.silence_window_seconds = 2
                self.noise_floor_multiplier = 0.50
                self.input_device_index = None
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not load audio settings: {e}, using defaults")
            self.silence_window_seconds = 2
            self.noise_floor_multiplier = 0.50
            self.input_device_index = None

    def get_silence(self):
        if not self.rms_values:
            return 0.0
        return sum(self.rms_values) / len(self.rms_values)

    def record_audio(self, transcriptor: AudioTranscriptionClass, noise_floor, existing_stream=None, existing_pyaudio=None):
        """Record audio using an existing stream if provided, otherwise create a new one."""
        p = existing_pyaudio
        stream = existing_stream
        owns_resources = (existing_stream is None)  # Track if we created the resources

        try:
            # Initialize PyAudio only if not provided
            if p is None:
                try:
                    p = pyaudio.PyAudio()
                except OSError as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize PyAudio: {e}"
                    )
                    return "Audio device initialization failed"
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error initializing PyAudio: {type(e).__name__}: {e}"
                    )
                    return "Audio initialization error"

            # Open audio stream only if not provided
            if stream is None:
                try:
                    stream_params = {
                        "format": pyaudio.paInt16,
                        "channels": self.channels,
                        "rate": self.sample_rate,
                        "input": True,
                        "frames_per_buffer": self.chunk_size,
                    }
                    
                    # Add input device if configured
                    if self.input_device_index is not None:
                        stream_params["input_device_index"] = self.input_device_index
                        
                        # Query device info to use its native sample rate
                        try:
                            device_info = p.get_device_info_by_index(self.input_device_index)
                            device_default_rate = int(device_info.get('defaultSampleRate', 16000))
                            print(
                                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Device default sample rate: {device_default_rate} Hz"
                            )
                            # Use device's native sample rate
                            stream_params["rate"] = device_default_rate
                            self.sample_rate = device_default_rate
                        except Exception as dev_err:
                            print(
                                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not query device info: {dev_err}"
                            )
                    
                    stream = p.open(**stream_params)
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio stream opened successfully at {self.sample_rate} Hz!")
                except OSError as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to open audio stream: {e}"
                    )
                    if owns_resources and p:
                        p.terminate()
                    return "Failed to access audio device"
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error opening stream: {type(e).__name__}: {e}"
                    )
                    if owns_resources and p:
                        p.terminate()
                    return "Audio stream error"
            else:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using existing audio stream")

            self.noise_threshold = noise_floor * self.noise_floor_multiplier
            frames = []

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording started, listening for at least 3 seconds and up to {self.duration} seconds..."
            )

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
                        if abs(measured_rms) < abs(self.noise_threshold) and len(
                            self.rms_values
                        ) >= (self.max_chunks - 1):
                            print(
                                f"{self.class_prefix_message} [{LogLevel.INFO.name}] RMS ({measured_rms:.2f}) dropped below noise threshold ({self.noise_threshold:.2f}), stopping recording."
                            )
                            break

                    if elapsed_time > self.duration:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording duration of {self.duration} seconds reached."
                        )
                        break
                except OSError as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio read error: {e}"
                    )
                    # If we have some frames, try to continue
                    if len(frames) < 10:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed too early"
                        )
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
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] No audio data recorded"
                )
                return "No audio captured"

            filename = "temp_audio.wav"
            try:
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b"".join(frames))
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to save audio file: {e}"
                )
                return "Failed to save recording"

            transcription = transcriptor.transcribe_audio(filename)
            return transcription

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed: {type(e).__name__}: {e}"
            )
            return "Recording error"
        finally:
            # Only cleanup if we own the resources
            if owns_resources:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except:
                        pass
                # Don't terminate PyAudio - it's a global shutdown
                # Just allow time for device cleanup
                time.sleep(0.3)
            else:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Returning stream to caller")


class NoiseFloorMonitor:
    """
    @class NoiseFloorMonitor
    @brief Monitors and calculates the noise floor (RMS) in an audio stream.
    """

    def __init__(self, rate=16000, chunk_size=1024, window_seconds=None):
        self.class_prefix_message = "[NoiseFloorMonitor]"
        self.rate = rate
        self.chunk_size = chunk_size
        
        # Load settings from system_settings.json
        if window_seconds is None:
            window_seconds = self._load_window_seconds()
        self.window_seconds = window_seconds
        
        self.max_chunks = int(self.rate / self.chunk_size * self.window_seconds)
        self.rms_values = deque(maxlen=self.max_chunks)
        self.noise_floor_multiplier = 1.05

    def _load_window_seconds(self):
        """Load window_seconds from system_settings.json"""
        import json
        from pathlib import Path
        
        try:
            settings_file = Path(__file__).parent / "settings" / "system_settings.json"
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                audio_settings = data.get("audio", {})
                return audio_settings.get("noise_monitor_window_seconds", {}).get("value", 5)
            else:
                return 5
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not load audio settings: {e}, using default")
            return 5

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
            return -float("inf")
        return 20 * np.log10(rms / ref)


class WakeWordListener:
    """
    @class WakeWordListener
    @brief Listens to the microphone and detects a predefined wake word using OpenWakeWord.
    """

    def __init__(self, noise_floor_monitor):
        self.class_prefix_message = "[WakeWordListener]"
        self.wakeword_thr = 0.85
        self.noise_floor_monitor: NoiseFloorMonitor = noise_floor_monitor
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused
        self.ready_event = threading.Event()  # Signal when ready to detect wake words
        
        # Load audio device settings
        self._load_settings()
        
        # Load OpenWakeWord model once during initialization
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading OpenWakeWord model...")
        self.owwModel = Model(inference_framework="tflite")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] OpenWakeWord model loaded successfully")
        self.CHUNK = 1280
        
        # Initialize PyAudio once
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing PyAudio...")
        self.audio = pyaudio.PyAudio()
        self.mic_stream = None  # Track current stream for reuse
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PyAudio initialized successfully")

    def _load_settings(self):
        """Load audio settings from system_settings.json"""
        import json
        from pathlib import Path
        
        try:
            settings_file = Path(__file__).parent / "settings" / "system_settings.json"
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                audio_settings = data.get("audio", {})
                self.input_device_index = audio_settings.get("input_device_index", {}).get("value", None)
                self.sample_rate = audio_settings.get("sample_rate", {}).get("value", 16000)
            else:
                self.input_device_index = None
                self.sample_rate = 16000
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not load audio settings: {e}, using default")
            self.input_device_index = None
            self.sample_rate = 16000

    def pause(self):
        """
        @brief Pause wake word detection to free audio device.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PAUSE requested, clearing pause_event")
        self.pause_event.clear()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection paused, pause_event is now: {self.pause_event.is_set()}"
        )

    def resume(self):
        """
        @brief Resume wake word detection.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] RESUME requested, setting pause_event")
        
        # Clear any stale wake word detections from the queue
        if hasattr(self, 'result_queue'):
            while not self.result_queue.empty():
                try:
                    self.result_queue.get_nowait()
                except:
                    break
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Cleared stale wake word detections from queue")
        
        # Reset OpenWakeWord model's internal prediction buffer to prevent false triggers
        if hasattr(self, 'owwModel') and hasattr(self.owwModel, 'prediction_buffer'):
            for model_name in self.owwModel.prediction_buffer.keys():
                self.owwModel.prediction_buffer[model_name].clear()
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Cleared OpenWakeWord model prediction buffer")
        
        self.pause_event.set()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection resumed, pause_event is now: {self.pause_event.is_set()}"
        )

    def listen_for_wake_word(self, result_queue):
        # Store queue reference for clearing on resume
        self.result_queue = result_queue
        
        while not self.stop_event.is_set():
          
            # Wait if paused - block until resumed or stopped
            self.pause_event.wait(timeout=1.0)
            
            # Check if we were stopped while waiting
            if self.stop_event.is_set():
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Stop event detected, breaking")
                break
            
            # Check if still paused after timeout (shouldn't normally happen)
            if not self.pause_event.is_set():
                continue

            mic_stream = None

            try:
                # Open microphone stream with error handling (PyAudio already initialized in __init__)
                try:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Opening microphone stream...")
                    
                    # Query device info if device index is configured
                    device_sample_rate = self.sample_rate
                    if self.input_device_index is not None:
                        try:
                            device_info = self.audio.get_device_info_by_index(self.input_device_index)
                            device_default_rate = int(device_info.get('defaultSampleRate', 16000))
                            print(
                                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Device default sample rate: {device_default_rate} Hz"
                            )
                            # Use device's native sample rate
                            device_sample_rate = device_default_rate
                        except Exception as dev_err:
                            print(
                                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not query device info: {dev_err}"
                            )
                    
                    stream_params = {
                        "format": pyaudio.paInt16,
                        "channels": 1,
                        "rate": device_sample_rate,
                        "input": True,
                        "frames_per_buffer": self.CHUNK,
                    }
                    
                    # Add input device if configured
                    if self.input_device_index is not None:
                        stream_params["input_device_index"] = self.input_device_index
                    
                    self.mic_stream = self.audio.open(**stream_params)
                    mic_stream = self.mic_stream
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Microphone stream opened successfully at {device_sample_rate} Hz!")
                except OSError as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to open microphone: {e}"
                    )
                    time.sleep(5)  # Wait before retry
                    continue
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected stream error: {type(e).__name__}: {e}"
                    )
                    time.sleep(5)
                    continue

                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection active and listening..."
                )
                
                # Signal that we're ready to detect wake words
                self.ready_event.set()
                
                # IMPORTANT: Flush initial audio buffer to discard any TTS echoes
                # Read and discard ~1 second of audio to clear the pipeline
                flush_iterations = int(16000 / self.CHUNK)  # ~1 second at 16kHz
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Flushing audio buffer ({flush_iterations} chunks)..."
                )
                for _ in range(flush_iterations):
                    try:
                        mic_stream.read(self.CHUNK, exception_on_overflow=False)
                    except:
                        break  # If read fails, just continue
                
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio buffer flushed, ready for wake word detection"
                )
                
                cooldown_time = 2
                ignore_rms_window = 3
                last_detection_time = 0

                # Main detection loop - exit if stopped OR paused
                while not self.stop_event.is_set() and self.pause_event.is_set():
                    try:
                        audio_data = mic_stream.read(self.CHUNK, exception_on_overflow=False)
                        np_audio = np.frombuffer(audio_data, dtype=np.int16)
                        
                        # Resample to 16kHz if device is using a different sample rate
                        # OpenWakeWord models are trained on 16kHz audio
                        if device_sample_rate != 16000:
                            from scipy import signal
                            # Calculate the resampling ratio
                            num_samples = int(len(np_audio) * 16000 / device_sample_rate)
                            np_audio = signal.resample(np_audio, num_samples).astype(np.int16)
                        
                        prediction = self.owwModel.predict(np_audio)

                        current_time = time.time()

                        if (current_time - last_detection_time) > ignore_rms_window:
                            self.noise_floor_monitor.update_and_get_average_rms(
                                audio_data
                            )

                        for mdl in self.owwModel.prediction_buffer.keys():
                            scores = list(self.owwModel.prediction_buffer[mdl])
                            last_scores = scores[-5:]
                            avg_score = (
                                sum(last_scores) / len(last_scores)
                                if last_scores
                                else 0
                            )

                            if (
                                avg_score >= self.wakeword_thr
                                and (current_time - last_detection_time) > cooldown_time
                            ):
                                last_detection_time = current_time
                                while not result_queue.empty():
                                    result_queue.get()
                                noise_floor = self.noise_floor_monitor.get_noise_floor()
                                result_queue.put(noise_floor)
                                print(
                                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detected, noise floor sent to queue."
                                )
                                break
                    except OSError as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio read error in wake word detection: {e}"
                        )
                        break  # Exit inner loop to reinitialize
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error in wake word detection: {type(e).__name__}: {e}"
                        )
                        break  # Exit inner loop to reinitialize

            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Wake word listener error: {type(e).__name__}: {e}"
                )
                import traceback
                traceback.print_exc()
            finally:
                # Clear ready flag since we're no longer listening
                self.ready_event.clear()
                
                # Cleanup resources (only close mic stream, keep PyAudio alive)
                if mic_stream:
                    try:
                        mic_stream.stop_stream()
                        mic_stream.close()
                        self.mic_stream = None  # Clear reference
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error closing mic stream: {e}")
                
                # Allow time for device cleanup - increased for device release
                time.sleep(1.0)

            # After cleanup, check if we should restart the detection loop
            # If still not stopped and not paused, we'll reinitialize on next iteration
            if not self.stop_event.is_set():
                # Brief delay before attempting to reinitialize
                if not self.pause_event.is_set():
                    # Paused - will wait at top of loop
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word detection paused, waiting for resume...")
                else:
                    # Error or other interruption - restart after delay
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restarting wake word detection in 2 seconds..."
                    )
                    time.sleep(2)
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Wake word listener thread stopped")
