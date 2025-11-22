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
        try:
            self.p = pyaudio.PyAudio()
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PyAudio initialized successfully")
        except OSError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize PyAudio: {e}")
            raise RuntimeError(f"Audio device initialization failed: {e}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error initializing PyAudio: {type(e).__name__}: {e}")
            raise
        
        self.voice = None
        self.voice_cache = {}  # Cache loaded voices by language
        self.current_lang = None

    def preprocess_text(self, text: str) -> str:
        return text.strip()

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
            length_scale=1.0,   
            noise_scale=1.0,     
            noise_w_scale=1.0,  
            normalize_audio=False
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
                            stream = self.p.open(
                                format=self.p.get_format_from_width(chunk.sample_width),
                                channels=chunk.sample_channels,
                                rate=chunk.sample_rate,
                                output=True,
                            )
                        stream.write(chunk.audio_int16_bytes)
                        break  # Success, exit retry loop
                    except OSError as e:
                        retry_count += 1
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio stream error (attempt {retry_count}/{max_retries + 1}): {e}")
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
        except OSError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Audio device error during speech: {e}")
            if stream:
                try:
                    stream.close()
                except:
                    pass
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error during speech: {type(e).__name__}: {e}")
            if stream:
                try:
                    stream.close()
                except:
                    pass

    def __del__(self):
        self.p.terminate()
