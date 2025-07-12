# system imports
import warnings
import torch
from collections import defaultdict, OrderedDict
from builtins import dict as builtin_dict
from pathlib import Path
import types
import functools
from TTS.utils.radam import RAdam
import os
import subprocess
import io
import threading
import sys
import logging
import time
from multiprocessing import Process, Queue
from logging.handlers import QueueHandler

# custom imports
from .SettingsLoader import SettingLoaderClass
from .StateMachine import StateMachineInstance
from .HA_Interfacer import HomeAssistantClient
from .WebService import LocalLLHAMA_WebService

# set environment variable for CUDA
os.environ['XLA_FLAGS'] = '--xla_gpu_cuda_data_dir=/usr/local/cuda'
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Allow Coqui TTS to unpickle necessary objects safely
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
    Monitor the queue and handle commands sent from the webservice process.
    Also process logging LogRecords pushed by QueueHandler.
    """
    logger = logging.getLogger("my_app")  # Use the main logger

    while True:
        try:
            message = queue.get()  # blocking call

            # If the message is a logging.LogRecord, emit it through the logger
            if isinstance(message, logging.LogRecord):
                logger.handle(message)  # This will print to console and any other handlers

            # Handle control messages (strings)
            elif isinstance(message, str):
                if message == "restart_llm":
                    logger.info("[Main] Restart command received: restarting LLM models...")
                    llm = load_llm_models(loader, ha_client)
                    new_state_machine = setup_state_machine(loader, llm, ha_client)
                    state_machine.run = new_state_machine.run
                    logger.info("[Main] LLM and State Machine restarted successfully.")
                else:
                    logger.warning(f"[Main] Unknown message received: {message}")

            else:
                logger.warning(f"[Main] Received unexpected message type: {type(message)}")

        except Exception as e:
            logger.error(f"[Main] Error processing queue message: {e}")

def check_mic_volume():
    """
    @brief Prints the current microphone volume levels using pactl.
    Useful for debugging input gain settings in PulseAudio.
    """
    result = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True)
    output = result.stdout
    for line in output.splitlines():
        if "Volume" in line:
            print(line)

def setup_logging(message_queue=None):
    logger = logging.getLogger("my_app")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
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
    if base_path == "":
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return base_path

def setup_settings(base_path):
    loader: SettingLoaderClass = SettingLoaderClass(base_path)
    loader.load()
    return loader


def start_local_web_service_process(logger, message_queue,loader:SettingLoaderClass):
    def run_service():
        webservice = LocalLLHAMA_WebService(stdout_buffer=logger, message_queue=message_queue)
        webservice.settings_data = loader.data
        webservice.settings_file = loader.settings_file
        webservice.run()

    process = Process(target=run_service, daemon=True)
    process.start()
    return process

def log_duration(message, func):
    start = time.time()
    func()
    print(f"{message} in {time.time() - start:.2f} seconds")

def setup_home_assistant(loader):
    start = time.time()
    ha_client = HomeAssistantClient()
    loader.apply([ha_client])
    ha_client.initialize_HA()
    print(f"Home Assistant initialized in {time.time() - start:.2f} seconds")
    return ha_client

def load_llm_models(loader:SettingLoaderClass, ha_client):
    start = time.time()
    llm = loader.load_llm_models(ha_client)
    print(f"LLM models loaded in {time.time() - start:.2f} seconds")
    return llm

def setup_state_machine(loader, llm, ha_client, logger):
    start = time.time()
    sm = StateMachineInstance(llm, loader.device, ha_client,logger )
    print(f"State machine initialized in {time.time() - start:.2f} seconds")
    return sm

def setup_audio():
    start = time.time()
    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
    check_mic_volume()
    print(f"Audio setup done in {time.time() - start:.2f} seconds")

def apply_additional_settings(loader:SettingLoaderClass, state_machine:StateMachineInstance):
    start = time.time()
    loader.apply([state_machine.awaker])
    print(f"Settings applied to vitality and awaker in {time.time() - start:.2f} seconds")


def run_state_machine(state_machine):
    start = time.time()
    state_machine.run()
    print(f"State machine run exited after {time.time() - start:.2f} seconds")

def main(base_path=""):

    start_time = time.time()
    print("Starting main()...")
    message_queue = Queue()

    base_path = resolve_base_path(base_path)
    loader = setup_settings(base_path)
    logger = setup_logging(message_queue)
    
    webservice_process = start_local_web_service_process(logger, message_queue,loader)

    # Start monitoring messages in a separate thread so main thread is not blocked
    monitor_thread = threading.Thread(target=monitor_messages, args=(message_queue, loader, None, None), daemon=True)
    monitor_thread.start()

    log_duration("Settings loaded", loader.load)

    print(f"Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    ha_client = setup_home_assistant(loader)
    command_llm = load_llm_models(loader, ha_client)
    state_machine = setup_state_machine(loader, command_llm, ha_client,logger)

    setup_audio()

    apply_additional_settings(loader, state_machine)

    # Update monitor thread args with actual state_machine and ha_client
    # (Because state_machine was not created when monitor started)
    monitor_thread._args = (message_queue, loader, ha_client, state_machine)

    run_state_machine(state_machine)

    print(f"Total startup time: {time.time() - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
