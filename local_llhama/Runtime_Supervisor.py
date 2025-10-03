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
import threading
import sys
import logging
import time
from multiprocessing import Process, Queue

# TTS imports for 
from logging.handlers import QueueHandler

# === Custom Imports ===
from .WebService import LocalLLHAMA_WebService
#from .logger import  shared_logger

from . import system_controller as sr
from .StateMachine import State

# === Configuration ===
os.environ['XLA_FLAGS'] = '--xla_gpu_cuda_data_dir=/usr/local/cuda'
warnings.filterwarnings("ignore", category=RuntimeWarning)

# al;lows torch safe configs for coqui


# Allow Coqui TTS to unpickle custom objects
torch.serialization.add_safe_globals([
    defaultdict,
    OrderedDict,
    builtin_dict,
    Path,
    types.SimpleNamespace,
    functools.partial,
])


def monitor_messages(ctx: sr.SystemContext):
    """
    @brief Monitor and process messages from the queue including logs and commands.
    """
    logger = logging.getLogger("Local LLHAMA")

    while True:
        try:
            message = ctx.message_queue.get()  # blocking call

            if isinstance(message, logging.LogRecord):
                logger.handle(message)

            elif isinstance(message, dict):
                msg_type = message.get("type")
                if msg_type == "console_output":
                    logger.info(message.get("data", ""))
                elif msg_type == "ollama_command":
                    command_data = message.get("data")
                    logger.info(f"[Main] Received Ollama command: {command_data}")
                    ctx.state_machine.transcription_queue.put(command_data)
                    ctx.state_machine.transition(State.PARSING_VOICE)
                else:
                    logger.warning(f"[Main] Unknown dict type: {msg_type}")

            elif isinstance(message, str):
                if message == "restart_llm":
                    logger.info("[Main] Restarting the system, please wait.")
                    ctx._should_stop.set()
                else:
                    logger.warning(f"[Main] Unknown string message: {message}")

            else:
                logger.warning(f"[Main] Unexpected message type: {type(message)}")

        except Exception as e:
            logger.error(f"[Main] Queue error: {e}")

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


def main(base_path=""):
    """
    @brief Main entry point for initializing and running the full Local LLHAMA system.
    """
    print("Starting main()...")

    # Create shared context
    ctx = sr.SystemContext()
    
    # Resolve and assign base path
    ctx.base_path = resolve_base_path(base_path)

    # Setup inter-process communication
    ctx.message_queue = Queue()
    #shared_logger.message_queue = ctx.message_queue

    # Load settings and logger
    ctx.loader = sr.setup_settings(ctx.base_path)
    ctx.logger = setup_logging(ctx.message_queue)

    # Start web service
    start_local_web_service_process(ctx.message_queue, ctx.loader)

    # Start monitoring logs and commands from the web UI
    ctx.monitor_thread = threading.Thread(
        target=monitor_messages, args=(ctx,), daemon=True
    )
    ctx.monitor_thread.start()

    log_duration("Settings loaded", ctx.loader.load)
    
    # Start the core system
    sr.start_system(ctx)
    ctx.state_machine.transition(State.LISTENING)
    while True:
        if not ctx._should_stop.is_set():
            sr.run_state_machine(ctx.state_machine)
        else:            
            sr.start_system(ctx)
            ctx.state_machine.transition(State.LISTENING)
            ctx._should_stop.clear()          

if __name__ == "__main__":
    main()
