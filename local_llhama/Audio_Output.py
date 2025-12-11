# === System Imports ===
import os
import pygame
from enum import Enum
import time
from pathlib import Path
import pyaudio
from piper import SynthesisConfig, PiperVoice

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
    reminder = 4          # Sound for reminders and alarms

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
        
        # Initialize mixer with retry logic
        mixer_initialized = False
        for attempt in range(3):
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                pygame.mixer.set_num_channels(16)
                mixer_initialized = True
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Pygame mixer initialized successfully")
                break
            except pygame.error as e:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to init mixer (attempt {attempt + 1}/3): {e}")
                time.sleep(0.5)
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error initializing mixer: {type(e).__name__}: {e}")
                break
        
        if not mixer_initialized:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize pygame mixer after 3 attempts - sounds will be disabled")
        
        self.mixer_available = mixer_initialized
        self.volume = 1.0  # Default max volume
        self.loaded_sounds = {}  # Cache loaded pygame Sound objects
        self.base_path = base_path
        self.sounds_root_folder = f"{self.base_path}/sounds/"  # Base folder for sound files

        # Map action names to filenames of sound files
        self.sounds_dictionary = {
            "system_awake": "system_awake.mp3",
            "action_closing": "action_closing.mp3",
            "system_error": "system_error.mp3",
            "reminder": "reminder.mp3"
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
        # Check if mixer is available
        if not self.mixer_available:
            return  # Silently skip if mixer initialization failed
        
        try:
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
        except pygame.error as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Playback error: {e}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected playback error: {type(e).__name__}: {e}")

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
        self.class_prefix_message = "[TextToSpeech]"
        
        # Validate voice directory
        if not self.voice_dir.exists():
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice directory not found: {voice_dir}")
            raise FileNotFoundError(f"Voice directory not found: {voice_dir}")
        
        if not self.voice_dir.is_dir():
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice path is not a directory: {voice_dir}")
            raise NotADirectoryError(f"Voice path is not a directory: {voice_dir}")
        
        # Check for readable voice files
        try:
            voice_files = list(self.voice_dir.glob("*.onnx"))
            if not voice_files:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No .onnx voice files found in {voice_dir}")
            else:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Found {len(voice_files)} voice file(s) in {voice_dir}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error scanning voice directory: {e}")
        
        # Initialize PyAudio with error handling
        # Important: Initialize AFTER pygame to avoid device conflicts
        # Multiple retries to handle race conditions with pygame
        self.p = None
        for init_attempt in range(3):
            try:
                if init_attempt > 0:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PyAudio init attempt {init_attempt + 1}/3...")
                    time.sleep(0.3 * init_attempt)  # Progressive backoff
                
                self.p = pyaudio.PyAudio()
                device_count = self.p.get_device_count()
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PyAudio initialized successfully ({device_count} devices found)")
                
                if device_count > 0:
                    break  # Success!
                else:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] PyAudio found 0 devices, retrying...")
                    self.p.terminate()
                    self.p = None
            except Exception as init_err:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] PyAudio init attempt {init_attempt + 1} failed: {init_err}")
                if self.p:
                    try:
                        self.p.terminate()
                    except:
                        pass
                    self.p = None
        
        if self.p is None:
            raise RuntimeError("Failed to initialize PyAudio after 3 attempts")
        
        device_count = self.p.get_device_count()
        
        # Get and validate default output device
        try:
            default_output_info = self.p.get_default_output_device_info()
            self.output_device_index = default_output_info['index']
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Default output device: {default_output_info['name']} (index: {self.output_device_index})")
        except (OSError, IOError) as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No default output device found: {e}")
            # Try to find any working output device
            self.output_device_index = None
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Searching {device_count} devices for output capability...")
            for i in range(device_count):
                try:
                    dev_info = self.p.get_device_info_by_index(i)
                    if dev_info['maxOutputChannels'] > 0:
                        self.output_device_index = i
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using output device: {dev_info['name']} (index: {i}, channels: {dev_info['maxOutputChannels']})")
                        break
                except Exception as dev_err:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error checking device {i}: {dev_err}")
                    continue
            
            if self.output_device_index is None:
                raise RuntimeError("No output audio device available")
        
        # Test if we can actually open the device
        try:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Testing output device {self.output_device_index}...")
            test_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=22050,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=1024
            )
            test_stream.close()
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Output device test successful")
        except (OSError, IOError) as test_err:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Output device test failed: {test_err}")
            # Device exists but can't be opened - try to find another one
            original_device = self.output_device_index
            self.output_device_index = None
            for i in range(device_count):
                if i == original_device:
                    continue
                try:
                    dev_info = self.p.get_device_info_by_index(i)
                    if dev_info['maxOutputChannels'] > 0:
                        test_stream = self.p.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=22050,
                            output=True,
                            output_device_index=i,
                            frames_per_buffer=1024
                        )
                        test_stream.close()
                        self.output_device_index = i
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Found working alternative device: {dev_info['name']} (index: {i})")
                        break
                except:
                    continue
            
            if self.output_device_index is None:
                raise RuntimeError(f"All output devices failed to open. Original error: {test_err}")
        
        self.voice = None
        self.voice_cache = {}  # Cache loaded voices by language
        self.current_lang = None

    def preprocess_text(self, text: str) -> str:
        """Preprocess text for better TTS pronunciation."""
        text = text.strip()
        
        # Fix common pronunciation issues
        replacements = [
            # Handle interjections and onomatopoeia - use phonetic spellings
            ('Brrr', 'Burr,'),  
            ('brrr', 'burr,'),
            ('Hmm', 'Hm,'),
            ('hmm', 'hm,'),
            ('Ahh', 'Ah,'),
            ('ahh', 'ah,'),
            ('Ohh', 'Oh,'),
            ('ohh', 'oh,'),
            ('Phew', 'Few,'),  # Phonetic pronunciation
            ('phew', 'few,'),
            ('Ugh', 'Uh,'),
            ('ugh', 'uh,'),
            ('Yay', 'Yay,'), 
            ('yay', 'yay,'),
            ('Wow', 'Wow,'),
            ('wow', 'wow,'),
            
            # Fix common abbreviations
            ('etc.', 'etcetera'),
            ('vs.', 'versus'),
            ('e.g.', 'for example'),
            ('i.e.', 'that is'),
        ]
        
        for old, new in replacements:
            text = text.replace(old, new)
        
        # Handle repeated punctuation for emphasis (e.g., "!!!") -> add pause
        import re
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        
        return text

    def select_voice_by_lang(self, lang_tag: str):
        """Select and load a voice for the specified language with caching and error handling."""
        
        # Check if already loaded
        if lang_tag == self.current_lang and self.voice is not None:
            return  # Voice already loaded
        
        # Check if voice is in cache
        if lang_tag in self.voice_cache:
            self.voice = self.voice_cache[lang_tag]
            self.current_lang = lang_tag
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using cached voice for language: {lang_tag}")
            return
        
        # Validate language tag
        if lang_tag not in self.LANG_VOICE_INITIALS:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unsupported language tag: {lang_tag}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Supported languages: {list(self.LANG_VOICE_INITIALS.keys())}")
            raise ValueError(f"Unsupported language tag: {lang_tag}. Supported: {list(self.LANG_VOICE_INITIALS.keys())}")

        prefix = self.LANG_VOICE_INITIALS[lang_tag]
        
        # Search for voice files with error handling
        try:
            matching_files = list(self.voice_dir.glob(f"{prefix}_*.onnx"))
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error searching for voice files: {type(e).__name__}: {e}")
            raise RuntimeError(f"Failed to search voice directory: {e}")

        if not matching_files:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] No voice found for language '{lang_tag}' (prefix: {prefix})")
            # List available voice files to help debugging
            try:
                all_voices = list(self.voice_dir.glob("*.onnx"))
                if all_voices:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Available voices: {[v.name for v in all_voices]}")
                else:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No .onnx files found in {self.voice_dir}")
            except Exception:
                pass
            raise FileNotFoundError(f"No voice found for language '{lang_tag}' in {self.voice_dir}")

        voice_file = matching_files[0]
        
        # Validate voice file
        if not voice_file.exists():
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice file does not exist: {voice_file}")
            raise FileNotFoundError(f"Voice file not found: {voice_file}")
        
        if not voice_file.is_file():
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice path is not a file: {voice_file}")
            raise ValueError(f"Voice path is not a file: {voice_file}")
        
        # Check file size
        try:
            file_size = voice_file.stat().st_size
            if file_size == 0:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice file is empty: {voice_file}")
                raise ValueError(f"Voice file is empty: {voice_file}")
            if file_size < 1000:  # Less than 1KB is suspicious
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Voice file suspiciously small ({file_size} bytes): {voice_file}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not check voice file size: {e}")
        
        # Load voice with error handling
        try:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading voice file: {voice_file.name}")
            self.voice = PiperVoice.load(voice_file)
            self.voice_cache[lang_tag] = self.voice
            self.current_lang = lang_tag
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully loaded voice: {voice_file.name}")
        except FileNotFoundError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice file not found during load: {e}")
            raise
        except PermissionError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Permission denied reading voice file: {e}")
            raise RuntimeError(f"Cannot read voice file (permission denied): {voice_file}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to load voice file: {type(e).__name__}: {e}")
            raise RuntimeError(f"Voice loading failed for {voice_file}: {e}")

    def speak(self, text: str, lang_tag: str):
        text = self.preprocess_text(text)
        if not text:
            raise ValueError(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Empty or invalid text")

        try:
            self.select_voice_by_lang(lang_tag)
        except (ValueError, FileNotFoundError) as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Voice selection failed: {e}")
            return

        # Synthesis configuration for natural voice
        syn_config = SynthesisConfig(
            volume=0.5,
            length_scale=1,      # Slightly slower for clarity
            noise_scale=0.667,     # Less noise/breathiness
            noise_w_scale=0.8,     # Smoother prosody
            normalize_audio=True   # Consistent volume
        )

        stream = None
        retry_count = 0
        max_retries = 2

        try:
            # Stream audio in real-time with error recovery
            for i, chunk in enumerate(self.voice.synthesize(text, syn_config=syn_config)):
                while retry_count <= max_retries:
                    try:
                        if stream is None:
                            # Verify PyAudio is still valid
                            if self.p is None:
                                raise RuntimeError("PyAudio instance is None")
                            
                            # Log what we're trying to use
                            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Opening audio stream: device={self.output_device_index}, rate={chunk.sample_rate}, channels={chunk.sample_channels}")
                            
                            stream = self.p.open(
                                format=self.p.get_format_from_width(chunk.sample_width),
                                channels=chunk.sample_channels,
                                rate=chunk.sample_rate,
                                output=True,
                                output_device_index=self.output_device_index,
                            )
                            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio stream opened successfully")
                        stream.write(chunk.audio_int16_bytes)
                        break  # Success, exit retry loop
                    except OSError as e:
                        retry_count += 1
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio stream error (attempt {retry_count}/{max_retries + 1}): {e}")
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Device index: {self.output_device_index}, PyAudio valid: {self.p is not None}")
                        
                        # Try to diagnose the issue
                        if self.p is not None:
                            try:
                                device_count = self.p.get_device_count()
                                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] PyAudio currently sees {device_count} devices")
                                if self.output_device_index < device_count:
                                    dev_info = self.p.get_device_info_by_index(self.output_device_index)
                                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Device {self.output_device_index} info: {dev_info['name']}, outputs: {dev_info['maxOutputChannels']}")
                            except Exception as diag_err:
                                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Diagnostic check failed: {diag_err}")
                        
                        if stream:
                            try:
                                stream.close()
                            except:
                                pass
                            stream = None
                        if retry_count > max_retries:
                            raise
                        time.sleep(0.2)

            if stream:
                stream.stop_stream()
                stream.close()
                # Allow time for device cleanup before other processes access it
                time.sleep(0.3)
        except OSError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Audio device error during speech: {e}")
            if stream:
                try:
                    stream.close()
                    # Allow time for device cleanup
                    time.sleep(0.3)
                except:
                    pass
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error during speech: {type(e).__name__}: {e}")
            if stream:
                try:
                    stream.close()
                    # Allow time for device cleanup
                    time.sleep(0.3)
                except:
                    pass

    def __del__(self):
        # Don't terminate PyAudio in destructor - it's a global shutdown
        # that can break other PyAudio instances in the same process
        pass
