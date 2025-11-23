# === System Imports ===
import time
from enum import Enum
from queue import Empty

# === Custom Imports ===
from .Audio_Output import SoundActions
from .Home_Assistant_Interface import HomeAssistantClient
from .Ollama_Client import OllamaClient
from .Shared_Logger import LogLevel

# === Component Imports ===
from .state_components import (
    QueueManager,
    AudioComponentManager,
    ThreadManager,
    StateTransitionManager,
    MessageHandler,
    CommandProcessor,
    StateHandlers,
)


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
# Main State Machine
# ===============================

class StateMachineInstance:
    """
    @brief Core state machine managing voice assistant states, audio input/output, command processing, and interactions.
    
    This class now acts as a coordinator, delegating responsibilities to specialized components.
    """

    # Expose State enum at class level for easier access
    State = State

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

        # Initialize component managers
        self.queue_manager = QueueManager()
        self.audio_manager = AudioComponentManager(device, base_path, voice_dir)
        self.thread_manager = ThreadManager()
        self.state_manager = StateTransitionManager(State.LOADING, self.class_prefix_message)
        self.message_handler = MessageHandler(action_message_queue, web_server_message_queue, self.class_prefix_message)
        self.command_processor = CommandProcessor(command_llm, self.class_prefix_message)
        
        # Initialize state handlers (delegates for state-specific logic)
        self.state_handlers = StateHandlers(self)

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
        """Thread worker that processes transcriptions - delegates to state handlers."""
        current_state = self.state_manager.get_state()
        if current_state == State.PARSING_VOICE:
            self.state_handlers._command_worker()

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
    # Message and Wake Word Processing
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

        # Delegate state handling to StateHandlers
        current_state = self.state_manager.get_state()

        if current_state == State.LISTENING:
            self.state_handlers.handle_listening()
        elif current_state == State.RECORDING:
            self.state_handlers.handle_recording()
        elif current_state == State.PARSING_VOICE:
            self.state_handlers.handle_parsing_voice()
        elif current_state == State.SEND_COMMANDS:
            self.state_handlers.handle_send_commands()
        elif current_state == State.NO_COMMANDS:
            self.state_handlers.handle_no_commands()
        elif current_state == State.SPEAKING:
            self.state_handlers.handle_speaking()
        elif current_state == State.ERROR:
            self.state_handlers.handle_error()
