# logger.py
class QueueLogger:
    def __init__(self, message_queue=None):
        self._buffer = ""
        self._messages = []
        self.message_queue = message_queue

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

            # Skip irrelevant lines
            if (
                line.startswith("127.0.0.1 - - [") or
                "HTTP/1.1" in line or
                line.startswith(("GET ", "POST ", "HEAD ", "OPTIONS ", "PUT ", "DELETE ", "PATCH "))
            ):
                continue

            # Only create log entry if line is not empty
            if line:
                log_entry = {"type": "console_output", "data": line}
                self._messages.append(log_entry)

                if self.message_queue:
                    self.message_queue.put(log_entry)

            # If the original message didn't contain a newline, exit the loop
            if "\n" not in message:
                break
            
    def flush(self):
        if self._buffer.strip():
            log_entry = {"type": "console_output", "data": self._buffer.strip()}
            self._messages.append(log_entry)
            if self.message_queue:
                self.message_queue.put(log_entry)
            self._buffer = ""

    def pop_messages(self):
        msgs = self._messages
        self._messages = []
        return msgs


# Create a single instance
shared_logger = QueueLogger()
