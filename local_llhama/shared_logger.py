import os
import re
import sys
from datetime import datetime
from enum import IntEnum
from multiprocessing import Process, Queue

from colorama import Fore, Style, init

# Initialize colorama for cross-platform color support
init(autoreset=True)


# Define log levels
class LogLevel(IntEnum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3


LEVEL_MAP = {
    "INFO": LogLevel.INFO,
    "WARNING": LogLevel.WARNING,
    "CRITICAL": LogLevel.CRITICAL,
}

# Global dev mode flag
DEV_MODE = os.environ.get("LLHAMA_DEV_MODE") == "1"


class AsyncQueueLogger:
    COLOR_MAP = {
        LogLevel.INFO: Fore.GREEN,
        LogLevel.WARNING: Fore.YELLOW,
        LogLevel.CRITICAL: Fore.RED,
    }

    def __init__(self, log_file_path="app.log", level=LogLevel.INFO):
        self._buffer = ""
        self._messages = []
        self.log_file_path = log_file_path
        self.level = level

        # Control whether messages should be printed
        # In dev mode, print based on level; in production, never print
        self._console_enabled = DEV_MODE

        # Save original stdout/stderr
        self._original_stdout = sys.__stdout__
        self._original_stderr = sys.__stderr__

        # Async logging queue
        self._log_queue = Queue()
        self._process = Process(
            target=self._log_worker, args=(self._log_queue, log_file_path)
        )
        self._process.daemon = True
        self._process.start()

        # Ensure log file exists
        if not os.path.exists(log_file_path):
            with open(log_file_path, "w") as f:
                pass

    # --- Console interception ---
    def write(self, message):
        self._buffer += message
        while True:
            if "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
            else:
                line = self._buffer
                self._buffer = ""

            line = line.strip()
            if not line:
                break

            # Skip HTTP request lines if needed
            if (
                line.startswith("127.0.0.1 - - [")
                or "HTTP/1.1" in line
                or line.startswith(
                    ("GET ", "POST ", "HEAD ", "OPTIONS ", "PUT ", "DELETE ", "PATCH ")
                )
            ):
                continue

            # Detect log level from message
            match = re.search(r"\[(INFO|WARNING|CRITICAL)\]", line, re.IGNORECASE)
            if match:
                level_str = match.group(1).upper()
                level = LEVEL_MAP.get(level_str, LogLevel.INFO)
            else:
                level = LogLevel.INFO

            # Filter by minimum log level
            if level < self.level:
                continue

            self._messages.append({"type": "console_output", "data": line})

            # Console output only in dev mode
            if self._console_enabled:
                self._write_to_console(line, level)

            # Always log to file asynchronously
            self.log(line, level)

            if "\n" not in message:
                break

    def flush(self):
        if self._buffer.strip():
            line = self._buffer.strip()

            # Detect log level from message
            match = re.search(r"\[(INFO|WARNING|CRITICAL)\]", line, re.IGNORECASE)
            if match:
                level_str = match.group(1).upper()
                level = LEVEL_MAP.get(level_str, LogLevel.INFO)
            else:
                level = LogLevel.INFO

            # Filter by minimum log level
            if level < self.level:
                self._buffer = ""
                return

            self._messages.append({"type": "console_output", "data": line})
            self.log(line, level)

            # Flush to console in dev mode
            if self._console_enabled:
                self._write_to_console(line, level)

            self._buffer = ""

    def pop_messages(self):
        msgs = self._messages
        self._messages = []
        return msgs

    # --- Async file logging ---
    def log(self, message, level=LogLevel.INFO):
        """
        @brief Log a message if it meets the minimum log level threshold.
        @param message The message to log
        @param level The log level (INFO, WARNING, or CRITICAL)
        """
        if level >= self.level:
            self._log_queue.put((level.name, message))

    def set_level(self, level):
        """
        @brief Set the minimum log level threshold.
        @param level LogLevel enum value (e.g., LogLevel.WARNING to show only WARNING and CRITICAL)
        """
        if isinstance(level, LogLevel):
            self.level = level
        else:
            raise ValueError("level must be an instance of LogLevel")

    # --- Internal helpers ---
    def _write_to_console(self, message, level):
        # Default color based on log level
        color = self.COLOR_MAP.get(level, "")

        # Override if message contains [Supervisor]
        if "[Supervisor]" in message and not "[CRITICAL]" in message:
            color = Fore.MAGENTA  # purple

        if "[User Prompt]" in message and not "[CRITICAL]" in message:
            color = Fore.CYAN  # cyan

        if "[LLM Reply]" in message and not "[CRITICAL]" in message:
            color = Fore.BLUE  # blue

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._original_stdout.write(
                f"{color}[{timestamp}] {message}{Style.RESET_ALL}\n"
            )
            self._original_stdout.flush()
        except Exception:
            pass

    def _log_worker(self, queue, file_path):
        with open(file_path, "a") as f:
            while True:
                try:
                    level_name, message = queue.get()
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] [{level_name}] {message}\n")
                    f.flush()
                except Exception as e:
                    f.write(
                        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to log message: {e}\n"
                    )
                    f.flush()


# --- Shared logger instance ---
shared_logger = AsyncQueueLogger()
