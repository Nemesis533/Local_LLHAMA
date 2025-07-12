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

def setup_logging():
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    # Optional: also log to console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return log_buffer


def resolve_base_path(base_path):
    if base_path == "":
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return base_path

def setup_settings(base_path):
    loader: SettingLoaderClass = SettingLoaderClass(base_path)
    loader.load()
    return loader

def start_local_web_service(logger):
    webservice: LocalLLHAMA_WebService = LocalLLHAMA_WebService(stdout_buffer=logger)
    thread = threading.Thread(target=webservice.run, daemon=True)
    thread.start()

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

def setup_state_machine(loader, llm, ha_client):
    start = time.time()
    sm = StateMachineInstance(llm, loader.device, ha_client)
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
    """
    Main entry point of the application.
    Sets up LLM, Home Assistant, State Machine, and LocalLLMChecker with live stdout view.
    """
    start_time = time.time()
    print("Starting main()...")

    base_path = resolve_base_path(base_path)
    loader = setup_settings(base_path)
    logger = setup_logging()

    start_local_web_service(logger)
    log_duration("Settings loaded", loader.load)

    print(f"Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    ha_client = setup_home_assistant(loader)
    command_llm = load_llm_models(loader, ha_client)
    state_machine = setup_state_machine(loader, command_llm, ha_client)

    setup_audio()

    apply_additional_settings(loader, state_machine)

    run_state_machine(state_machine)

    print(f"Total startup time: {time.time() - start_time:.2f} seconds")

if __name__ == "__main__":
    main()
