"""
@class QueueLogger
@brief Logger that captures and processes console output into structured messages.

This class intercepts stdout/stderr output and converts relevant log lines into
structured dictionary entries. It supports optional queueing to enable asynchronous
log handling, such as transferring logs to a UI or another thread.
"""

class QueueLogger:
    def __init__(self, message_queue=None):
        """
        @brief Initializes the QueueLogger instance.

        @param message_queue Optional queue to which processed log entries will be pushed.
        """
        self._buffer = ""
        self._messages = []
        self.message_queue = message_queue

    def write(self, message):
        """
        @brief Processes incoming text message from stdout/stderr.

        Captures the message, filters out irrelevant lines (such as HTTP requests),
        and converts the relevant lines into structured log entries.

        @param message The string to be logged.
        """
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

            # Skip irrelevant HTTP log lines
            if (
                line.startswith("127.0.0.1 - - [") or
                "HTTP/1.1" in line or
                line.startswith(("GET ", "POST ", "HEAD ", "OPTIONS ", "PUT ", "DELETE ", "PATCH "))
            ):
                continue

            # Create and store the structured log entry
            if line:
                log_entry = {"type": "console_output", "data": line}
                self._messages.append(log_entry)

                if self.message_queue:
                    self.message_queue.put(log_entry)

            # If no newline in original message, stop processing further
            if "\n" not in message:
                break

    def flush(self):
        """
        @brief Flushes the buffer and pushes any remaining data as a log entry.

        Ensures that partially collected logs are processed and queued.
        """
        if self._buffer.strip():
            log_entry = {"type": "console_output", "data": self._buffer.strip()}
            self._messages.append(log_entry)
            if self.message_queue:
                self.message_queue.put(log_entry)
            self._buffer = ""

    def pop_messages(self):
        """
        @brief Retrieves and clears the internal log message list.

        @return List of log entries captured since the last pop.
        """
        msgs = self._messages
        self._messages = []
        return msgs


# Create a globally shared instance of the logger
shared_logger = QueueLogger()
