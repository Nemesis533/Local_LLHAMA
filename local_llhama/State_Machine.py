# === System Imports ===
import threading
from threading import  Event
from queue import Queue, Empty
import time
from enum import Enum
import time
import multiprocessing as mp

# === Custom Imports ===
from .Sound_And_Speech import SoundPlayer, SoundActions, TextToSpeech, AudioRecorderClass, NoiseFloorMonitor, AudioTranscriptionClass, WakeWordListener
from .LLM_Handler import LLM_Class
from .Ollama_Client import OllamaClient
from .Home_Assistant_Interface import HomeAssistantClient
from .Shared_Logger import LogLevel

class State(Enum):
    """
    @brief Enumeration for various states of the voice assistant state machine.
    """
    LOADING = "LOADING"
    LISTENING = "LISTENING"
    RECORDING = "RECORDING"
    GENERATING = "GENERATING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    PARSING_VOICE = "PARSING_VOICE"
    SEND_COMMANDS = "SEND_COMMANDS"
    NO_COMMANDS = "NO_COMMANDS"


class StateMachineInstance:
    """
    @brief Core state machine managing voice assistant states, audio input/output, command processing, and interactions.
    """

    def __init__(self, command_llm, device, ha_client, base_path=None, action_message_queue=None,web_server_message_queue=None):
        """
        @brief Initialize the state machine, threads, queues, and component instances.
        @param command_llm The LLM instance used for command parsing.
        @param device The computation device (e.g., "cuda" or "cpu").
        @param ha_client The Home Assistant client interface.
        """
        self.device = device
        self.noise_floor = 0
        self.base_path = base_path
        voice_dir = "/home/llhama-usr/Local_LLHAMA/piper_voices"

        self.web_server_message_queue  : mp.Queue  = web_server_message_queue
        self.action_message_queue : mp.Queue  = action_message_queue

        # Prefix for all log messages
        self.class_prefix_message = "[State Machine]"

        # State and synchronization primitives
        self.state: State = State.LOADING
        self.lock = threading.RLock()  # RLock allows reentrant locking from same thread
        self._print_lock = threading.Lock()  # Separate lock for print_once to avoid deadlock

        # Initialize queues and threads
        self.load_queues()


        self.stop_event = threading.Event()

        # Instantiate audio and NLP components
        self.noise_floor_monitor = NoiseFloorMonitor()
        self.awaker = WakeWordListener(self.noise_floor_monitor)
        self.recorder = AudioRecorderClass(noise_floor_monitor=self.noise_floor_monitor)
        self.transcriptor = AudioTranscriptionClass()
        self.transcriptor.init_model(device)

        self.sound_player = SoundPlayer(self.base_path)
        # Small delay to allow pygame's audio system to fully initialize
        # This prevents device conflicts between pygame and PyAudio
        time.sleep(0.5)
        self.speaker = TextToSpeech(voice_dir=voice_dir)

        self.load_threads()

        # Load the command LLM (using int8 for memory efficiency)
        self.command_llm = command_llm
        if not isinstance(self.command_llm, OllamaClient):
            self.command_llm.load_model(use_int8=True)

        # Home Assistant client interface
        self.ha_client: HomeAssistantClient = ha_client

        self._last_printed_message = None
        self.last_transcription = None  # Store the last user query for context

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine init completed")

    # ===============================
    # Queue Management
    # ===============================

    def load_queues(self):
        """Initialize all communication queues used by the state machine."""
        self.result_queue = Queue()         # Wake word detection results
        self.transcription_queue = Queue()  # Transcriptions from audio input
        self.command_queue = Queue()        # Parsed commands to execute
        self.sound_action_queue = Queue()   # Sound actions to play asynchronously
        self.speech_queue = Queue()         # Text responses to speak aloud

        # Store all in a dict for convenience
        self.queues = {
            "result": self.result_queue,
            "transcription": self.transcription_queue,
            "command": self.command_queue,
            "sound_action": self.sound_action_queue,
            "speech": self.speech_queue,
        }

    # ===============================
    # Thread Management
    # ===============================

    def load_threads(self):
        """Initialize worker threads."""

        # Start background threads
        self.wakeword_thread = threading.Thread(target=self.awaker.listen_for_wake_word, args=(self.result_queue,))
        self.wakeword_thread.daemon = True
        self.wakeword_thread.start()

        self.sound_thread = threading.Thread(target=self.sound_player_worker)
        self.sound_thread.daemon = True
        self.sound_thread.start()

        self.command_worker_thread = threading.Thread(target=self.command_worker, daemon=True).start()       

        # Store all in a dict for easy access
        self.threads = {
            "wakeword": self.wakeword_thread,
            "sound": self.sound_thread,
            "commands" : self.command_worker_thread
        }

    # ===============================
    # Stop Logic
    # ===============================
    def stop(self):
        """
        Cleanly stop all background threads and prepare for shutdown or reset.
        Thread-safe: Uses stop_event and sentinel values to signal threads.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Shutting down state machine...")
        self.stop_event.set()

        # Unblock any threads waiting on queues with sentinel values
        try:
            self.sound_action_queue.put(None, timeout=1)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send stop signal to sound queue: {e}")
        
        try:
            self.result_queue.put(None, timeout=1)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send stop signal to result queue: {e}")

        # Join threads if running
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=3)
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {name} thread stopped.")

        # Clean up GPU-related or heavy resources
        for attr in ("awaker", "transcriptor", "speaker"):
            if hasattr(self, attr):
                delattr(self, attr)
                setattr(self, attr, None)

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine stopped.")

    def print_once(self, message, end='\n'):
        with self._print_lock:
            if message != self._last_printed_message:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {message}", end=end)
                self._last_printed_message = message

    def get_state(self):
        """Thread-safe method to get current state."""
        with self.lock:
            return self.state

    def set_noise_floor(self, value):
        """Thread-safe method to set noise floor."""
        with self.lock:
            self.noise_floor = value

    def get_noise_floor(self):
        """Thread-safe method to get noise floor."""
        with self.lock:
            return self.noise_floor

    # ----------------------------------------
    # Restart logic
    # ----------------------------------------
    def restart(self):
        """
        Stop all components and restart the state machine cleanly.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Restarting state machine...")

        # Stop existing threads and clear resources
        self.stop()

        # Recreate stop event, queues, and threads
        self.stop_event = Event()
        self.load_queues()
        self.load_threads()

        # Join threads
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=3)
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {name} thread stopped.")

        # Delete or reset GPU-heavy components
        for attr in ("awaker", "transcriptor", "speaker"):
            if hasattr(self, attr):
                delattr(self, attr)
                setattr(self, attr, None)

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine stopped.")

    def command_worker(self):
        """
        @brief Thread worker that processes transcriptions and parses commands using the LLM.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.PARSING_VOICE:
            try:
                transcription = self.transcription_queue.get(timeout=2)
                self.last_transcription = transcription  # Store for later use
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Got transcription: {transcription}")
                message = f"{self.class_prefix_message} [User Prompt]: {transcription}"
                self.send_messages(message)

            except Empty:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Transcription queue timeout after 2s, returning to LISTENING")
                self.transition(State.LISTENING)
                return
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to get transcription from queue: {type(e).__name__}: {e}")
                self.transition(State.LISTENING)
                return
            
            if not isinstance(self.command_llm, OllamaClient):
                structured_output = self.command_llm.parse_with_llm(transcription)
            else:
                structured_output = self.command_llm.send_message(transcription)

            if structured_output:
                if structured_output.get("commands"):
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Structured Commands: {structured_output}")
                    try:
                        self.command_queue.put(structured_output, timeout=1)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully put command into queue")
                        self.transition(State.SEND_COMMANDS)
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue command: {type(e).__name__}: {e}")
                        self.transition(State.LISTENING)

                elif structured_output.get("nl_response"):
                    nl_message = structured_output.get("nl_response")
                    lang = structured_output.get("language")
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] NL Response: {nl_message}")
                    try:
                        self.speech_queue.put([nl_message, lang], timeout=1)
                        message = f"{self.class_prefix_message} [LLM Reply]: {nl_message}"
                        self.send_messages(message)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully put NL response into speech queue")
                        self.transition(State.SPEAKING)
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue speech: {type(e).__name__}: {e}")
                        self.transition(State.LISTENING)

                else:
                    message_to_speak = "No valid commands or responses extracted, Please try again."
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No valid commands or responses extracted.")
                    try:
                        self.speech_queue.put([message_to_speak, "en"], timeout=1)
                        self.transition(State.SPEAKING)
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue error message: {type(e).__name__}: {e}")
                        self.transition(State.LISTENING)

    def sound_player_worker(self):
        """
        @brief Background thread that plays queued sound actions asynchronously.
        """
        while not self.stop_event.is_set():
            try:
                sound_action = self.sound_action_queue.get(timeout=1)
                if sound_action is None:
                    continue
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Playing sound: {sound_action}")
                self.sound_player.play(sound_action)
            except Empty:
                continue
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Sound player worker error: {type(e).__name__}: {e}")
                time.sleep(0.5)  # Brief delay before retry to avoid tight error loop

    def play_sound(self, sound_action):
        """
        @brief Enqueue a sound action to be played asynchronously by the sound thread.
        @param sound_action The SoundActions enum member to play.
        """
        try:
            self.sound_action_queue.put(sound_action, timeout=1)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to queue sound action: {type(e).__name__}: {e}")

    def transition(self, new_state: State):
        """
        @brief Safely transition the state machine to a new state.
        @param new_state The new State to transition to.
        """
        if self.lock.acquire(timeout=2):
            try:
                old_state = self.state
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Transitioning from {old_state} to {new_state}")
                self.state = new_state
            finally:
                self.lock.release()
        else:
            # Could not acquire lock - log with current state read (unsafe but informational)
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Lock timeout: failed to transition to {new_state} (lock held for >2s)")

    def start_recording(self):
        """
        @brief Start audio recording and enqueue transcription if valid.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.RECORDING:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording...")
            # Pause wake word detection to free audio device
            self.awaker.pause()
            time.sleep(0.5)  # Allow time for wake word listener to cleanup
            try:
                noise_floor_val = self.get_noise_floor()
                transcription = self.recorder.record_audio(self.transcriptor, noise_floor_val)
                transcription_words = len(str.split(transcription, " "))
                if transcription_words > 4:
                    try:
                        self.transcription_queue.put(transcription, timeout=1)
                        self.transition(State.PARSING_VOICE)
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue transcription: {type(e).__name__}: {e}")
                        self.transition(State.LISTENING)
                else:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Transcription only had {transcription_words} words, returning to listening")
                    self.transition(State.LISTENING)
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed: {type(e).__name__}: {e}")
                self.transition(State.LISTENING)

    def speak(self):
        """
        @brief Speak the next queued speech response and play closing sound.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.SPEAKING:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Speaking response...")
            # Pause wake word detection to free audio device
            self.awaker.pause()
            time.sleep(0.5)  # Allow time for wake word listener to cleanup
            try:
                transcription = self.speech_queue.get(timeout=2)
                self.speaker.speak(transcription[0], transcription[1])
                time.sleep(0.3)  # delay for more natural interactions
                if not isinstance(self.command_llm, OllamaClient):
                    self.sound_player.play(SoundActions.action_closing)
                self.transition(State.LISTENING)
            except Empty:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Speech queue timeout after 2s, returning to LISTENING")
                self.transition(State.LISTENING)
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Speaking failed: {type(e).__name__}: {e}")
                self.transition(State.LISTENING)

    def handle_error(self):
        """
        @brief Handle errors by transitioning to ERROR state, playing error sound, and returning to LISTENING.
        """
        with self.lock:
            current_state = self.state

        if current_state != State.ERROR:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] An error occurred.")
            self.transition(State.ERROR)
            self.sound_player.play(SoundActions.system_error)
            time.sleep(2)
            self.transition(State.LISTENING)

    def monitor_messages(self):
        try:
            message = self.action_message_queue.get(timeout=0.01)  # mp.Queue
            if isinstance(message, dict):
                msg_type = message.get("type")
                if msg_type == "ollama_command":
                    command_data = message.get("data")
                    try:
                        self.transcription_queue.put(command_data, timeout=1)
                        self.transition(State.PARSING_VOICE)
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to queue command from web: {type(e).__name__}: {e}")

            elif isinstance(message, str):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unknown message {message}")

            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unexpected message type {type(message)}")

        except Empty:
            # Queue empty, safe to ignore
            return

        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Message Queue Error! {repr(e)}")
            self.transition(State.ERROR)

    def send_messages(self, message):
        try:
            message_dict = {
                "type": "web_ui_message",
                "data": message
            }
            self.web_server_message_queue.put(message_dict, timeout=1)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send message to web server: {type(e).__name__}: {e}")

    def run(self):
        
            time.sleep(0.1)  # Avoid busy waiting, reduce CPU load

            self.monitor_messages()

            # Process wake word detection results
            if not self.result_queue.empty():
                try:
                    wakeword_data = self.result_queue.get(timeout=0.5)

                    with self.lock:
                        current_state = self.state

                    if current_state == State.LISTENING and wakeword_data:
                        self.print_once(f"Wakeword detected! Transitioning to RECORDING. Noise Floor is {wakeword_data}")
                        self.set_noise_floor(wakeword_data)
                        # Clear any remaining wake word events to avoid stale data
                        try:
                            while not self.result_queue.empty():
                                self.result_queue.get_nowait()
                        except Empty:
                            pass
                        except Exception as e:
                            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error clearing wake word queue: {type(e).__name__}: {e}")

                        self.transition(State.RECORDING)
                except Empty:
                    pass  # Queue became empty between check and get, safe to ignore
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to process wake word: {type(e).__name__}: {e}")

            with self.lock:
                current_state = self.state

            if current_state == State.LISTENING:
                # Ensure wake word detection is resumed in listening state
                if not self.awaker.pause_event.is_set():
                    self.awaker.resume()
                self.print_once("Listening for input...", end="\r")

            elif current_state == State.RECORDING:
                self.print_once("Recording state active.")
                self.play_sound(SoundActions.system_awake)
                self.start_recording()

            elif current_state == State.PARSING_VOICE:
                self.print_once("Generating state active.")
                self.command_worker()

            elif current_state == State.SEND_COMMANDS:
                self.print_once("Sending commands to HA client.")
                try:
                    command = self.command_queue.get_nowait()
                    # Extract language from command
                    language = command.get("language", "en")
                    
                    command_result = self.ha_client.send_commands(command)
                    
                    if command_result:
                        # Check if any results are simple functions
                        has_simple_function = any(result.get("type") == "simple_function" for result in command_result if isinstance(result, dict))
                        
                        if has_simple_function:
                            # Simple functions present: send only simple function results to LLM
                            if isinstance(self.command_llm, OllamaClient):
                                # Extract only simple function results
                                simple_function_results = [r for r in command_result if isinstance(r, dict) and r.get("type") == "simple_function"]
                                
                                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Simple function result(s) received: {simple_function_results}")
                                
                                # Send only simple function results for natural language conversion with original query for context
                                user_query_context = f"\n\nOriginal user query: {self.last_transcription}" if self.last_transcription else ""
                                llm_input = f"Convert these function results into a natural language response in {language} language: {simple_function_results}{user_query_context}"
                                
                                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Sending to LLM for NL conversion")
                                nl_output = self.command_llm.send_message(llm_input, message_type="response")
                                
                                if nl_output and nl_output.get("nl_response"):
                                    nl_message = nl_output.get("nl_response")
                                    lang = nl_output.get("language", language)  # Fallback to original language
                                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] LLM converted response: {nl_message}")
                                    message = f"{self.class_prefix_message} [LLM Reply]: {nl_message}"
                                    self.send_messages(message)
                                    try:
                                        self.speech_queue.put([nl_message, lang], timeout=1)
                                        self.transition(State.SPEAKING)
                                    except Exception as e:
                                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue speech: {type(e).__name__}: {e}")
                                        self.transition(State.LISTENING)
                                else:
                                    # Fallback: use raw response
                                    fallback_msg = str(simple_function_results)
                                    message = f"{self.class_prefix_message} [Command Result]: {fallback_msg}"
                                    self.send_messages(message)
                                    try:
                                        self.speech_queue.put([fallback_msg, language], timeout=1)
                                        self.transition(State.SPEAKING)
                                    except Exception as e:
                                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue result: {type(e).__name__}: {e}")
                                        self.transition(State.LISTENING)
                            else:
                                # Non-Ollama client: use raw response
                                message = f"{self.class_prefix_message} [Command Result]: {command_result}"
                                self.send_messages(message)
                                try:
                                    self.speech_queue.put([str(command_result), language], timeout=1)
                                    self.transition(State.SPEAKING)
                                except Exception as e:
                                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue result: {type(e).__name__}: {e}")
                                    self.transition(State.LISTENING)
                        else:
                            # Pure HA commands: just play success sound, no verbal feedback
                            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] HA command(s) executed successfully: {command_result}")
                            message = f"{self.class_prefix_message} [HA Command Result]: {command_result}"
                            self.send_messages(message)
                            self.play_sound(SoundActions.system_awake)
                            self.transition(State.LISTENING)
                    else:
                        self.play_sound(SoundActions.system_awake)
                        self.transition(State.LISTENING)
                except Empty:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Command queue empty when expected, returning to LISTENING")
                    self.transition(State.LISTENING)
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to send command: {type(e).__name__}: {e}")
                    self.transition(State.LISTENING)

            elif current_state == State.NO_COMMANDS:
                self.print_once("No commands available.")
                self.sound_player.play(SoundActions.system_error, 0.5)
                self.transition(State.LISTENING)

            elif current_state == State.SPEAKING:
                self.print_once("Speaking state active.")
                self.speak()
                self.transition(State.LISTENING)

            elif current_state == State.ERROR:
                self.print_once("Error state active.")
                self.handle_error()