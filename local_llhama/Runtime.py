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

def main(base_path = ""):
    """
    Main entry point of the application.
    Sets up LLM, Home Assistant, State Machine, and LocalLLMChecker with live stdout view.
    """
    start_time = time.time()
    print("Starting main()...")

    if base_path == "":
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))

    # Instance the loader and load data from the settings file\]
    loader :SettingLoaderClass = SettingLoaderClass(base_path)
    loader.load()

    step_start = time.time()
    loader.load()
    print(f"Settings loaded in {time.time() - step_start:.2f} seconds")

    logger = setup_logging()

    print(f"Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    # Home Assistant setup
    step_start = time.time()
    ha_client = HomeAssistantClient()
    loader.apply([ha_client])
    ha_client.initialize_HA()
    print(f"Home Assistant initialized in {time.time() - step_start:.2f} seconds")

    # Load LLM model
    step_start = time.time()
    command_llm = loader.load_llm_models(ha_client)
    print(f"LLM models loaded in {time.time() - step_start:.2f} seconds")

    # State machine setup
    step_start = time.time()
    state_machine = StateMachineInstance(command_llm, loader.device, ha_client, stdout_buffer=logger)
    print(f"State machine initialized in {time.time() - step_start:.2f} seconds")

    # Audio setup
    step_start = time.time()
    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
    check_mic_volume()
    print(f"Audio setup done in {time.time() - step_start:.2f} seconds")

    # Apply settings to vitality and awaker
    step_start = time.time()
    loader.apply([state_machine.vitality, state_machine.awaker])
    print(f"Settings applied to vitality and awaker in {time.time() - step_start:.2f} seconds")

    # Start background checker thread
    step_start = time.time()
    llm_checker = state_machine.vitality
    server_thread = threading.Thread(target=llm_checker.run, daemon=True)
    server_thread.start()
    print(f"Background LLM checker started in {time.time() - step_start:.2f} seconds")

    # Start the state machine logic (likely blocking)
    step_start = time.time()
    state_machine.run()
    print(f"State machine run exited after {time.time() - step_start:.2f} seconds")

    print(f"Total startup time: {time.time() - start_time:.2f} seconds")



if __name__ == "__main__":
    main()
