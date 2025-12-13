"""
State Machine Orchestrator

This module contains the main StateMachineInstance class that coordinates
all state machine components and manages the main run loop.
"""

# === System Imports ===
import time
from queue import Empty

# === Custom Imports ===
from ..audio_output import SoundActions
from ..home_assistant import HomeAssistantClient
from ..ollama import OllamaClient
from ..shared_logger import LogLevel

# === Component Imports ===
from ..state_components import (
    AudioComponentManager,
    ChatHandler,
    CommandProcessor,
    MessageHandler,
    QueueManager,
    StateHandlers,
    StateTransitionManager,
    ThreadManager,
)
from .core_state import State
from .workers import WorkerThreads


class StateMachineInstance:
    """
    Core state machine managing voice assistant states, audio input/output,
    command processing, and interactions.

    This class acts as a coordinator, delegating responsibilities to specialized
    components while maintaining the main orchestration logic.
    """

    # Expose State enum at class level for easier access
    State = State

    def __init__(
        self,
        command_llm,
        ha_client,
        base_path=None,
        action_message_queue=None,
        web_server_message_queue=None,
        chat_message_queue=None,
        preset_response_queue=None,
        system_controller=None,
        language_models=None,
        whisper_model="turbo",
        chat_config=None,
    ):
        """
        Initialize the state machine, threads, queues, and component instances.

        @param command_llm The LLM instance used for command parsing
        @param ha_client The Home Assistant client interface
        @param base_path Base path for audio files
        @param action_message_queue Queue for action messages
        @param web_server_message_queue Queue for web server messages
        @param chat_message_queue Queue for WebUI chat messages (bypasses state machine)
        @param preset_response_queue Queue for preset API responses
        @param system_controller Reference to the system controller for restart coordination
        @param language_models Dictionary mapping language codes to TTS model filenames
        @param whisper_model Whisper model name to use (e.g., 'turbo', 'medium', 'small')
        @param chat_config Dictionary with ChatHandler configuration (max_tokens, context parameters)
        """
        print(f"[State Machine] [{LogLevel.INFO.name}] Initializing state machine...")

        self.base_path = base_path
        self.system_controller = system_controller
        self.preset_response_queue = preset_response_queue
        self.class_prefix_message = "[State Machine]"
        self.from_webui = False  # Track if current request is from WebUI
        self.language_models = language_models  # Store for restart
        self.whisper_model = whisper_model  # Store for restart
        self.chat_config = chat_config or {}  # Store for restart

        voice_dir = "/home/llhama-usr/Local_LLHAMA/piper_voices"
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Voice directory: {voice_dir}"
        )

        # Initialize component managers
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing queue manager..."
        )
        self.queue_manager = QueueManager()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing audio components (this may take a moment)..."
        )
        self.audio_manager = AudioComponentManager(
            base_path, voice_dir, language_models, whisper_model
        )
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio components initialized successfully"
        )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing thread manager..."
        )
        self.thread_manager = ThreadManager()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing state transition manager..."
        )
        self.state_manager = StateTransitionManager(
            State.LOADING, self.class_prefix_message
        )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing message handler..."
        )
        self.message_handler = MessageHandler(
            action_message_queue, web_server_message_queue, self.class_prefix_message
        )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing command processor..."
        )
        self.command_processor = CommandProcessor(
            command_llm, self.class_prefix_message
        )

        # Initialize state handlers (delegates for state-specific logic)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing state handlers..."
        )
        self.state_handlers = StateHandlers(self)

        # Initialize worker threads manager
        self.workers = WorkerThreads(self)

        # Load the command LLM
        self.command_llm = command_llm
        if not isinstance(self.command_llm, OllamaClient):
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading non-Ollama LLM model..."
            )
            self.command_llm.load_model(use_int8=True)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] LLM model loaded"
            )
        else:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using Ollama client (no local model loading required)"
            )

        # Home Assistant client interface
        self.ha_client: HomeAssistantClient = ha_client
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Home Assistant client connected"
        )

        # Initialize ChatHandler for WebUI chat messages (bypasses state machine)
        self.chat_handler = None
        if chat_message_queue:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing chat handler for WebUI..."
            )
            self.chat_handler = ChatHandler(
                chat_queue=chat_message_queue,
                command_llm=command_llm,
                ha_client=ha_client,
                message_handler=self.message_handler,
                log_prefix="[Chat Handler]",
                max_tokens=self.chat_config.get("max_tokens", 4096),
                default_context_words=self.chat_config.get(
                    "default_context_words", 400
                ),
                min_context_words=self.chat_config.get("min_context_words", 100),
                context_reduction_factor=self.chat_config.get(
                    "context_reduction_factor", 0.7
                ),
                history_exchanges=self.chat_config.get("history_exchanges", 3),
            )
            self.chat_handler.start()
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Chat handler initialized and started"
            )
        else:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] No chat queue provided - chat handler disabled"
            )

        # Start worker threads
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting worker threads..."
        )
        self._start_worker_threads()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Worker threads started"
        )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine initialization completed successfully"
        )

    # ===============================
    # Thread Workers
    # ===============================

    def _start_worker_threads(self):
        """
        Initialize and start all worker threads.
        """
        self.thread_manager.register_thread(
            "wakeword",
            target=self.audio_manager.awaker.listen_for_wake_word,
            args=(self.queue_manager.result_queue,),
        )
        self.thread_manager.register_thread(
            "sound", target=self.workers.sound_player_worker
        )
        self.thread_manager.register_thread(
            "commands", target=self.workers.command_worker
        )
        self.thread_manager.register_thread(
            "calendar", target=self.workers.calendar_checker_worker
        )

    # ===============================
    # Public Interface Methods
    # ===============================

    def play_sound(self, sound_action):
        """
        Enqueue a sound action to be played asynchronously.

        @param sound_action SoundActions enum value to play
        """
        self.queue_manager.put_safe(
            self.queue_manager.sound_action_queue,
            sound_action,
            log_prefix=self.class_prefix_message,
        )

    def get_state(self):
        """
        Get current state (for external access).

        @return Current State enum value
        """
        return self.state_manager.get_state()

    def transition(self, new_state: State):
        """
        Transition to a new state (for external access).

        @param new_state New State to transition to
        """
        self.state_manager.transition(new_state)

    # ===============================
    # Lifecycle Methods
    # ===============================

    def stop(self):
        """
        Cleanly stop all background threads and prepare for shutdown or reset.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Shutting down state machine..."
        )

        # Signal threads to stop
        self.thread_manager.stop_all(log_prefix=self.class_prefix_message)

        # Send sentinel values to unblock queues
        self.queue_manager.put_safe(
            self.queue_manager.sound_action_queue,
            None,
            log_prefix=self.class_prefix_message,
        )
        self.queue_manager.put_safe(
            self.queue_manager.result_queue, None, log_prefix=self.class_prefix_message
        )

        # Clean up audio components
        self.audio_manager.cleanup()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine stopped."
        )

    def restart(self):
        """
        Stop all components and restart the state machine cleanly.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Restarting state machine..."
        )

        # Stop existing threads and clear resources
        self.stop()

        # Reset and recreate components
        self.thread_manager.reset()
        self.queue_manager = QueueManager()

        voice_dir = "/home/llhama-usr/Local_LLHAMA/piper_voices"
        self.audio_manager = AudioComponentManager(
            self.base_path, voice_dir, self.language_models
        )

        # Recreate workers
        self.workers = WorkerThreads(self)

        # Restart worker threads
        self._start_worker_threads()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine restarted."
        )

    # ===============================
    # Message and Wake Word Processing
    # ===============================

    def _process_incoming_messages(self):
        """
        Check and process incoming messages from web server or other sources.
        """
        message = self.message_handler.check_incoming_messages()

        if message is None:
            return

        if isinstance(message, dict):
            msg_type = message.get("type")

            if msg_type == "ollama_command":
                self._handle_ollama_command_message(message.get("data"))
            elif msg_type == "restart_system":
                self._handle_restart_system_message()
            elif msg_type == "preset_request":
                self._handle_preset_request_message(message)
            elif msg_type == "error":
                self.state_manager.transition(State.ERROR)
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unknown message type: {msg_type}"
                )

        elif isinstance(message, str):
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Received legacy string message: {message}"
            )

    def _handle_ollama_command_message(self, message_data):
        """
        Handle incoming Ollama command from web interface.

        @param message_data Message data containing command and metadata
        """
        # Extract command data, from_webui flag, and client_id
        if isinstance(message_data, dict):
            command_data = message_data.get("data", message_data)
            from_webui = message_data.get("from_webui", True)
            client_id = message_data.get("client_id")
        else:
            command_data = message_data
            from_webui = True
            client_id = None

        # Package transcription with from_webui flag and client_id
        transcription_data = {
            "text": command_data,
            "from_webui": from_webui,
            "client_id": client_id,
        }

        success = self.queue_manager.put_safe(
            self.queue_manager.transcription_queue,
            transcription_data,
            log_prefix=self.class_prefix_message,
        )
        if success:
            self.state_manager.transition(State.PARSING_VOICE)

    def _handle_restart_system_message(self):
        """
        Handle system restart request.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restart system request received from web UI"
        )

        if self.system_controller:
            try:
                # Send initial restart message
                message = "🔄 System restart initiated... This may take 30-60 seconds."
                self.message_handler.send_to_web_server(message)

                # Small delay to ensure message is sent before stopping
                import time

                time.sleep(0.5)

                # Set the stop flag
                self.system_controller._should_stop.set()
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Restart signal sent to system controller"
                )

            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to trigger restart: {type(e).__name__}: {e}"
                )
                message = f"❌ System restart failed: {str(e)}"
                self.message_handler.send_to_web_server(message)
        else:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Cannot restart: system_controller reference not set"
            )
            message = f"{self.class_prefix_message} [System Error]: Restart not available (no controller reference)"
            self.message_handler.send_to_web_server(message)

    def _handle_preset_request_message(self, message):
        """
        Handle preset-related requests from web UI.
        Processes the request and sends response back via preset_response_queue.
        """
        request_type = message.get("request_type")
        request_id = message.get("request_id")
        data = message.get("data", {})

        if not request_id:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Preset request missing request_id"
            )
            return

        # Validate preset_response_queue is available
        if not self.preset_response_queue:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Preset response queue not available"
            )
            return

        try:
            # Get settings loader from system controller
            if not self.system_controller or not hasattr(
                self.system_controller, "loader"
            ):
                self.preset_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "message": "Settings loader not available",
                    }
                )
                return

            loader = self.system_controller.loader

            # Process different request types
            if request_type == "list_presets":
                presets = loader.list_presets()
                self.preset_response_queue.put(
                    {"request_id": request_id, "status": "ok", "presets": presets}
                )

            elif request_type == "get_preset_info":
                preset_id = data.get("preset_id")
                info = loader.get_preset_info(preset_id)
                if info:
                    self.preset_response_queue.put(
                        {"request_id": request_id, "status": "ok", "preset": info}
                    )
                else:
                    self.preset_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "error",
                            "message": f"Preset '{preset_id}' not found",
                            "not_found": True,
                        }
                    )

            elif request_type == "apply_preset":
                preset_id = data.get("preset_id")
                info = loader.get_preset_info(preset_id)
                if not info:
                    self.preset_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "error",
                            "message": f"Preset '{preset_id}' not found",
                            "not_found": True,
                        }
                    )
                    return

                success = loader.apply_preset(preset_id)
                if success:
                    self.preset_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "ok",
                            "message": f"Preset '{info['name']}' applied successfully. Restart required for changes to take effect.",
                            "preset_name": info["name"],
                            "restart_required": True,
                        }
                    )
                else:
                    self.preset_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "error",
                            "message": f"Failed to apply preset '{preset_id}'",
                        }
                    )

            elif request_type == "validate_preset":
                preset_id = data.get("preset_id")
                is_valid, errors = loader.validate_preset(preset_id)
                self.preset_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "ok",
                        "is_valid": is_valid,
                        "errors": errors,
                    }
                )

            elif request_type == "create_preset":
                success, message = loader.preset_loader.create_preset(data)
                if success:
                    self.preset_response_queue.put(
                        {"request_id": request_id, "status": "ok", "message": message}
                    )
                else:
                    self.preset_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "error",
                            "message": message,
                        }
                    )

            elif request_type == "get_current_config":
                ollama_model = loader.ollama_model
                whisper_model = loader.get_whisper_model()
                language_models = loader.get_language_models()

                # Get active preset ID if available
                active_preset = None
                try:
                    active_preset = loader.get_setting("_system", "active_preset")
                    if active_preset:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Active preset: {active_preset}"
                        )
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not retrieve active preset: {e}"
                    )

                self.preset_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "ok",
                        "current_config": {
                            "llm_model": ollama_model,
                            "whisper_model": whisper_model,
                            "languages": list(language_models.keys()),
                            "active_preset": active_preset,
                        },
                    }
                )

            else:
                self.preset_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "message": f"Unknown preset request type: {request_type}",
                    }
                )

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error handling preset request: {type(e).__name__}: {e}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Traceback:\n{error_details}"
            )

            if self.preset_response_queue:
                self.preset_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "message": f"{type(e).__name__}: {str(e)}",
                    }
                )
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Cannot send error response - preset_response_queue is None"
                )

    def _process_wake_word_detection(self):
        """
        Check and process wake word detection results.
        """
        if not self.queue_manager.result_queue.empty():
            try:
                wakeword_data = self.queue_manager.result_queue.get(timeout=0.5)
                current_state = self.state_manager.get_state()

                if current_state == State.LISTENING and wakeword_data:
                    self.state_manager.print_once(
                        f"Wakeword detected! Transitioning to RECORDING. Noise Floor is {wakeword_data}"
                    )
                    self.audio_manager.set_noise_floor(wakeword_data)

                    # Clear any remaining wake word events to avoid stale data
                    self.queue_manager.clear_queue(
                        self.queue_manager.result_queue,
                        log_prefix=self.class_prefix_message,
                    )

                    self.state_manager.transition(State.RECORDING)

            except Empty:
                pass  # Queue became empty between check and get
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to process wake word: {type(e).__name__}: {e}"
                )

    # ===============================
    # Main Run Loop
    # ===============================

    def run(self):
        """
        Main state machine run loop - processes one cycle.
        """
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
