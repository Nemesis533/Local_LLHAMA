"""
Queue Manager Component

Manages all queues used by the state machine for inter-thread communication.
"""

from queue import Empty, Queue

from ..shared_logger import LogLevel


class QueueManager:
    """
    @brief Manages all queues used by the state machine for inter-thread communication.
    """

    def __init__(self):
        self.result_queue = Queue()  # Wake word detection results
        self.transcription_queue = Queue()  # Transcriptions from audio input
        self.command_queue = Queue()  # Parsed commands to execute
        self.sound_action_queue = Queue()  # Sound actions to play asynchronously
        self.speech_queue = Queue()  # Text responses to speak aloud

    def get_queue(self, name):
        """
        @brief Get a specific queue by name.
        @param name Queue name identifier
        @return Queue object or None if not found
        """
        return getattr(self, f"{name}_queue", None)

    def clear_queue(self, queue, log_prefix=""):
        """
        @brief Safely clear all items from a queue.
        @param queue Queue to clear
        @param log_prefix Optional prefix for logging
        """
        try:
            while not queue.empty():
                queue.get_nowait()
        except Empty:
            pass
        except Exception as e:
            print(
                f"{log_prefix} [{LogLevel.WARNING.name}] Error clearing queue: {type(e).__name__}: {e}"
            )

    def put_safe(self, queue, item, timeout=1, log_prefix=""):
        """
        @brief Safely put an item into a queue with error handling.
        @param queue Queue to put item in
        @param item Item to queue
        @param timeout Timeout for the operation
        @param log_prefix Optional prefix for logging
        @return True if successful, False otherwise
        """
        try:
            queue.put(item, timeout=timeout)
            return True
        except Exception as e:
            print(
                f"{log_prefix} [{LogLevel.WARNING.name}] Failed to queue item: {type(e).__name__}: {e}"
            )
            return False

    def get_safe(self, queue, timeout=2, log_prefix=""):
        """
        @brief Safely get an item from a queue with error handling.
        @param queue Queue to get item from
        @param timeout Timeout for the operation
        @param log_prefix Optional prefix for logging
        @return Item from queue or None on timeout/error
        """
        try:
            return queue.get(timeout=timeout)
        except Empty:
            print(
                f"{log_prefix} [{LogLevel.WARNING.name}] Queue timeout after {timeout}s"
            )
            return None
        except Exception as e:
            print(
                f"{log_prefix} [{LogLevel.CRITICAL.name}] Failed to get from queue: {type(e).__name__}: {e}"
            )
            return None
