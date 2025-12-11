"""
@file main.py
@brief Entry point for the Local LLHAMA system.

This module defines the LocalLLHamaMain class, which manages environment setup,
web service launching, and system orchestration for Local LLHAMA.
"""

import multiprocessing as mp
import os
import time

# === System Imports ===
import warnings
from multiprocessing import Process

import local_llhama

from .Shared_Logger import LogLevel
from .state_machine import State
from .System_Controller import LocalLLHamaSystemController

# === Custom Imports ===
from .Web_Server import LocalLLHAMA_WebService

# === Configuration ===
warnings.filterwarnings("ignore", category=RuntimeWarning)


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

        self.web_server_message_queue: mp.Queue = mp.Queue()
        self.action_message_queue: mp.Queue = mp.Queue()
        self.chat_message_queue: mp.Queue = mp.Queue()
        self.preset_response_queue: mp.Queue = mp.Queue()  # For preset API responses

        self.initialize_system()

    # === Utility Methods ===

    def resolve_base_path(self) -> str:
        """
        Determine absolute base path for the system.
        """
        resolved = os.path.dirname(os.path.abspath(local_llhama.__file__))

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Resolved base path: {resolved}"
        )
        return resolved

    def start_web_service(
        self,
        action_message_queue,
        web_server_message_queue,
        chat_message_queue,
        preset_response_queue,
        loader,
        pg_client=None,
    ):
        """
        Start the local web dashboard in a separate process.
        """

        def run_service():
            webservice = LocalLLHAMA_WebService(
                action_message_queue=action_message_queue,
                web_server_message_queue=web_server_message_queue,
                chat_message_queue=chat_message_queue,
                preset_response_queue=preset_response_queue,
                pg_client=pg_client,
            )
            webservice.settings_data = loader.data
            webservice.settings_file = loader.settings_file
            webservice.loader = loader  # Store loader reference
            webservice.run()

        process = Process(target=run_service, daemon=True)
        process.start()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Web service process started with PID {process.pid}"
        )
        return process

    def log_duration(self, message: str, func):
        """
        Helper to time a function execution and print duration.
        """
        start = time.time()
        func()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] {message} in {time.time() - start:.2f} seconds"
        )

    # === Core Execution ===

    def initialize_system(self):
        """
        Perform initial system setup including:
        - Path resolution
        - Message queue setup
        - Settings loader initialization
        - Web service startup
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initializing Local LLHAMA Supervisor"
        )

        # Setup message queue for inter-process communication
        self.system_controller.action_message_queue = self.action_message_queue
        self.system_controller.web_server_message_queue = self.web_server_message_queue
        self.system_controller.chat_message_queue = self.chat_message_queue
        self.system_controller.preset_response_queue = self.preset_response_queue

        # Load settings
        start = time.time()
        self.system_controller.setup_settings()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Settings loaded in {time.time() - start:.2f} seconds"
        )

    def run_main_loop(self):
        """
        Main control loop:
        - Starts system controller
        - Manages the state machine lifecycle
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting system controller"
        )

        # Start the system
        self.system_controller.start_system()
        self.system_controller.state_machine.transition(State.LISTENING)

        # Start local web service process
        self.start_web_service(
            self.action_message_queue,
            self.web_server_message_queue,
            self.chat_message_queue,
            self.preset_response_queue,
            self.system_controller.loader,
            self.system_controller.pg_client,
        )

        # Continuous monitoring loop
        while True:
            try:
                if not self.system_controller._should_stop.is_set():
                    self.system_controller.state_machine.run()
                else:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Restart signal detected — restarting system"
                    )

                    # Properly stop the old state machine
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Stopping current state machine..."
                    )
                    try:
                        self.system_controller.state_machine.stop()
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error stopping state machine: {e}"
                        )

                    # Small delay to ensure cleanup
                    time.sleep(1)

                    # Restart the system
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting fresh system instance..."
                    )
                    success = self.system_controller.start_system()

                    if success is False:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] System restart failed!"
                        )
                        # Try to recover by clearing the flag and continuing with old state
                        self.system_controller._should_stop.clear()
                        continue

                    # Transition to listening state
                    self.system_controller.state_machine.transition(State.LISTENING)
                    self.system_controller._should_stop.clear()

                    # Send success message to web UI
                    try:
                        message = {
                            "type": "system_message",
                            "data": "✅ System restart completed successfully. All components reloaded.",
                        }
                        self.web_server_message_queue.put(message, timeout=1.0)
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not send restart success message: {e}"
                        )

                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] System restart completed successfully"
                    )
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error in main loop: {type(e).__name__}: {e}"
                )
                import traceback

                traceback.print_exc()
                # Don't crash the whole system, try to continue
                time.sleep(1)

    def start(self):
        """
        Entry point for initializing and running the full Local LLHAMA system.
        """
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting main()...")

        self.run_main_loop()
