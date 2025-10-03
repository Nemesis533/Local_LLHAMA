from flask import Flask, jsonify, request, abort, send_file
from flask_socketio import SocketIO
from flask_cors import CORS
import io
import threading
import logging
import socket
import queue
from pathlib import Path
import psutil
import traceback


# Import blueprints from the routes package
from .routes import main_bp, settings_bp, llm_bp, system_bp, user_bp


class LocalLLHAMA_WebService:
    def __init__(self, host='0.0.0.0', port=5001, message_queue=None):
        self.message_queue: queue = message_queue
        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()

        # Logging setup
        buffer_handler = logging.StreamHandler(self.stdout_buffer)
        buffer_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        buffer_handler.setFormatter(formatter)

        # Allowed IPs
        self.ALLOWED_IP_PREFIXES = ['192.168.88.', '127.0.0.1']

        # Paths
        self.base_path = Path(__file__).resolve().parent
        self.static_path = self.base_path / 'static'
        self.settings_data = ""
        self.settings_file = ""

        # Flask app
        self.app = Flask(
            __name__,
            static_url_path='/static',
            static_folder=str(self.static_path),
        )
        CORS(self.app)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.connected_clients = set()
        self.clients_lock = threading.Lock()

        # Put service instance + paths into app config
        self.app.config["SERVICE_INSTANCE"] = self
        self.app.config["STATIC_PATH"] = self.static_path

        # Register blueprints
        self.app.register_blueprint(main_bp)
        self.app.register_blueprint(settings_bp)
        self.app.register_blueprint(llm_bp)
        self.app.register_blueprint(system_bp)
        self.app.register_blueprint(user_bp)

        # Socket.IO handlers
        self.socketio.on_event('connect', self.handle_connect)
        self.socketio.on_event('disconnect', self.handle_disconnect)

        # Background log listener
        self.socketio.start_background_task(self._log_listener)

        # Suppress werkzeug logs
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)


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

    def handle_connect(self):
        ip = request.remote_addr
        if not self._is_ip_allowed(ip):
            print(f"Denied connection from {ip}")
            return False  # Reject connection

        print('Client connected:', request.sid)
        with self.clients_lock:
            self.connected_clients.add(request.sid)

        # emit welcome message
        self.socketio.emit(
            'log_line',
            {'line': 'Local_LLHAMA socket connected!'},
            room=request.sid
        )

    def handle_disconnect(self):
        print('Client disconnected:', request.sid)
        with self.clients_lock:
            self.connected_clients.discard(request.sid)

    def send_ollama_command(self, text: str):
        """
        @brief Send an Ollama command to the message queue.
        @param text: The command text to send.
        """
        if hasattr(self, "message_queue") and self.message_queue:
            message = {
                "type": "ollama_command",
                "data": text
            }
            self.message_queue.put(message)
        else:
            raise RuntimeError("Message queue not initialized.")

    def _log_listener(self):
        """
        Runs in a Socket.IO-managed background task.
        """
        while True:
            try:
                message = self.message_queue.get(timeout=1)
                log_line = None

                if isinstance(message, dict) and message.get("type") == "console_output":
                    log_line = message["data"]
                elif isinstance(message, logging.LogRecord):
                    log_line = f"{message.levelname} - {message.name} - {message.getMessage()}"
                else:
                    print(f"Received unexpected message type: {type(message)}")

                if log_line:
                    # buffer it somewhere if you want; here we just emit
                    with self.app.app_context():
                        # copy set to avoid mutation while iterating
                        for sid in list(self.connected_clients):
                            self.socketio.emit(
                                'log_line',
                                {'line': log_line},
                                room=sid,
                                namespace='/'   # adjust if using a custom namespace
                            )

                    # yield to the Socket.IO loop so messages are sent
                    self.socketio.sleep(0)

            except queue.Empty:
                # no message this cycle, just yield control
                self.socketio.sleep(0.1)
                continue

            except Exception:
                print("Exception in log_listener:\n", traceback.format_exc())
                # yield back so we don't block the loop
                self.socketio.sleep(0.1)
                continue


    def get_host_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't need to be reachable, just used to get the outgoing IP
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def run(self):
        """
        @brief Starts the Flask web server.

        Launches the service on the configured host and port.
        """
        if self.host == '0.0.0.0':
            self.host = self.get_host_ip()
        self.socketio.run(self.app, host=self.host , port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
