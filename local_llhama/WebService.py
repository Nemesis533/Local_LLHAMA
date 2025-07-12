import time
import psutil
from pathlib import Path
from flask import Flask, jsonify, request, abort, send_from_directory, Response, send_file
from flask_cors import CORS


class LocalLLHAMA_WebService:
    """
    @class LocalLLHAMA_WebService
    @brief A simple Flask-based service to check if a process named 'local_llm' is running
           and view live stdout output.
    """

    def __init__(self, host='0.0.0.0', port=5001, stdout_buffer=None):
        """
        @brief Constructor for LocalLLHAMA_WebService.

        @param host: IP address to bind the Flask app to. Default is '0.0.0.0'.
        @param port: Port number for the Flask app. Default is 5001.
        @param stdout_buffer: Optional buffer for capturing stdout.
        """
        self.host = host
        self.port = port
        self.stdout_buffer = stdout_buffer
        self.ALLOWED_IP_PREFIXES = ['192.168.88.', '127.0.0.1']

        # Define base and static paths only once
        self.base_path = Path(__file__).resolve().parent
        self.static_path = self.base_path / 'static'

        self.app = Flask(
            __name__,
            static_url_path='/static',
            static_folder=str(self.static_path)
        )
        CORS(self.app)
        self._register_routes()

    def _register_routes(self):
        @self.app.route('/')
        def index():
            return send_file(self.static_path / 'dashboard.html')

        @self.app.route('/check-local-llm')
        def check_local_llm():
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
            if not self._is_ip_allowed(request.remote_addr):
                abort(403, description="Access denied")

            content = self.stdout_buffer.getvalue() if self.stdout_buffer else "Stdout capturing not enabled."
            return Response(content, mimetype='text/plain')

    def _is_ip_allowed(self, ip):
        return any(ip.startswith(prefix) for prefix in self.ALLOWED_IP_PREFIXES)

    def _safe_process(self, proc):
        try:
            proc.info  # just to ensure info is accessible
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def run(self):
        """
        @brief Starts the Flask web server.
        """
        self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False, threaded=True)
