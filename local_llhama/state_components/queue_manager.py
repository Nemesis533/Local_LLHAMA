"""
Queue Manager Component

Manages all queues used by the state machine for inter-thread communication.
"""

from queue import Queue, Empty
from ..Shared_Logger import LogLevel


class QueueManager:
    """
    @brief Manages all queues used by the state machine for inter-thread communication.
    """
    def __init__(self):
        self.result_queue = Queue()         # Wake word detection results
        self.transcription_queue = Queue()  # Transcriptions from audio input
        self.command_queue = Queue()        # Parsed commands to execute
        self.sound_action_queue = Queue()   # Sound actions to play asynchronously
        self.speech_queue = Queue()         # Text responses to speak aloud

    def get_queue(self, name):
        """Get a specific queue by name."""
        return getattr(self, f"{name}_queue", None)

    def clear_queue(self, queue, log_prefix=""):
        """Safely clear all items from a queue."""
        try:
            while not queue.empty():
                queue.get_nowait()
        except Empty:
            pass
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Error clearing queue: {type(e).__name__}: {e}")

    def put_safe(self, queue, item, timeout=1, log_prefix=""):
        """Safely put an item into a queue with error handling."""
        try:
            queue.put(item, timeout=timeout)
            return True
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Failed to queue item: {type(e).__name__}: {e}")
            return False

    def get_safe(self, queue, timeout=2, log_prefix=""):
        """Safely get an item from a queue with error handling."""
        try:
            return queue.get(timeout=timeout)
        except Empty:
            print(f"{log_prefix} [{LogLevel.WARNING.name}] Queue timeout after {timeout}s")
            return None
        except Exception as e:
            print(f"{log_prefix} [{LogLevel.CRITICAL.name}] Failed to get from queue: {type(e).__name__}: {e}")
            return None
