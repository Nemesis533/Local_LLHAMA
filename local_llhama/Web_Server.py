from flask import Flask, request
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_login import LoginManager
import io
import threading
import socket
import multiprocessing as mp
from queue import Queue, Empty
from pathlib import Path
import psutil
import os
import secrets
from dotenv import load_dotenv

# Import blueprints from the routes package
from .routes import main_bp, settings_bp, llm_bp, system_bp, user_bp, auth_bp, calendar_bp

# Import authentication
from .auth import AuthManager

# Import LogLevel
from .Shared_Logger import LogLevel


class LocalLLHAMA_WebService:
    def __init__(self, host='0.0.0.0', port=5001, action_message_queue=None,web_server_message_queue=None):
        # Load environment variables
        load_dotenv()
        
        self.web_server_message_queue  : mp.Queue  = web_server_message_queue
        self.action_message_queue : mp.Queue  = action_message_queue
        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()

        # Class prefix for messages
        self.class_prefix_message = "[WebServer]"

        # Allowed IPs - load from environment variable
        allowed_ips_str = os.getenv('ALLOWED_IP_PREFIXES', '192.168.88.,127.0.0.1')
        self.ALLOWED_IP_PREFIXES = [ip.strip() for ip in allowed_ips_str.split(',')]

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
        
        # Security configuration
        self._configure_security()
        
        # Initialize authentication
        self._setup_authentication()
        
        CORS(self.app)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        # Start lightweight message monitor after SocketIO is ready
        self.message_monitor_started = False
        self.connected_clients = set()
        self.clients_lock = threading.Lock()

        # Put service instance + paths into app config
        self.app.config["SERVICE_INSTANCE"] = self
        self.app.config["STATIC_PATH"] = self.static_path
        self.app.config["SYSTEM_CONTROLLER"] = None  # Will be set later

        # Register blueprints
        self.app.register_blueprint(auth_bp)  # Auth routes first
        self.app.register_blueprint(main_bp)
        self.app.register_blueprint(settings_bp)
        self.app.register_blueprint(llm_bp)
        self.app.register_blueprint(system_bp)
        self.app.register_blueprint(user_bp)
        self.app.register_blueprint(calendar_bp)

        # Socket.IO handlers
        self.socketio.on_event('connect', self.handle_connect)
        self.socketio.on_event('disconnect', self.handle_disconnect)
    
    def _configure_security(self):
        """Configure Flask security settings."""
        # Generate or load secret key
        secret_key = os.getenv('SECRET_KEY')
        if not secret_key:
            # Generate a new secret key
            secret_key = secrets.token_hex(32)
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No SECRET_KEY in .env, generated temporary key")
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Add this to .env for persistent sessions:")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] SECRET_KEY={secret_key}")
        
        self.app.config['SECRET_KEY'] = secret_key
        
        # Session configuration
        session_timeout = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))
        self.app.config['PERMANENT_SESSION_LIFETIME'] = session_timeout * 3600  # Convert to seconds
        
        # Security headers
        self.app.config['SESSION_COOKIE_SECURE'] = False  # Set True if using HTTPS
        self.app.config['SESSION_COOKIE_HTTPONLY'] = True
        self.app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Security configured: {session_timeout}h session timeout")
    
    def _setup_authentication(self):
        """Initialize Flask-Login and authentication manager."""
        # Initialize LoginManager
        self.login_manager = LoginManager()
        self.login_manager.init_app(self.app)
        self.login_manager.login_view = 'auth.login'
        self.login_manager.login_message = 'Please log in to access this page.'
        
        # Initialize AuthManager
        self.auth_manager = AuthManager()
        self.app.config['AUTH_MANAGER'] = self.auth_manager
        
        # User loader callback
        @self.login_manager.user_loader
        def load_user(user_id):
            return self.auth_manager.get_user_by_id(int(user_id))
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Authentication system initialized")

    def set_system_controller(self, system_controller):
        """Set the system controller reference for routes that need it."""
        self.app.config['SYSTEM_CONTROLLER'] = system_controller
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] System controller registered")


    def _is_ip_allowed(self, ip):
        return any(ip.startswith(prefix) for prefix in self.ALLOWED_IP_PREFIXES)

    def _safe_process(self, proc):
        try:
            proc.info
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        
    def emit_messages(self, message):
        if not message:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Attempted to emit empty message")
            return
        
        with self.clients_lock:
            clients_to_remove = []
            for sid in self.connected_clients:
                try:
                    self.socketio.emit('log_line', {'line': message}, room=sid)
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit to client {sid}: {repr(e)}")
                    clients_to_remove.append(sid)
            
            # Remove failed clients
            for sid in clients_to_remove:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Removing disconnected client {sid}")
                self.connected_clients.discard(sid)

    def handle_connect(self):
        ip = request.remote_addr
        if not self._is_ip_allowed(ip):
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Denied connection from {ip}")
            return False  # Reject connection

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Client connected: {request.sid}")
        with self.clients_lock:
            self.connected_clients.add(request.sid)

        try:
            self.emit_messages("Local_LLHAMA socket connected!")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send welcome message: {repr(e)}")
        
        # Start message monitor on first connection
        if not self.message_monitor_started:
            self.message_monitor_started = True
            self.socketio.start_background_task(self.monitor_messages_lightweight)



    def handle_disconnect(self):
        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Client disconnected: {request.sid}")
        with self.clients_lock:
            self.connected_clients.discard(request.sid)

    def send_ollama_command(self, text: str, from_webui: bool = True):
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Received Text from User: {text} (from_webui={from_webui})")
        if not self.action_message_queue:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Action message queue not initialized")
            raise RuntimeError("Message queue not initialized.")
        
        message = {
            "type": "ollama_command",
            "data": text,
            "from_webui": from_webui
        }
        
        try:
            self.action_message_queue.put(message, timeout=2.0)
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command queued successfully")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue command: {repr(e)}")
            raise RuntimeError(f"Failed to queue command: {repr(e)}")

    def monitor_messages_lightweight(self):
        """Lightweight non-blocking message monitor using SocketIO sleep."""
        if not self.web_server_message_queue:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Web server message queue not initialized")
            return
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Message monitor started")
        
        while True:
            try:
                # Non-blocking check
                message = self.web_server_message_queue.get_nowait()
                
                if isinstance(message, dict) and message.get("type") == "web_ui_message":
                    message_data = message.get("data")
                    if message_data:
                        try:
                            self.emit_messages(message_data)
                        except Exception as e:
                            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit: {repr(e)}")
                            
            except Empty:
                pass  # Queue empty, that's fine
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Monitor error: {repr(e)}")
            
            # Sleep to avoid busy waiting - this properly yields to SocketIO
            self.socketio.sleep(0.1)

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
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting web server on {self.host}:{self.port}")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Access at: http://{self.host}:{self.port}/login")
        self.socketio.run(self.app, host=self.host, port=5001, debug=False, use_reloader=False)

