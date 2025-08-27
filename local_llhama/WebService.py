import time
import psutil
from pathlib import Path
from flask import Flask, jsonify, request, abort, send_file
from flask_socketio import SocketIO
from flask_cors import CORS
import json
import io
import threading
import logging
import socket
import traceback
import queue

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
        self.message_queue : queue = message_queue
        self.host = host
        self.port = port
        self.stdout_buffer = io.StringIO()

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
            static_folder=str(self.static_path),
        )
        CORS(self.app)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.connected_clients = set()
        self.clients_lock = threading.Lock()

        # register handlers
        self.socketio.on_event('connect', self.handle_connect)
        self.socketio.on_event('disconnect', self.handle_disconnect)

        # start background task under Socket.IO
        self.socketio.start_background_task(self._log_listener)

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
        
        @self.app.route('/from_user_text', methods=['POST'])
        def from_user_text():
            """
            Receives user text from the frontend and processes it.
            """
            data = request.get_json()
            if not data or 'text' not in data:
                return jsonify({"error": "No text provided"}), 400

            user_text = data['text']
            

            print("Received user text:", user_text)
            self.send_ollama_command(text=user_text)

            return jsonify({"success": True})

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
        
        @self.app.route("/restart-system", methods=["POST"])
        def restart_system():
            try:
                data = request.get_json()
                if data and data.get("action") == "restart":
                    # Here you would enqueue the restart command in your queue
                    # Example (assuming queue is globally accessible or imported):
                    self.message_queue.put("restart_llm")

                    return jsonify({"success": True})
                else:
                    return jsonify({"success": False, "error": "Invalid action"}), 400
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500
            
        @self.app.route('/llm_status/<host>', methods=['GET'])
        def llm_status(host):
            """
            @brief Returns the online/offline status of a given LLM host.

            The frontend expects a JSON response with `status` = "online" or "offline".
            """
            try:
                # For now, check if 'local_llm' process exists on *this machine*.
                # (You could extend this to check other hosts if needed.)
                process_found = any(
                    'local_llm' in (proc.info['name'] or '') or
                    'local_llm' in ' '.join(proc.info.get('cmdline', []))
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline'])
                    if self._safe_process(proc)
                )

                status = "online" if process_found else "offline"
                return jsonify({"status": status})

            except Exception as e:
                return jsonify({"status": "error", "error": str(e)}), 500

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

