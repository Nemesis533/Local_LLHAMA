from flask import Flask, request
from flask_socketio import SocketIO
from flask_cors import CORS
import io
import threading
import socket
import multiprocessing as mp
from queue import Queue, Empty
from pathlib import Path
import psutil

# Import blueprints from the routes package
from .routes import main_bp, settings_bp, llm_bp, system_bp, user_bp

# Import LogLevel
from .Shared_Logger import LogLevel


class LocalLLHAMA_WebService:
    def __init__(self, host='0.0.0.0', port=5001, action_message_queue=None,web_server_message_queue=None):
        self.web_server_message_queue  : mp.Queue  = web_server_message_queue
        self.action_message_queue : mp.Queue  = action_message_queue
        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()

        # Class prefix for messages
        self.class_prefix_message = "[WebServer]"

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
        self.socketio.start_background_task(self.monitor_messages)
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


    def _is_ip_allowed(self, ip):
        return any(ip.startswith(prefix) for prefix in self.ALLOWED_IP_PREFIXES)

    def _safe_process(self, proc):
        try:
            proc.info
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        
    def emit_messages(self, message):
        with self.clients_lock:
            for sid in self.connected_clients:
                self.socketio.emit('log_line', {'line': message}, room=sid)

    def handle_connect(self):
        ip = request.remote_addr
        if not self._is_ip_allowed(ip):
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Denied connection from {ip}")
            return False  # Reject connection

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Client connected: {request.sid}")
        with self.clients_lock:
            self.connected_clients.add(request.sid)

        self.emit_messages("Local_LLHAMA socket connected!")



    def handle_disconnect(self):
        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Client disconnected: {request.sid}")
        with self.clients_lock:
            self.connected_clients.discard(request.sid)

    def send_ollama_command(self, text: str):
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Received Text from User: {text}")
        if self.action_message_queue:
            message = {
                "type": "ollama_command",
                "data": text
            }
            self.action_message_queue.put(message)
        else:
            raise RuntimeError("Message queue not initialized.")
        
    def monitor_messages(self):
        while True:
            try:
                message = self.web_server_message_queue.get(timeout=0.1)  # adjust timeout as needed
                if isinstance(message, dict):
                    msg_type = message.get("type")
                    if msg_type == "web_ui_message":
                        message_data = message.get("data")
                        self.emit_messages(message_data)

                elif isinstance(message, str):
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unknown message {message}")
                else:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Unexpected message type {type(message)}")
            except Empty:
                continue  # queue is empty, keep looping
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Message Queue Error! {repr(e)}")




    def get_host_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def run(self):
        if self.host == '0.0.0.0':
            self.host = self.get_host_ip()
        self.socketio.run(self.app, host=self.host, port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

