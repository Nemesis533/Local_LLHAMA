# === System Imports ===
import threading
from threading import Event
from queue import Queue, Empty
import time
from enum import Enum
import multiprocessing as mp

# === Custom Imports ===
from .Audio_Output import SoundPlayer, SoundActions, TextToSpeech
from .Audio_Input import WakeWordListener, AudioRecorderClass, NoiseFloorMonitor, AudioTranscriptionClass
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


# ===============================
# Helper Classes
# ===============================

class QueueManager:
    """
    @brief Manages all queues used by the state machine for inter-thread communication.
    """
    def __init__(self):
        self.result_queue = Queue()         # Wake word detection results
        self.transcription_queue = Queue()  # Transcriptions from audio input
        self.command_queue = Queue()        # Parsed commands to execute
        self.sound_action_queue = Queue()   # Sound actions to play asynchronously
        self.speech_queue = Queue()         # Text responses to speak aloud

    def get_queue(self, name):
        """Get a specific queue by name."""
        return getattr(self, f"{name}_queue", None)

    def clear_queue(self, queue, log_prefix=""):
        """Safely clear all items from a queue."""
        try:
            while not queue.empty():
                queue.get_nowait()
        except Empty:
            pass
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Error clearing queue: {type(e).__name__}: {e}")

    def put_safe(self, queue, item, timeout=1, log_prefix=""):
        """Safely put an item into a queue with error handling."""
        try:
            queue.put(item, timeout=timeout)
            return True
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Failed to queue item: {type(e).__name__}: {e}")
            return False

    def get_safe(self, queue, timeout=2, log_prefix=""):
        """Safely get an item from a queue with error handling."""
        try:
            return queue.get(timeout=timeout)
        except Empty:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Queue timeout after {timeout}s")
            return None
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.CRITICAL.name}] Failed to get from queue: {type(e).__name__}: {e}")
            return None


class AudioComponentManager:
    """
    @brief Manages all audio-related components including recording, transcription, and playback.
    """
    def __init__(self, device, base_path, voice_dir):
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


class ThreadManager:
    """
    @brief Manages lifecycle of background worker threads.
    """
    def __init__(self):
        self.threads = {}
        self.stop_event = threading.Event()

    def register_thread(self, name, target, args=(), daemon=True):
        """Create and start a new thread."""
        thread = threading.Thread(target=target, args=args, daemon=daemon)
        thread.start()
        self.threads[name] = thread
        return thread

    def stop_all(self, log_prefix=""):
        """Signal all threads to stop and wait for them."""
        self.stop_event.set()
        
        for name, thread in self.threads.items():
            if thread and thread.is_alive():
                thread.join(timeout=3)
                print(f"{log_prefix} [{LogLevel.INFO.name}] {name} thread stopped.")

    def is_stopping(self):
        """Check if stop has been requested."""
        return self.stop_event.is_set()

    def reset(self):
        """Reset the stop event for restart."""
        self.stop_event.clear()


class StateTransitionManager:
    """
    @brief Manages state transitions with validation and logging.
    """
    def __init__(self, initial_state, log_prefix=""):
        self.state = initial_state
        self.lock = threading.RLock()
        self.log_prefix = log_prefix
        self._last_printed_message = None
        self._print_lock = threading.Lock()

    def transition(self, new_state: State):
        """Thread-safe state transition with logging."""
        if self.lock.acquire(timeout=2):
            try:
                old_state = self.state
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] Transitioning from {old_state.name} to {new_state.name}")
                self.state = new_state
            finally:
                self.lock.release()
        else:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Lock timeout: failed to transition to {new_state.name} (lock held for >2s)")

    def get_state(self):
        """Thread-safe getter for current state."""
        with self.lock:
            return self.state

    def print_once(self, message, end='\n'):
        """Print a message only if it differs from the last printed message."""
        with self._print_lock:
            if message != self._last_printed_message:
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] {message}", end=end)
                self._last_printed_message = message


class MessageHandler:
    """
    @brief Handles inter-process message communication with web server and other components.
    """
    def __init__(self, action_queue: mp.Queue, web_server_queue: mp.Queue, log_prefix=""):
        self.action_message_queue = action_queue
        self.web_server_message_queue = web_server_queue
        self.log_prefix = log_prefix

    def send_to_web_server(self, message):
        """Send a message to the web server queue."""
        try:
            message_dict = {
                "type": "web_ui_message",
                "data": message
            }
            self.web_server_message_queue.put(message_dict, timeout=1)
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to send message to web server: {type(e).__name__}: {e}")

    def check_incoming_messages(self):
        """Check for and return any incoming messages from the action queue."""
        try:
            message = self.action_message_queue.get(timeout=0.01)
            return message
        except Empty:
            return None
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Message Queue Error! {repr(e)}")
            return {"type": "error", "data": str(e)}


class CommandProcessor:
    """
    @brief Processes voice commands using LLM and handles command parsing.
    """
    def __init__(self, command_llm, log_prefix=""):
        self.command_llm = command_llm
        self.log_prefix = log_prefix

    def parse_transcription(self, transcription):
        """Parse transcription using LLM and return structured output."""
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Got transcription: {transcription}")
        
        if not isinstance(self.command_llm, OllamaClient):
            structured_output = self.command_llm.parse_with_llm(transcription)
        else:
            structured_output = self.command_llm.send_message(transcription)
        
        return structured_output

    def process_command_result(self, command_result, language="en"):
        """Process command execution results and prepare response."""
        if not command_result:
            return None
        
        # Check if any results are simple functions
        has_simple_function = any(
            result.get("type") == "simple_function" 
            for result in command_result 
            if isinstance(result, dict)
        )
        
        if has_simple_function and isinstance(self.command_llm, OllamaClient):
            # Extract only simple function results
            simple_function_results = [
                r for r in command_result 
                if isinstance(r, dict) and r.get("type") == "simple_function"
            ]
            
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Simple function result(s) received: {simple_function_results}")
            
            # Send for natural language conversion
            llm_input = f"Convert these function results into a natural language response in {language} language: {simple_function_results}"
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Sending to LLM for NL conversion")
            
            return self.command_llm.send_message(llm_input, message_type="response")
        
        return None


# ===============================
# Main State Machine
# ===============================

class StateMachineInstance:
    """
    @brief Core state machine managing voice assistant states, audio input/output, command processing, and interactions.
    """

    def __init__(self, command_llm, device, ha_client, base_path=None, action_message_queue=None, web_server_message_queue=None, system_controller=None):
        """
        @brief Initialize the state machine, threads, queues, and component instances.
        @param command_llm The LLM instance used for command parsing.
        @param device The computation device (e.g., "cuda" or "cpu").
        @param ha_client The Home Assistant client interface.
        @param system_controller Reference to the system controller for restart coordination.
        """
        self.device = device
        self.base_path = base_path
        self.system_controller = system_controller
        self.class_prefix_message = "[State Machine]"
        
        voice_dir = "/home/llhama-usr/Local_LLHAMA/piper_voices"

        # Initialize helper managers
        self.queue_manager = QueueManager()
        self.audio_manager = AudioComponentManager(device, base_path, voice_dir)
        self.thread_manager = ThreadManager()
        self.state_manager = StateTransitionManager(State.LOADING, self.class_prefix_message)
        self.message_handler = MessageHandler(action_message_queue, web_server_message_queue, self.class_prefix_message)
        self.command_processor = CommandProcessor(command_llm, self.class_prefix_message)

        # Load the command LLM
        self.command_llm = command_llm
        if not isinstance(self.command_llm, OllamaClient):
            self.command_llm.load_model(use_int8=True)

        # Home Assistant client interface
        self.ha_client: HomeAssistantClient = ha_client

        # Start worker threads
        self._start_worker_threads()

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine init completed")

    # ===============================
    # Thread Workers
    # ===============================

    def _start_worker_threads(self):
        """Initialize and start all worker threads."""
        self.thread_manager.register_thread(
            "wakeword",
            target=self.audio_manager.awaker.listen_for_wake_word,
            args=(self.queue_manager.result_queue,)
        )
        self.thread_manager.register_thread(
            "sound",
            target=self._sound_player_worker
        )
        self.thread_manager.register_thread(
            "commands",
            target=self._command_worker
        )

    def _sound_player_worker(self):
        """Background thread that plays queued sound actions asynchronously."""
        while not self.thread_manager.is_stopping():
            try:
                sound_action = self.queue_manager.sound_action_queue.get(timeout=1)
                if sound_action is None:
                    continue
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Playing sound: {sound_action}")
                self.audio_manager.sound_player.play(sound_action)
            except Empty:
                continue
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Sound player worker error: {type(e).__name__}: {e}")
                time.sleep(0.5)

    def _command_worker(self):
        """Thread worker that processes transcriptions and parses commands using the LLM."""
        current_state = self.state_manager.get_state()

        if current_state == State.PARSING_VOICE:
            transcription = self.queue_manager.get_safe(
                self.queue_manager.transcription_queue,
                timeout=2,
                log_prefix=self.class_prefix_message
            )
            
            if transcription is None:
                self.state_manager.transition(State.LISTENING)
                return

            message = f"{self.class_prefix_message} [User Prompt]: {transcription}"
            self.message_handler.send_to_web_server(message)

            structured_output = self.command_processor.parse_transcription(transcription)

            if structured_output:
                if structured_output.get("commands"):
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Structured Commands: {structured_output}")
                    success = self.queue_manager.put_safe(
                        self.queue_manager.command_queue,
                        structured_output,
                        log_prefix=self.class_prefix_message
                    )
                    if success:
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully put command into queue")
                        self.state_manager.transition(State.SEND_COMMANDS)
                    else:
                        self.state_manager.transition(State.LISTENING)

                elif structured_output.get("nl_response"):
                    nl_message = structured_output.get("nl_response")
                    lang = structured_output.get("language")
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] NL Response: {nl_message}")
                    
                    success = self.queue_manager.put_safe(
                        self.queue_manager.speech_queue,
                        [nl_message, lang],
                        log_prefix=self.class_prefix_message
                    )
                    
                    if success:
                        message = f"{self.class_prefix_message} [LLM Reply]: {nl_message}"
                        self.message_handler.send_to_web_server(message)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully put NL response into speech queue")
                        self.state_manager.transition(State.SPEAKING)
                    else:
                        self.state_manager.transition(State.LISTENING)

                else:
                    self._queue_error_message("No valid commands or responses extracted, Please try again.")

    def _queue_error_message(self, message):
        """Queue an error message to be spoken."""
        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] {message}")
        success = self.queue_manager.put_safe(
            self.queue_manager.speech_queue,
            [message, "en"],
            log_prefix=self.class_prefix_message
        )
        if success:
            self.state_manager.transition(State.SPEAKING)
        else:
            self.state_manager.transition(State.LISTENING)

    # ===============================
    # Public Interface Methods
    # ===============================

    def play_sound(self, sound_action):
        """Enqueue a sound action to be played asynchronously."""
        self.queue_manager.put_safe(
            self.queue_manager.sound_action_queue,
            sound_action,
            log_prefix=self.class_prefix_message
        )

    def get_state(self):
        """Get current state (for external access)."""
        return self.state_manager.get_state()

    def transition(self, new_state: State):
        """Transition to a new state (for external access)."""
        self.state_manager.transition(new_state)

    # ===============================
    # Lifecycle Methods
    # ===============================

    def stop(self):
        """Cleanly stop all background threads and prepare for shutdown or reset."""
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Shutting down state machine...")
        
        # Signal threads to stop
        self.thread_manager.stop_all(log_prefix=self.class_prefix_message)
        
        # Send sentinel values to unblock queues
        self.queue_manager.put_safe(
            self.queue_manager.sound_action_queue,
            None,
            log_prefix=self.class_prefix_message
        )
        self.queue_manager.put_safe(
            self.queue_manager.result_queue,
            None,
            log_prefix=self.class_prefix_message
        )
        
        # Clean up audio components
        self.audio_manager.cleanup()
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine stopped.")

    def restart(self):
        """Stop all components and restart the state machine cleanly."""
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Restarting state machine...")
        
        # Stop existing threads and clear resources
        self.stop()
        
        # Reset and recreate components
        self.thread_manager.reset()
        self.queue_manager = QueueManager()
        
        voice_dir = "/home/llhama-usr/Local_LLHAMA/piper_voices"
        self.audio_manager = AudioComponentManager(self.device, self.base_path, voice_dir)
        
        # Restart worker threads
        self._start_worker_threads()
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine restarted.")


    # ===============================
    # State Handlers
    # ===============================

    def _handle_listening_state(self):
        """Handle the LISTENING state."""
        # Ensure wake word detection is resumed
        self.audio_manager.resume_wake_word()
        self.state_manager.print_once("Listening for input...", end="\r")

    def _handle_recording_state(self):
        """Handle the RECORDING state."""
        self.state_manager.print_once("Recording state active.")
        self.play_sound(SoundActions.system_awake)
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Recording...")
        self.audio_manager.pause_wake_word()
        
        try:
            transcription = self.audio_manager.record_and_transcribe()
            transcription_words = len(str.split(transcription, " "))
            
            if transcription_words > 4:
                success = self.queue_manager.put_safe(
                    self.queue_manager.transcription_queue,
                    transcription,
                    log_prefix=self.class_prefix_message
                )
                if success:
                    self.state_manager.transition(State.PARSING_VOICE)
                else:
                    self.state_manager.transition(State.LISTENING)
            else:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Transcription only had {transcription_words} words, returning to listening")
                self.state_manager.transition(State.LISTENING)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Recording failed: {type(e).__name__}: {e}")
            self.state_manager.transition(State.LISTENING)

    def _handle_parsing_voice_state(self):
        """Handle the PARSING_VOICE state."""
        self.state_manager.print_once("Generating state active.")
        self._command_worker()

    def _handle_send_commands_state(self):
        """Handle the SEND_COMMANDS state."""
        self.state_manager.print_once("Sending commands to HA client.")
        
        try:
            command = self.queue_manager.command_queue.get_nowait()
            language = command.get("language", "en")
            
            command_result = self.ha_client.send_commands(command)
            
            if command_result:
                # Check if any results are simple functions
                has_simple_function = any(
                    result.get("type") == "simple_function" 
                    for result in command_result 
                    if isinstance(result, dict)
                )
                
                if has_simple_function:
                    self._handle_simple_function_result(command_result, language)
                else:
                    # Pure HA commands: just play success sound, no verbal feedback
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] HA command(s) executed successfully: {command_result}")
                    message = f"{self.class_prefix_message} [HA Command Result]: {command_result}"
                    self.message_handler.send_to_web_server(message)
                    self.play_sound(SoundActions.system_awake)
                    self.state_manager.transition(State.LISTENING)
            else:
                self.play_sound(SoundActions.system_awake)
                self.state_manager.transition(State.LISTENING)
                
        except Empty:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Command queue empty when expected, returning to LISTENING")
            self.state_manager.transition(State.LISTENING)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to send command: {type(e).__name__}: {e}")
            self.state_manager.transition(State.LISTENING)

    def _handle_simple_function_result(self, command_result, language):
        """Handle results from simple functions by converting to natural language."""
        if isinstance(self.command_llm, OllamaClient):
            nl_output = self.command_processor.process_command_result(command_result, language)
            
            if nl_output and nl_output.get("nl_response"):
                nl_message = nl_output.get("nl_response")
                lang = nl_output.get("language", language)
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] LLM converted response: {nl_message}")
                
                message = f"{self.class_prefix_message} [LLM Reply]: {nl_message}"
                self.message_handler.send_to_web_server(message)
                
                success = self.queue_manager.put_safe(
                    self.queue_manager.speech_queue,
                    [nl_message, lang],
                    log_prefix=self.class_prefix_message
                )
                if success:
                    self.state_manager.transition(State.SPEAKING)
                else:
                    self.state_manager.transition(State.LISTENING)
            else:
                # Fallback: use raw response
                simple_function_results = [
                    r for r in command_result 
                    if isinstance(r, dict) and r.get("type") == "simple_function"
                ]
                fallback_msg = str(simple_function_results)
                message = f"{self.class_prefix_message} [Command Result]: {fallback_msg}"
                self.message_handler.send_to_web_server(message)
                
                success = self.queue_manager.put_safe(
                    self.queue_manager.speech_queue,
                    [fallback_msg, language],
                    log_prefix=self.class_prefix_message
                )
                if success:
                    self.state_manager.transition(State.SPEAKING)
                else:
                    self.state_manager.transition(State.LISTENING)
        else:
            # Non-Ollama client: use raw response
            message = f"{self.class_prefix_message} [Command Result]: {command_result}"
            self.message_handler.send_to_web_server(message)
            
            success = self.queue_manager.put_safe(
                self.queue_manager.speech_queue,
                [str(command_result), language],
                log_prefix=self.class_prefix_message
            )
            if success:
                self.state_manager.transition(State.SPEAKING)
            else:
                self.state_manager.transition(State.LISTENING)

    def _handle_speaking_state(self):
        """Handle the SPEAKING state."""
        self.state_manager.print_once("Speaking state active.")
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Speaking response...")
        self.audio_manager.pause_wake_word()
        
        transcription = self.queue_manager.get_safe(
            self.queue_manager.speech_queue,
            timeout=2,
            log_prefix=self.class_prefix_message
        )
        
        if transcription:
            try:
                self.audio_manager.speak_text(transcription[0], transcription[1])
                time.sleep(0.3)  # delay for more natural interactions
                if not isinstance(self.command_llm, OllamaClient):
                    self.audio_manager.sound_player.play(SoundActions.action_closing)
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Speaking failed: {type(e).__name__}: {e}")
        
        self.state_manager.transition(State.LISTENING)

    def _handle_error_state(self):
        """Handle the ERROR state."""
        self.state_manager.print_once("Error state active.")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] An error occurred.")
        self.audio_manager.sound_player.play(SoundActions.system_error)
        time.sleep(2)
        self.state_manager.transition(State.LISTENING)

    def _handle_no_commands_state(self):
        """Handle the NO_COMMANDS state."""
        self.state_manager.print_once("No commands available.")
        self.audio_manager.sound_player.play(SoundActions.system_error, 0.5)
        self.state_manager.transition(State.LISTENING)

    # ===============================
    # Message Processing
    # ===============================

    def _process_incoming_messages(self):
        """Check and process incoming messages from web server or other sources."""
        message = self.message_handler.check_incoming_messages()
        
        if message is None:
            return
        
        if isinstance(message, dict):
            msg_type = message.get("type")
            
            if msg_type == "ollama_command":
                self._handle_ollama_command_message(message.get("data"))
            elif msg_type == "restart_system":
                self._handle_restart_system_message()
            elif msg_type == "error":
                self.state_manager.transition(State.ERROR)
            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unknown message type: {msg_type}")
        
        elif isinstance(message, str):
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Received legacy string message: {message}")

    def _handle_ollama_command_message(self, command_data):
        """Handle incoming Ollama command from web interface."""
        success = self.queue_manager.put_safe(
            self.queue_manager.transcription_queue,
            command_data,
            log_prefix=self.class_prefix_message
        )
        if success:
            self.state_manager.transition(State.PARSING_VOICE)

    def _handle_restart_system_message(self):
        """Handle system restart request."""
        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restart system request received from web UI")
        
        if self.system_controller:
            try:
                self.system_controller._should_stop.set()
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Restart signal sent to system controller")
                message = f"{self.class_prefix_message} [System]: Restarting system..."
                self.message_handler.send_to_web_server(message)
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to trigger restart: {type(e).__name__}: {e}")
                message = f"{self.class_prefix_message} [System Error]: Failed to restart system: {e}"
                self.message_handler.send_to_web_server(message)
        else:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Cannot restart: system_controller reference not set")
            message = f"{self.class_prefix_message} [System Error]: Restart not available (no controller reference)"
            self.message_handler.send_to_web_server(message)

    # ===============================
    # Wake Word Processing
    # ===============================

    def _process_wake_word_detection(self):
        """Check and process wake word detection results."""
        if not self.queue_manager.result_queue.empty():
            try:
                wakeword_data = self.queue_manager.result_queue.get(timeout=0.5)
                current_state = self.state_manager.get_state()

                if current_state == State.LISTENING and wakeword_data:
                    self.state_manager.print_once(f"Wakeword detected! Transitioning to RECORDING. Noise Floor is {wakeword_data}")
                    self.audio_manager.set_noise_floor(wakeword_data)
                    
                    # Clear any remaining wake word events to avoid stale data
                    self.queue_manager.clear_queue(
                        self.queue_manager.result_queue,
                        log_prefix=self.class_prefix_message
                    )
                    
                    self.state_manager.transition(State.RECORDING)
                    
            except Empty:
                pass  # Queue became empty between check and get
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to process wake word: {type(e).__name__}: {e}")

    # ===============================
    # Main Run Loop
    # ===============================

    def run(self):
        """Main state machine run loop - processes one cycle."""
        time.sleep(0.1)  # Avoid busy waiting, reduce CPU load

        # Check for incoming messages
        self._process_incoming_messages()

        # Process wake word detection
        self._process_wake_word_detection()

        # Handle current state
        current_state = self.state_manager.get_state()

        if current_state == State.LISTENING:
            self._handle_listening_state()
        elif current_state == State.RECORDING:
            self._handle_recording_state()
        elif current_state == State.PARSING_VOICE:
            self._handle_parsing_voice_state()
        elif current_state == State.SEND_COMMANDS:
            self._handle_send_commands_state()
        elif current_state == State.NO_COMMANDS:
            self._handle_no_commands_state()
        elif current_state == State.SPEAKING:
            self._handle_speaking_state()
        elif current_state == State.ERROR:
            self._handle_error_state()
