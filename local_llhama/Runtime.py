"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This script sets up the environment, loads settings, initializes the Home Assistant client,
loads LLM models, configures the state machine, starts a web service for control and monitoring,
and begins processing voice commands and automations.
"""

# === System Imports ===
import warnings
import torch
from collections import defaultdict, OrderedDict
from builtins import dict as builtin_dict
from pathlib import Path
import types
import functools
import os
import subprocess
import threading
import sys
import logging
import time
from multiprocessing import Process, Queue
from logging.handlers import QueueHandler

# === Custom Imports ===
from .SettingsLoader import SettingLoaderClass
from .StateMachine import StateMachineInstance
from .HA_Interfacer import HomeAssistantClient
from .WebService import LocalLLHAMA_WebService
from .logger import QueueLogger, shared_logger
from TTS.utils.radam import RAdam

# === Configuration ===
os.environ['XLA_FLAGS'] = '--xla_gpu_cuda_data_dir=/usr/local/cuda'
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Allow Coqui TTS to unpickle custom objects
torch.serialization.add_safe_globals([
    RAdam,
    defaultdict,
    OrderedDict,
    builtin_dict,
    Path,
    types.SimpleNamespace,
    functools.partial,
])

def monitor_messages(queue, loader, ha_client, state_machine):
    """
    @brief Monitor and process messages from the queue including logs and commands.

    @param queue The multiprocessing queue used for inter-process communication.
    @param loader The settings loader instance.
    @param ha_client The Home Assistant client instance.
    @param state_machine The state machine instance used to run automation.
    """
    logger = logging.getLogger("Local LLHAMA")

    while True:
        try:
            message = queue.get()  # blocking call

            if isinstance(message, logging.LogRecord):
                logger.handle(message)

            elif isinstance(message, dict):
                msg_type = message.get("type")
                if msg_type == "console_output":
                    logger.info(message.get("data", ""))
                else:
                    logger.warning(f"[Main] Unknown dict type: {msg_type}")

            elif isinstance(message, str):
                if message == "restart_llm":
                    logger.info("[Main] Restarting LLM models...")
                    llm = load_llm_models(loader, ha_client)
                    new_state_machine = setup_state_machine(loader, llm, ha_client, logger, resolve_base_path(""))
                    state_machine.run = new_state_machine.run
                    logger.info("[Main] Restart complete.")
                else:
                    logger.warning(f"[Main] Unknown string message: {message}")

            else:
                logger.warning(f"[Main] Unexpected message type: {type(message)}")

        except Exception as e:
            logger.error(f"[Main] Queue error: {e}")


def check_mic_volume():
    """
    @brief Display current microphone volume using pactl (PulseAudio).
    """
    result = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "Volume" in line:
            print(line)


def setup_logging(message_queue=None):
    """
    @brief Configure logging with optional message queue handler.

    @param message_queue Optional multiprocessing queue for remote logging.
    @return A configured logger instance.
    """
    logger = logging.getLogger("Local LLHAMA")
    logger.setLevel(logging.DEBUG)

    if not logger.hasHandlers():
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(console_handler)

        if message_queue:
            queue_handler = QueueHandler(message_queue)
            queue_handler.setLevel(logging.DEBUG)
            logger.addHandler(queue_handler)

    return logger


def resolve_base_path(base_path):
    """
    @brief Determine absolute base path for the system.

    @param base_path Custom base path or empty string to use script path.
    @return Resolved absolute path.
    """
    if base_path == "":
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return base_path


def setup_settings(base_path):
    """
    @brief Load application settings from file.

    @param base_path The base directory where settings are located.
    @return An initialized SettingLoaderClass instance.
    """
    loader = SettingLoaderClass(base_path)
    loader.load()
    return loader


def start_local_web_service_process(message_queue, loader):
    """
    @brief Start the local web dashboard in a separate process.

    @param message_queue Queue used to send logs to web interface.
    @param loader Settings loader used to share data with the web service.
    @return The started process instance.
    """
    def run_service():
        webservice = LocalLLHAMA_WebService(message_queue=message_queue)
        webservice.settings_data = loader.data
        webservice.settings_file = loader.settings_file
        webservice.run()

    process = Process(target=run_service, daemon=True)
    process.start()
    return process


def log_duration(message, func):
    """
    @brief Helper to time a function execution and print duration.

    @param message Description of what is being measured.
    @param func Callable function with no arguments.
    """
    start = time.time()
    func()
    print(f"{message} in {time.time() - start:.2f} seconds")


def setup_home_assistant(loader):
    """
    @brief Initialize the Home Assistant client.

    @param loader The settings loader.
    @return An initialized HomeAssistantClient instance.
    """
    start = time.time()
    ha_client = HomeAssistantClient()
    loader.apply([ha_client])
    ha_client.initialize_HA()
    print(f"Home Assistant initialized in {time.time() - start:.2f} seconds")
    return ha_client


def load_llm_models(loader : SettingLoaderClass, ha_client):
    """
    @brief Load LLM models from disk or remote config.

    @param loader The settings loader.
    @param ha_client The Home Assistant client.
    @return Loaded LLM model instance.
    """
    start = time.time()
    llm = loader.load_llm_models(ha_client)
    print(f"LLM models loaded in {time.time() - start:.2f} seconds")
    return llm


def setup_state_machine(loader, llm, ha_client, logger, base_path):
    """
    @brief Setup the core automation state machine.

    @param loader Settings loader instance.
    @param llm The language model used for command processing.
    @param ha_client Home Assistant client.
    @param logger Logger instance.
    @param base_path Application base path.
    @return A configured StateMachineInstance.
    """
    start = time.time()
    sm = StateMachineInstance(llm, loader.device, ha_client, base_path=base_path)
    print(f"State machine initialized in {time.time() - start:.2f} seconds")
    return sm


def setup_audio():
    """
    @brief Configure microphone input volume via PulseAudio.
    """
    start = time.time()
    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
    check_mic_volume()
    print(f"Audio setup done in {time.time() - start:.2f} seconds")


def apply_additional_settings(loader, state_machine):
    """
    @brief Apply runtime configuration to state machine components.

    @param loader The settings loader.
    @param state_machine The state machine instance.
    """
    start = time.time()
    loader.apply([state_machine.awaker])
    print(f"Settings applied to vitality and awaker in {time.time() - start:.2f} seconds")


def run_state_machine(state_machine):
    """
    @brief Start the state machine's execution loop.

    @param state_machine The state machine instance.
    """
    start = time.time()
    state_machine.run()
    print(f"State machine run exited after {time.time() - start:.2f} seconds")


def main(base_path=""):
    """
    @brief Main entry point for initializing and running the full Local LLHAMA system.

    This function handles initialization of all components including:
    settings, logging, Home Assistant, LLM, web dashboard, and the automation engine.
    """
    start_time = time.time()
    print("Starting main()...")

    # Setup inter-process communication
    message_queue = Queue()
    shared_logger.message_queue = message_queue

    # Setup and initialize all core components
    base_path = resolve_base_path(base_path)
    loader = setup_settings(base_path)
    logger = setup_logging(message_queue)
    start_local_web_service_process(message_queue, loader)

    # Start monitoring logs and commands from the web UI
    monitor_thread = threading.Thread(target=monitor_messages, args=(message_queue, loader, None, None), daemon=True)
    monitor_thread.start()

    log_duration("Settings loaded", loader.load)

    print(f"Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    ha_client = setup_home_assistant(loader)
    command_llm = load_llm_models(loader, ha_client)
    state_machine = setup_state_machine(loader, command_llm, ha_client, logger, base_path)

    setup_audio()
    apply_additional_settings(loader, state_machine)

    # Inject references into the monitor thread after initialization
    monitor_thread._args = (message_queue, loader, ha_client, state_machine)

    run_state_machine(state_machine)

    print(f"Total startup time: {time.time() - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
