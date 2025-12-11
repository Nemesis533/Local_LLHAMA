"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This module defines the LocalLLHamaMain class, which manages environment setup,
web service launching, and system orchestration for Local LLHAMA.
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
import local_llhama
import time
import multiprocessing  as mp
from multiprocessing import Process


# === Custom Imports ===
from .Web_Server import LocalLLHAMA_WebService
from .System_Controller import LocalLLHamaSystemController
from .State_Machine import State
from .Shared_Logger import LogLevel

# === Configuration ===
os.environ["XLA_FLAGS"] = "--xla_gpu_cuda_data_dir=/usr/local/cuda"
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Allow Coqui TTS to unpickle custom objects
torch.serialization.add_safe_globals(
    [
        defaultdict,
        OrderedDict,
        builtin_dict,
        Path,
        types.SimpleNamespace,
        functools.partial,
    ]
)


class LocalLLHamaSupervisor:
    """
    @class LocalLLHamaSupervisor
    @brief Handles environment setup, web service startup, and system orchestration
           for the Local LLHAMA system.
    """

    def __init__(self):

        self.class_prefix_message = "[Supervisor]"
        self.base_path = self.resolve_base_path()               
         
        self.system_controller = LocalLLHamaSystemController(self.base_path)
        
        self.web_server_message_queue  : mp.Queue = mp.Queue()
        self.action_message_queue  : mp.Queue = mp.Queue()
        self.chat_message_queue  : mp.Queue = mp.Queue()

        self.initialize_system()
        

    # === Utility Methods ===

    def resolve_base_path(self) -> str:
        """
        Determine absolute base path for the system.
        """
        resolved =  os.path.dirname(os.path.abspath(local_llhama.__file__))

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Resolved base path: {resolved}")
        return resolved

    def start_local_web_service_process(self, action_message_queue, web_server_message_queue, chat_message_queue, loader, pg_client=None):
        """
        Start the local web dashboard in a separate process.
        """

        def run_service():
            webservice = LocalLLHAMA_WebService(
                action_message_queue=action_message_queue, 
                web_server_message_queue=web_server_message_queue, 
                chat_message_queue=chat_message_queue,
                pg_client=pg_client
            )
            webservice.settings_data = loader.data
            webservice.settings_file = loader.settings_file
            webservice.run()

        process = Process(target=run_service, daemon=True)
        process.start()
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Web service process started with PID {process.pid}")
        return process

    def log_duration(self, message: str, func):
        """
        Helper to time a function execution and print duration.
        """
        start = time.time()
        func()
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] {message} in {time.time() - start:.2f} seconds")

    # === Core Execution ===

    def initialize_system(self):
        """
        Perform initial system setup including:
        - Path resolution
        - Message queue setup
        - Settings loader initialization
        - Web service startup
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing Local LLHAMA Supervisor")

        # Setup message queue for inter-process communication
        self.system_controller.action_message_queue = self.action_message_queue
        self.system_controller.web_server_message_queue = self.web_server_message_queue
        self.system_controller.chat_message_queue = self.chat_message_queue

        # Load settings
        self.system_controller.setup_settings()


        # Measure settings load time
        self.log_duration("Settings loaded", self.system_controller.loader.load)

    def run_main_loop(self):
        """
        Main control loop:
        - Starts system controller
        - Manages the state machine lifecycle
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting system controller")

        # Start the system
        self.system_controller.start_system()
        self.system_controller.state_machine.transition(State.LISTENING)

        # Start local web service process
        self.start_local_web_service_process(
            self.action_message_queue, 
            self.web_server_message_queue, 
            self.chat_message_queue, 
            self.system_controller.loader,
            self.system_controller.pg_client
        )

        # Continuous monitoring loop
        while True:
            if not self.system_controller._should_stop.is_set():
                self.system_controller.state_machine.run()
            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restart signal detected — restarting system")
                self.system_controller.start_system()
                self.system_controller.state_machine.transition(State.LISTENING)
                self.system_controller._should_stop.clear()

    def start(self):
        """
        Entry point for initializing and running the full Local LLHAMA system.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting main()...")      

        self.run_main_loop()
