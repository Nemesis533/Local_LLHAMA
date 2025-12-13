"""
State Transition Manager Component

Manages state transitions with validation and logging.
"""

import threading

from ..shared_logger import LogLevel


class StateTransitionManager:
    """
    @brief Manages state transitions with validation and logging.
    """

    def __init__(self, initial_state, log_prefix=""):
        self.state = initial_state
        self.lock = threading.RLock()
        self.log_prefix = log_prefix
        self._last_printed_message = None
        self._print_lock = threading.Lock()

    def transition(self, new_state):
        """
        @brief Thread-safe state transition with logging.
        @param new_state New state to transition to
        """
        if self.lock.acquire(timeout=2):
            try:
                old_state = self.state
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Transitioning from {old_state.name} to {new_state.name}"
                )
                self.state = new_state
            finally:
                self.lock.release()
        else:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Lock timeout: failed to transition to {new_state.name} (lock held for >2s)"
            )

    def get_state(self):
        """
        @brief Thread-safe getter for current state.
        @return Current state
        """
        with self.lock:
            return self.state

    def print_once(self, message, end="\n"):
        """
        @brief Print a message only if it differs from the last printed message.
        @param message Message to print
        @param end Line ending character
        """
        with self._print_lock:
            if message != self._last_printed_message:
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] {message}", end=end)
                self._last_printed_message = message
