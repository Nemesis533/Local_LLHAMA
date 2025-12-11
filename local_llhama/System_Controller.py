"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This module defines the LocalLLHamaSystem class, which orchestrates the setup,
initialization, and execution of the LLHAMA automation system components.
"""

# === System Imports ===
import subprocess
import threading
import time

from .error_handler import ErrorHandler
from .home_assistant import HomeAssistantClient
from .PostgreSQL_Client import PostgreSQLClient

# === Custom Imports ===
from .Settings_Loader import SettingLoaderClass
from .Shared_Logger import LogLevel
from .state_machine import StateMachineInstance


class LocalLLHamaSystemController:
    """
    @class LocalLLHamaSystem
    @brief Handles setup, initialization, and execution of the Local LLHAMA system.
    """

    def __init__(self, base_path):
        self.class_prefix_message = "[Controller]"
        self.base_path = base_path
        self.web_server_message_queue = None
        self.action_message_queue = None
        self.chat_message_queue = None
        self.preset_response_queue = None
        self.loader: SettingLoaderClass = None
        self.monitor_thread = None
        self.command_llm = None
        self.state_machine: StateMachineInstance = None
        self._should_stop = threading.Event()
        self.started = False

        # Initialize PostgreSQL client once for the entire system
        self.pg_client = None
        try:
            self.pg_client = PostgreSQLClient()
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] PostgreSQL client initialized"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] PostgreSQL not available: {repr(e)}"
            )

    # === Setup & Initialization Methods ===

    def setup_settings(self):
        """
        Load application settings from file.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading Settings")
        loader = SettingLoaderClass(self.base_path)
        loader.load()
        loader.apply([])
        self.loader = loader

        # Reload prompts with system settings
        from .LLM_Prompts import reload_prompts

        reload_prompts(
            settings_loader=loader, system_settings=loader.get_system_settings()
        )

        return loader

    def setup_home_assistant(self, loader: SettingLoaderClass):
        """
        Initialize the Home Assistant client.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up Home Assistant"
        )
        start = time.time()
        ha_client = HomeAssistantClient()
        loader.apply([ha_client])
        ha_client.initialize_HA(
            allow_internet_searches=loader.allow_internet_searches,
            pg_client=self.pg_client,
        )
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Home Assistant initialized in {time.time() - start:.2f} seconds"
        )
        return ha_client

    def load_llm_models(self, loader: SettingLoaderClass, ha_client):
        """
        Load LLM models from disk or remote config.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading LLMs")
        start = time.time()
        llm = loader.load_llm_models(ha_client)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] LLM models loaded in {time.time() - start:.2f} seconds"
        )
        return llm

    def setup_state_machine(self, loader, llm, ha_client):
        """
        Setup the core automation state machine.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up the state machine"
        )
        start = time.time()

        # Get language models configuration from settings
        language_models = loader.get_language_models()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded language models: {list(language_models.keys())}"
        )

        # Get whisper model configuration from settings
        whisper_model = loader.get_whisper_model()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Whisper model: {whisper_model}"
        )

        # Get ChatHandler configuration from settings
        chat_config = loader.get_chat_handler_config()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] ChatHandler config loaded: max_tokens={chat_config['max_tokens']}"
        )

        sm = StateMachineInstance(
            llm,
            ha_client,
            base_path=self.base_path,
            action_message_queue=self.action_message_queue,
            web_server_message_queue=self.web_server_message_queue,
            chat_message_queue=self.chat_message_queue,
            preset_response_queue=self.preset_response_queue,
            system_controller=self,
            language_models=language_models,
            whisper_model=whisper_model,
            chat_config=chat_config,
        )
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine initialized in {time.time() - start:.2f} seconds"
        )
        return sm

    def apply_additional_settings(self, loader, state_machine):
        """
        Apply runtime configuration to state machine components.
        """
        start = time.time()
        loader.apply([state_machine.audio_manager.awaker])
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Settings applied to vitality and awaker in {time.time() - start:.2f} seconds"
        )

    # === Audio Handling ===

    def check_mic_volume(self):
        """
        Display current microphone volume using pactl (PulseAudio).
        """
        try:
            result = subprocess.run(
                ["pactl", "list", "sources"], capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] pactl command failed with code {result.returncode}"
                )
                if result.stderr:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Error: {result.stderr[:100]}"
                    )
                return

            volume_found = False
            for line in result.stdout.splitlines():
                if "Volume" in line:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {line}")
                    volume_found = True

            if not volume_found:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No volume information found"
                )

        except subprocess.TimeoutExpired:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] pactl command timed out after 5 seconds"
            )
        except FileNotFoundError:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] pactl command not found - PulseAudio may not be installed"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to check microphone volume: {repr(e)}"
            )

    def setup_audio(self):
        """
        Configure microphone input volume via PulseAudio.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up system audio"
        )
        start = time.time()

        with ErrorHandler.catch_and_log(
            self.class_prefix_message,
            level=LogLevel.WARNING,
            context="Audio setup",
            suppress=True,
            exceptions=(subprocess.TimeoutExpired, FileNotFoundError, Exception),
        ):
            result = subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to set audio volume (code {result.returncode})"
                )
                if result.stderr:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Error: {result.stderr[:100]}"
                    )
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio volume set successfully"
                )

        # Check volume regardless of setup success
        self.check_mic_volume()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio setup done in {time.time() - start:.2f} seconds"
        )

    # === Execution Methods ===

    def start_system(self):
        """
        Start or restart the Local LLHAMA system components.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] === Starting Local LLHAMA System ==="
        )

        # 1. Reload settings
        try:
            loader = self.setup_settings()
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to load settings: {repr(e)}"
            )
            return False

        # 2. Initialize Home Assistant
        try:
            ha_client = self.setup_home_assistant(loader)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize Home Assistant: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Continuing without Home Assistant"
            )
            ha_client = None

        # 3. Cleanup existing models
        if self.command_llm:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Existing LLM detected, clearing..."
            )
            try:
                del self.command_llm
                self.command_llm = None
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error during LLM cleanup: {repr(e)}"
                )
                self.command_llm = None

        # 4. Load LLM models
        try:
            self.command_llm = self.load_llm_models(loader, ha_client)
            if self.command_llm is None:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] LLM loading returned None"
                )
                return False
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to load LLM models: {repr(e)}"
            )
            import traceback

            traceback.print_exc()
            return False

        # 5. Setup the state machine
        if self.state_machine is not None:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Stopping existing state machine"
            )
            try:
                self.state_machine.stop()
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error stopping state machine: {repr(e)}"
                )

            try:
                del self.state_machine
                self.state_machine = None
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error deleting state machine: {repr(e)}"
                )

        try:
            self.state_machine = self.setup_state_machine(
                loader, self.command_llm, ha_client
            )
            if self.state_machine is None:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] State machine setup returned None"
                )
                return False
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to setup state machine: {repr(e)}"
            )
            import traceback

            traceback.print_exc()
            return False

        # 6. Setup system audio
        try:
            self.setup_audio()
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Audio setup failed: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Continuing without audio configuration"
            )

        # 7. Apply runtime configuration
        try:
            self.apply_additional_settings(loader, self.state_machine)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to apply additional settings: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Continuing with default settings"
            )

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] System Started")

        self.started = True
        return True
