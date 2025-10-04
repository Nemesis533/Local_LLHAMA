"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This module defines the LocalLLHamaSystem class, which orchestrates the setup,
initialization, and execution of the LLHAMA automation system components.
"""

# === System Imports ===
import subprocess
import time
import torch
import gc
import threading

# === Custom Imports ===
from .Settings_Loader import SettingLoaderClass
from .State_Machine import StateMachineInstance
from .Home_Assistant_Interface import HomeAssistantClient
from .Shared_Logger import LogLevel

class LocalLLHamaSystemController:
    """
    @class LocalLLHamaSystem
    @brief Handles setup, initialization, and execution of the Local LLHAMA system.
    """

    def __init__(self, base_path):
        self.class_prefix_message = "[Controller]"
        self.base_path = base_path
        self.message_queue = None
        self.loader : SettingLoaderClass = None
        self.monitor_thread = None
        self.command_llm = None
        self.state_machine: StateMachineInstance = None
        self._should_stop = threading.Event()


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
        return loader

    def setup_home_assistant(self, loader: SettingLoaderClass):
        """
        Initialize the Home Assistant client.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up Home Assistant")
        start = time.time()
        ha_client = HomeAssistantClient()
        loader.apply([ha_client])
        ha_client.initialize_HA()
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
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up the state machine")
        start = time.time()
        sm = StateMachineInstance(llm, loader.device, ha_client, base_path=self.base_path)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] State machine initialized in {time.time() - start:.2f} seconds"
        )
        return sm

    def apply_additional_settings(self, loader, state_machine):
        """
        Apply runtime configuration to state machine components.
        """
        start = time.time()
        loader.apply([state_machine.awaker])
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Settings applied to vitality and awaker in {time.time() - start:.2f} seconds"
        )

    # === Audio Handling ===

    def check_mic_volume(self):
        """
        Display current microphone volume using pactl (PulseAudio).
        """
        result = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "Volume" in line:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {line}")

    def setup_audio(self):
        """
        Configure microphone input volume via PulseAudio.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Setting up system audio")
        start = time.time()
        subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
        self.check_mic_volume()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Audio setup done in {time.time() - start:.2f} seconds"
        )

    # === Model Memory Management ===

    @staticmethod
    def unload_model(model):
        """
        Unload a PyTorch model from memory and clear CUDA cache.
        """
        if hasattr(model, "model"):
            del model.model
        torch.cuda.empty_cache()
        gc.collect()

    # === Execution Methods ===

    def start_system(self):
        """
        Start or restart the Local LLHAMA system components.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] === Starting Local LLHAMA System ===")

        # 1. Reload settings
        loader = self.setup_settings()

        # 2. Initialize Home Assistant
        ha_client = self.setup_home_assistant(loader)

        # 3. Cleanup existing models
        if self.command_llm:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Existing LLM detected, unloading...")
            if getattr(self.command_llm, "prompt_guard", None):
                self.unload_model(self.command_llm.prompt_guard)
                del self.command_llm.prompt_guard
                self.command_llm.prompt_guard = None

            self.unload_model(self.command_llm)
            del self.command_llm
            self.command_llm = None

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model")

        # 4. Load LLM models
        self.command_llm = self.load_llm_models(loader, ha_client)

        # 5. Setup the state machine
        if self.state_machine is not None:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Stopping existing state machine")
            self.state_machine.stop()
            del self.state_machine
            self.state_machine = None

        self.state_machine = self.setup_state_machine(loader, self.command_llm, ha_client)

        # 6. Setup system audio
        self.setup_audio()

        # 7. Apply runtime configuration
        self.apply_additional_settings(loader, self.state_machine)

        # 8. Patch monitor thread
        if self.monitor_thread:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Updating monitor thread references")
            self.monitor_thread._args = (
                self.message_queue,
                loader,
                ha_client,
                self.state_machine,
            )
            
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting state machine loop")
    
    def run_system(self):        

        # 9. Run the automation loop
        self.state_machine.run()

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] === Local LLHAMA System Running ===")
