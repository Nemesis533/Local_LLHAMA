import time
import psutil
from pathlib import Path
from flask import Flask, jsonify, request, abort, Response, send_file
from flask_cors import CORS
import json
import io
import threading
import logging

class LocalLLHAMA_WebService:
    """
    @class LocalLLHAMA_WebService
    @brief A simple Flask-based service to check if a process named 'local_llm' is running
           and view live stdout output.

    This service exposes endpoints for health checks, process monitoring, settings management,
    and live log viewing. It includes IP-based access control and supports logging via message queues.
    """

    def __init__(self, host='0.0.0.0', port=5001, message_queue=None):
        """
        @brief Constructor for LocalLLHAMA_WebService.

        @param host IP address to bind the Flask app to. Default is '0.0.0.0'.
        @param port Port number for the Flask app. Default is 5001.
        @param message_queue Optional queue for receiving log messages asynchronously.
        """
        self.message_queue = message_queue
        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()
        self._start_log_listener()

        # Create a logging handler to store logs in memory
        buffer_handler = logging.StreamHandler(self.stdout_buffer)
        buffer_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        buffer_handler.setFormatter(formatter)

        # IP prefixes allowed to access the web endpoints
        self.ALLOWED_IP_PREFIXES = ['192.168.88.', '127.0.0.1']

        # Define filesystem paths
        self.base_path = Path(__file__).resolve().parent
        self.static_path = self.base_path / 'static'
        self.settings_data = ""
        self.settings_file = ""

        # Initialize Flask app
        self.app = Flask(
            __name__,
            static_url_path='/static',
            static_folder=str(self.static_path)
        )
        CORS(self.app)

        # Suppress Werkzeug request logs
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # Register HTTP routes
        self._register_routes()

    def _register_routes(self):
        """
        @brief Registers all Flask HTTP routes for the web service.
        """

        @self.app.route('/')
        def index():
            """
            @brief Serves the main dashboard HTML page.
            """
            return send_file(self.static_path / 'dashboard.html')

        @self.app.route('/settings', methods=['GET'])
        def get_settings():
            """
            @brief Returns the current settings JSON.
            """
            return self.settings_data

        @self.app.route('/settings', methods=['POST'])
        def save_settings():
            """
            @brief Saves incoming settings JSON to a file.

            @return A JSON response indicating success.
            """
            data = request.get_json()
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=2)
            return jsonify({"status": "ok"})

        @self.app.route('/check-local-llm')
        def check_local_llm():
            """
            @brief Checks if a process named 'local_llm' is currently running.

            @return A JSON response with status: "up" or "down".
            """
            if not self._is_ip_allowed(request.remote_addr):
                abort(403, description="Access denied")

            process_found = any(
                'local_llm' in (proc.info['name'] or '') or
                'local_llm' in ' '.join(proc.info.get('cmdline', []))
                for proc in psutil.process_iter(['pid', 'name', 'cmdline'])
                if self._safe_process(proc)
            )

            status = "up" if process_found else "down"
            return jsonify({'status': status, 'timestamp': time.time()})

        @self.app.route('/stdout')
        def view_stdout():
            """
            @brief Returns current contents of the stdout log buffer.

            @return Text/plain response containing log output.
            """
            if not self._is_ip_allowed(request.remote_addr):
                abort(403, description="Access denied")
            return Response(self.stdout_buffer.getvalue(), mimetype='text/plain')

    def _is_ip_allowed(self, ip):
        """
        @brief Checks if the given IP address is allowed to access the service.

        @param ip The remote IP address as a string.
        @return True if allowed, False otherwise.
        """
        return any(ip.startswith(prefix) for prefix in self.ALLOWED_IP_PREFIXES)

    def _safe_process(self, proc):
        """
        @brief Validates that process info is accessible without raising exceptions.

        @param proc A psutil.Process instance.
        @return True if process info is accessible, False otherwise.
        """
        try:
            proc.info
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def _start_log_listener(self):
        """
        @brief Starts a background thread that listens for log messages from the queue.

        Writes received messages into the in-memory stdout buffer.
        """
        def log_listener():
            while True:
                try:
                    message = self.message_queue.get(timeout=1)
                    if isinstance(message, dict) and message.get("type") == "console_output":
                        self.stdout_buffer.write(message["data"] + "\n")
                        self.stdout_buffer.flush()
                    elif isinstance(message, logging.LogRecord):
                        log_line = f"{message.levelname} - {message.name} - {message.getMessage()}"
                        self.stdout_buffer.write(log_line + "\n")
                        self.stdout_buffer.flush()
                    else:
                        print(f"Received unexpected message type: {type(message)}")
                except Exception:
                    continue

        threading.Thread(target=log_listener, daemon=True).start()

    def run(self):
        """
        @brief Starts the Flask web server.

        Launches the service on the configured host and port.
        """
        self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False, threaded=True)
