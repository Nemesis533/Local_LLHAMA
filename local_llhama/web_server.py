import io
import multiprocessing as mp
import os
import secrets
import socket
import threading
from pathlib import Path
from queue import Empty

import psutil
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_login import LoginManager
from flask_socketio import SocketIO

# Import authentication
from .auth import AuthManager
from .postgresql_client import PostgreSQLClient

# Import blueprints from the routes package
from .routes import (
    admin_bp,
    auth_bp,
    calendar_bp,
    llm_bp,
    main_bp,
    preset_bp,
    settings_bp,
    system_bp,
    user_bp,
)
from .routes.calendar_routes import init_calendar_routes
from .routes.chat_history_routes import chat_history_bp, init_chat_history_routes

# Import LogLevel
from .shared_logger import LogLevel
from .state_components.conversation_loader import ConversationLoader


class LocalLLHAMA_WebService:
    def __init__(
        self,
        host="0.0.0.0",
        port=5001,
        action_message_queue=None,
        web_server_message_queue=None,
        chat_message_queue=None,
        preset_response_queue=None,
        pg_client=None,
    ):
        # Load environment variables
        load_dotenv()

        self.web_server_message_queue: mp.Queue = web_server_message_queue
        self.action_message_queue: mp.Queue = action_message_queue
        self.chat_message_queue: mp.Queue = chat_message_queue
        self.preset_response_queue: mp.Queue = preset_response_queue

        # Create fresh PostgreSQL client in this process (cannot share across process boundaries)
        try:
            self.pg_client = PostgreSQLClient()
            print(
                f"[WebServer] [{LogLevel.INFO.name}] PostgreSQL client created for web service process"
            )
        except Exception as e:
            print(
                f"[WebServer] [{LogLevel.WARNING.name}] Failed to create PostgreSQL client: {repr(e)}"
            )
            self.pg_client = None

        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()

        # Class prefix for messages
        self.class_prefix_message = "[WebServer]"

        # Allowed IPs - load from environment variable
        allowed_ips_str = os.getenv("ALLOWED_IP_PREFIXES", "192.168.88.,127.0.0.1")
        self.ALLOWED_IP_PREFIXES = [ip.strip() for ip in allowed_ips_str.split(",")]

        # Paths
        self.base_path = Path(__file__).resolve().parent
        self.static_path = self.base_path / "static"
        self.settings_data = ""
        self.settings_file = ""
        self.loader = None  # Will be set by Runtime_Supervisor

        # Flask app
        self.app = Flask(
            __name__,
            static_url_path="/static",
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
        self.client_sessions = {}  # Map session_id to socket_id for routing
        self.clients_lock = threading.Lock()

        # Initialize conversation loader for chat history
        try:
            self.conversation_loader = ConversationLoader(self.pg_client)
            print(f"[WebServer] [{LogLevel.INFO.name}] Conversation loader initialized")
        except Exception as e:
            print(
                f"[WebServer] [{LogLevel.WARNING.name}] Failed to initialize conversation loader: {repr(e)}"
            )
            self.conversation_loader = None

        # Put service instance + paths into app config
        self.app.config["SERVICE_INSTANCE"] = self
        self.app.config["STATIC_PATH"] = self.static_path
        self.app.config["SYSTEM_CONTROLLER"] = None  # Will be set later
        self.app.config["CONVERSATION_LOADER"] = self.conversation_loader

        # Register blueprints
        self.app.register_blueprint(auth_bp)  # Auth routes first
        self.app.register_blueprint(main_bp)
        self.app.register_blueprint(settings_bp)
        self.app.register_blueprint(preset_bp)
        self.app.register_blueprint(llm_bp)
        self.app.register_blueprint(system_bp)
        self.app.register_blueprint(user_bp)
        self.app.register_blueprint(calendar_bp)
        self.app.register_blueprint(admin_bp)
        self.app.register_blueprint(
            chat_history_bp
        )  # Register chat_history_bp before init

        # Initialize calendar routes with PostgreSQL client
        init_calendar_routes(self.pg_client)

        # Initialize chat history routes with conversation loader
        if self.conversation_loader:
            init_chat_history_routes(self.conversation_loader)

        # Socket.IO handlers
        self.socketio.on_event("connect", self.handle_connect)
        self.socketio.on_event("disconnect", self.handle_disconnect)
        self.socketio.on_event("register_user", self.handle_register_user)

    def _configure_security(self):
        """
        @brief Configure Flask security settings.
        """
        # Generate or load secret key
        secret_key = os.getenv("SECRET_KEY")
        if not secret_key:
            # Generate a new secret key
            secret_key = secrets.token_hex(32)
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No SECRET_KEY in .env, generated temporary key"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Add this to .env for persistent sessions:"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] SECRET_KEY={secret_key}"
            )

        self.app.config["SECRET_KEY"] = secret_key

        # Session configuration
        session_timeout = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
        self.app.config["PERMANENT_SESSION_LIFETIME"] = (
            session_timeout * 3600
        )  # Convert to seconds

        # Security headers
        self.app.config["SESSION_COOKIE_SECURE"] = False  # Set True if using HTTPS
        self.app.config["SESSION_COOKIE_HTTPONLY"] = True
        self.app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Security configured: {session_timeout}h session timeout"
        )

    def _setup_authentication(self):
        """
        @brief Initialize Flask-Login and authentication manager.
        """
        # Initialize LoginManager
        self.login_manager = LoginManager()
        self.login_manager.init_app(self.app)
        self.login_manager.login_view = "auth.login"
        self.login_manager.login_message = "Please log in to access this page."

        # Initialize AuthManager with PostgreSQL client (will create its own if None)
        try:
            self.auth_manager = AuthManager(self.pg_client)
            self.app.config["AUTH_MANAGER"] = self.auth_manager
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Authentication manager initialized"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to initialize auth manager: {repr(e)}"
            )
            raise

        # User loader callback
        @self.login_manager.user_loader
        def load_user(user_id):
            return self.auth_manager.get_user_by_id(int(user_id))

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Authentication system initialized"
        )

    def set_system_controller(self, system_controller):
        """
        @brief Set the system controller reference for routes that need it.
        @param system_controller SystemController instance
        """
        self.app.config["SYSTEM_CONTROLLER"] = system_controller

        # Also set the conversation_loader on the OllamaClient so ChatHandler can access it
        if self.conversation_loader and hasattr(system_controller, "command_llm"):
            try:
                system_controller.command_llm.conversation_loader = (
                    self.conversation_loader
                )
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Conversation loader attached to OllamaClient"
                )
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to attach conversation loader: {repr(e)}"
                )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] System controller registered"
        )

    def _is_ip_allowed(self, ip):
        return any(ip.startswith(prefix) for prefix in self.ALLOWED_IP_PREFIXES)

    def _safe_process(self, proc):
        try:
            proc.info
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def emit_messages(self, message, client_id=None):
        if not message:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Attempted to emit empty message"
            )
            return

        with self.clients_lock:
            # If client_id specified, send only to that client's socket
            if client_id and client_id in self.client_sessions:
                target_sid = self.client_sessions[client_id]
                if target_sid in self.connected_clients:
                    try:
                        self.socketio.emit(
                            "log_line", {"line": message}, room=target_sid
                        )
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit to client {target_sid}: {repr(e)}"
                        )
                        self.connected_clients.discard(target_sid)
                        del self.client_sessions[client_id]
                return

            # Broadcast to all clients (for system messages, STT responses, etc.)
            clients_to_remove = []
            for sid in self.connected_clients:
                try:
                    self.socketio.emit("log_line", {"line": message}, room=sid)
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit to client {sid}: {repr(e)}"
                    )
                    clients_to_remove.append(sid)

            # Remove failed clients
            for sid in clients_to_remove:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Removing disconnected client {sid}"
                )
                self.connected_clients.discard(sid)

    def emit_streaming_chunk(self, chunk_text, client_id=None, is_complete=False):
        """
        @brief Emit a streaming response chunk to the WebUI.
        @param chunk_text The partial text chunk to send
        @param client_id Optional client identifier for routing
        @param is_complete Whether this is the final chunk
        """
        with self.clients_lock:
            # If client_id specified, send only to that client's socket
            if client_id and client_id in self.client_sessions:
                target_sid = self.client_sessions[client_id]
                if target_sid in self.connected_clients:
                    try:
                        self.socketio.emit(
                            "streaming_chunk",
                            {"chunk": chunk_text, "complete": is_complete},
                            room=target_sid,
                        )
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit streaming chunk to client {target_sid}: {repr(e)}"
                        )
                        self.connected_clients.discard(target_sid)
                        del self.client_sessions[client_id]
                return

            # If no client_id, broadcast to all clients
            clients_to_remove = []
            for sid in self.connected_clients:
                try:
                    self.socketio.emit(
                        "streaming_chunk",
                        {"chunk": chunk_text, "complete": is_complete},
                        room=sid,
                    )
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit streaming chunk to client {sid}: {repr(e)}"
                    )
                    clients_to_remove.append(sid)

            # Remove failed clients
            for sid in clients_to_remove:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Removing disconnected client {sid}"
                )
                self.connected_clients.discard(sid)

    def handle_connect(self):
        ip = request.remote_addr
        if not self._is_ip_allowed(ip):
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Denied connection from {ip}"
            )
            return False  # Reject connection

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Client connected: {request.sid}"
        )
        with self.clients_lock:
            self.connected_clients.add(request.sid)

        try:
            self.emit_messages("Local_LLHAMA socket connected!")
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send welcome message: {repr(e)}"
            )

        # Start message monitor on first connection
        if not self.message_monitor_started:
            self.message_monitor_started = True
            self.socketio.start_background_task(self.monitor_messages_lightweight)

    def handle_disconnect(self):
        print(
            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Client disconnected: {request.sid}"
        )
        with self.clients_lock:
            self.connected_clients.discard(request.sid)
            # Clean up client session mapping
            sessions_to_remove = [
                user_id
                for user_id, sid in self.client_sessions.items()
                if sid == request.sid
            ]
            for user_id in sessions_to_remove:
                del self.client_sessions[user_id]

    def handle_register_user(self, data):
        """
        Register authenticated user's socket connection.
        Maps user_id to socket_id for per-user message routing.
        """
        user_id = data.get("user_id")
        if user_id:
            with self.clients_lock:
                self.client_sessions[str(user_id)] = request.sid
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Registered user {user_id} with socket {request.sid}"
                )

    def send_ollama_command(
        self, text: str, from_webui: bool = True, client_id: str = None
    ):
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Received Text from User: {text} (from_webui={from_webui}, client={client_id})"
        )
        if not self.action_message_queue:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Action message queue not initialized"
            )
            raise RuntimeError("Message queue not initialized.")

        message = {
            "type": "ollama_command",
            "data": text,
            "from_webui": from_webui,
            "client_id": client_id,
        }

        try:
            self.action_message_queue.put(message, timeout=2.0)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command queued successfully"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue command: {repr(e)}"
            )
            raise RuntimeError(f"Failed to queue command: {repr(e)}")

    def send_chat_message(
        self, text: str, client_id: str = None, conversation_id: str = None
    ):
        """
        Send chat message to dedicated chat handler (bypasses state machine).

        Returns the conversation_id so frontend can track it for subsequent messages.
        If new conversation is created, this will return the newly created ID.
        """
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Received Chat from User: {text} (client={client_id}, conversation={conversation_id})"
        )
        if not self.chat_message_queue:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Chat message queue not initialized"
            )
            raise RuntimeError("Chat message queue not initialized.")

        message = {
            "text": text,
            "client_id": client_id,
            "conversation_id": conversation_id,
        }

        try:
            self.chat_message_queue.put(message, timeout=2.0)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Chat message queued successfully"
            )
            # Return conversation_id for frontend to store
            # If it was None, backend will create one and update client_conversations
            # Frontend should update its tracking with whatever ID we return here
            return conversation_id
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue chat message: {repr(e)}"
            )
            raise RuntimeError(f"Failed to queue chat message: {repr(e)}")

    def monitor_messages_lightweight(self):
        """
        @brief Lightweight non-blocking message monitor using SocketIO sleep.
        """
        if not self.web_server_message_queue:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Web server message queue not initialized"
            )
            return

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Message monitor started"
        )

        while True:
            try:
                # Non-blocking check
                message = self.web_server_message_queue.get_nowait()

                if isinstance(message, dict):
                    message_type = message.get("type")

                    if message_type == "web_ui_message":
                        message_data = message.get("data")
                        client_id = message.get("client_id")
                        if message_data:
                            try:
                                self.emit_messages(message_data, client_id=client_id)
                            except Exception as e:
                                print(
                                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit: {repr(e)}"
                                )

                    elif message_type == "streaming_chunk":
                        chunk_text = message.get("data")
                        client_id = message.get("client_id")
                        is_complete = message.get("complete", False)
                        if chunk_text is not None:
                            try:
                                self.emit_streaming_chunk(
                                    chunk_text,
                                    client_id=client_id,
                                    is_complete=is_complete,
                                )
                            except Exception as e:
                                print(
                                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to emit streaming chunk: {repr(e)}"
                                )

            except Empty:
                pass  # Queue empty, that's fine
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Monitor error: {repr(e)}"
                )

            # Sleep to avoid busy waiting - this properly yields to SocketIO
            self.socketio.sleep(0.1)

    def get_host_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def get_all_network_ips(self):
        """Get all non-loopback IP addresses on the system."""
        ips = []
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith("127."):
                            ips.append(ip)
        except Exception:
            pass
        return ips

    def run(self):
        display_host = self.host
        if self.host == "0.0.0.0":
            display_host = self.get_host_ip()
        
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting web server on {self.host}:{self.port}"
        )
        
        # Display all network interfaces
        all_ips = self.get_all_network_ips()
        if all_ips:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Access at:")
            for ip in all_ips:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}]   http://{ip}:{self.port}/login")
        else:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Access at: http://{display_host}:{self.port}/login"
            )
        
        self.socketio.run(
            self.app, host="0.0.0.0", port=5001, debug=False, use_reloader=False
        )
