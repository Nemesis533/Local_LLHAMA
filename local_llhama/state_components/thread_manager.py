"""
Thread Manager Component

Manages lifecycle of background worker threads.
"""

import threading
from ..Shared_Logger import LogLevel


class ThreadManager:
    """
    @brief Manages lifecycle of background worker threads.
    """
    def __init__(self):
        self.threads = {}
        self.stop_event = threading.Event()

    def register_thread(self, name, target, args=(), daemon=True):
        """Create and start a new thread."""
        thread = threading.Thread(target=target, args=args, daemon=daemon)
        thread.start()
        self.threads[name] = thread
        return thread

    def stop_all(self, log_prefix=""):
        """Signal all threads to stop and wait for them."""
        self.stop_event.set()
        
        for name, thread in self.threads.items():
            if thread and thread.is_alive():
                thread.join(timeout=3)
                print(f"{log_prefix} [{LogLevel.INFO.name}] {name} thread stopped.")

    def is_stopping(self):
        """Check if stop has been requested."""
        return self.stop_event.is_set()

    def reset(self):
        """Reset the stop event for restart."""
        self.stop_event.clear()
