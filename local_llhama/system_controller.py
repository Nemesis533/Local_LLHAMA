"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This script sets up the environment, loads settings, initializes the Home Assistant client,
loads LLM models, configures the state machine, starts a web service for control and monitoring,
and begins processing voice commands and automations.
"""

# === System Imports ===

import subprocess
import time
import torch
import gc
import threading

# === Custom Imports ===
from .SettingsLoader import SettingLoaderClass
from .StateMachine import StateMachineInstance
from .HA_Interfacer import HomeAssistantClient

class SystemContext:
    def __init__(self):
        self.base_path  = None
        self.message_queue = None
        self.loader = None
        self.logger = None
        self.monitor_thread = None
        self.command_llm = None
        self.state_machine :StateMachineInstance = None
        self._should_stop = threading.Event()

def setup_settings(base_path):
    """
    @brief Load application settings from file.

    @param base_path The base directory where settings are located.
    @return An initialized SettingLoaderClass instance.
    """
    print("[Main] Loading Settings")
    loader = SettingLoaderClass(base_path)
    loader.load()
    return loader

def setup_home_assistant(loader):
    """
    @brief Initialize the Home Assistant client.

    @param loader The settings loader.
    @return An initialized HomeAssistantClient instance.
    """
    print("[Main] Setting up Home Assistant")
    start = time.time()
    ha_client = HomeAssistantClient()
    loader.apply([ha_client])
    ha_client.initialize_HA()
    print(f"[Main] Home Assistant initialized in {time.time() - start:.2f} seconds")
    return ha_client

def load_llm_models(loader : SettingLoaderClass, ha_client):
    """
    @brief Load LLM models from disk or remote config.

    @param loader The settings loader.
    @param ha_client The Home Assistant client.
    @return Loaded LLM model instance.
    """
    print("[Main] Loading LLMs")
    start = time.time()
    llm = loader.load_llm_models(ha_client)
    print(f"[Main] LLM models loaded in {time.time() - start:.2f} seconds")
    return llm

def setup_state_machine(loader, llm, ha_client, base_path):
    """
    @brief Setup the core automation state machine.

    @param loader Settings loader instance.
    @param llm The language model used for command processing.
    @param ha_client Home Assistant client.
    @param logger Logger instance.
    @param base_path Application base path.
    @return A configured StateMachineInstance.
    """
    print("[Main] Setting up the state machine")
    start = time.time()
    
    sm = StateMachineInstance(llm, loader.device, ha_client, base_path=base_path)
    print(f"[Main] State machine initialized in {time.time() - start:.2f} seconds")
    return sm

def apply_additional_settings(loader, state_machine):
    """
    @brief Apply runtime configuration to state machine components.

    @param loader The settings loader.
    @param state_machine The state machine instance.
    """
    start = time.time()
    loader.apply([state_machine.awaker])
    print(f"[Main] Settings applied to vitality and awaker in {time.time() - start:.2f} seconds")

def run_state_machine(state_machine):
    """
    @brief Start the state machine's execution loop.

    @param state_machine The state machine instance.
    """

    state_machine.run()


def check_mic_volume():
    """
    @brief Display current microphone volume using pactl (PulseAudio).
    """
    result = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "Volume" in line:
            print(line)

def setup_audio():
    """
    @brief Configure microphone input volume via PulseAudio.
    """
    print("[Main] Setting up system audio")
    start = time.time()
    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
    check_mic_volume()
    print(f"[Main] Audio setup done in {time.time() - start:.2f} seconds")

def unload_model(model):
    if hasattr(model, 'model'):
        del model.model  # Assuming model.model is the PyTorch model
    torch.cuda.empty_cache()
    gc.collect()


def start_system(ctx : SystemContext):
    
    """
    Start or restart the Local LLHAMA system components.

    This function performs a complete system (re)initialization:
    - Reloads configuration settings
    - Initializes the Home Assistant client
    - Loads the language model for processing commands
    - Sets up the automation state machine
    - Prepares audio input and applies runtime parameters
    - Begins the automation loop

    @param ctx A SystemContext object containing shared runtime state.
    """

    # Reload the settings to ensure fresh configuration values    
    loader = setup_settings(ctx.base_path)

    # Initialize the Home Assistant client with settings
    ha_client = None
    ha_client = setup_home_assistant(loader)

    # Load LLM models used for command processing and automations
    if ctx.command_llm:
        if ctx.command_llm.prompt_guard:
            unload_model(ctx.command_llm.prompt_guard)
            del ctx.command_llm.prompt_guard
            ctx.command_llm.prompt_guard = None
        unload_model(ctx.command_llm)  # custom cleanup if implemented
        del ctx.command_llm
        ctx.command_llm = None

    print(f"[Main] Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    ctx.command_llm = load_llm_models(loader, ha_client)

    # Set up the automation state machine with the loaded models and HA client
    if ctx.state_machine is not None:
        ctx.state_machine.stop()
        del ctx.state_machine
        ctx.state_machine = None
    ctx.state_machine = setup_state_machine(loader, ctx.command_llm, ha_client, ctx.base_path)

    # Set microphone input volume and verify levels
    setup_audio()

    # Apply any additional runtime settings (e.g., thresholds, sensitivities) to components
    apply_additional_settings(loader, ctx.state_machine)

    # Patch the monitor thread with current initialized references
    ctx.monitor_thread._args = (ctx.message_queue, loader, ha_client, ctx.state_machine)

    # Start the main loop for processing commands and automation
    run_state_machine(ctx.state_machine)




