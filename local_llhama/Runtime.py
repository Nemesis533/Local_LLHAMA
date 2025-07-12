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
from StateMachine import StateMachineInstance
from HA_Interfacer import HomeAssistantClient
import io
import threading
import sys
from SettingsLoader import SettingLoaderClass

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


def main():
    """
    Main entry point of the application.
    Sets up LLM, Home Assistant, State Machine, and LocalLLMChecker with live stdout view.
    """
    # Instance the loader and load data from the settings file
    loader = SettingLoaderClass()
    loader.load()

    # Redirect stdout to buffer
    stdout_buffer = io.StringIO()
    sys.stdout = stdout_buffer
    sys.stderr = stdout_buffer

    print(f"Using {'GPU' if loader.device == 'cuda' else 'CPU'} for model.")

    # Instancing Home Assistant and applying settings, then loading entities
    ha_client = HomeAssistantClient()
    loader.apply([ha_client])
    ha_client.initialize_HA()
    
    #loads the main LLM model and then instances the StateMachine
    command_llm = loader.load_llm_models(ha_client)
    state_machine: StateMachineInstance = StateMachineInstance(command_llm, loader.device, ha_client,stdout_buffer=stdout_buffer)

    #starts the audio processes
    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "65535"])
    check_mic_volume()

    
    loader.apply([state_machine.vitality,state_machine.awaker])# applying settings
    # Start LocalLLMChecker in background
    llm_checker = state_machine.vitality     
    server_thread = threading.Thread(target=llm_checker.run, daemon=True)
    server_thread.start()

    # Start state machine logic
    state_machine.run()


if __name__ == "__main__":
    main()
