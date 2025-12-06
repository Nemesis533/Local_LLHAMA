"""
Message Handler Component

Handles inter-process message communication with web server and other components.
"""

import multiprocessing as mp
from queue import Empty
from ..Shared_Logger import LogLevel


class MessageHandler:
    """
    @brief Handles inter-process message communication with web server and other components.
    """
    def __init__(self, action_queue: mp.Queue, web_server_queue: mp.Queue, log_prefix=""):
        self.action_message_queue = action_queue
        self.web_server_message_queue = web_server_queue
        self.log_prefix = log_prefix

    def send_to_web_server(self, message, client_id=None):
        """Send a message to the web server queue."""
        try:
            message_dict = {
                "type": "web_ui_message",
                "data": message,
                "client_id": client_id
            }
            self.web_server_message_queue.put(message_dict, timeout=1)
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to send message to web server: {type(e).__name__}: {e}")

    def check_incoming_messages(self):
        """Check for and return any incoming messages from the action queue."""
        try:
            message = self.action_message_queue.get(timeout=0.01)
            return message
        except Empty:
            return None
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Message Queue Error! {repr(e)}")
            return {"type": "error", "data": str(e)}
