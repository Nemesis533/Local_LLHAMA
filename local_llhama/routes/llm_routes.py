# llm_routes.py
import time
import psutil
from flask import Blueprint, jsonify, request, abort, current_app
from flask_login import login_required

llm_bp = Blueprint("llm", __name__)

@llm_bp.route('/check-local-llm')
@login_required
def check_local_llm():
    """
    Checks if a process named 'local_llm' is currently running.
    """
    service = current_app.config["SERVICE_INSTANCE"]

    if not service._is_ip_allowed(request.remote_addr):
        abort(403, description="Access denied")

    process_found = any(
        'local_llm' in (proc.info['name'] or '') or
        'local_llm' in ' '.join(proc.info.get('cmdline', []))
        for proc in psutil.process_iter(['pid', 'name', 'cmdline'])
        if service._safe_process(proc)
    )

    status = "up" if process_found else "down"
    return jsonify({'status': status, 'timestamp': time.time()})


@llm_bp.route('/llm_status/<host>', methods=['GET'])
@login_required
def llm_status(host):
    """
    Returns the online/offline status of a given LLM host.
    """
    try:
        process_found = any(
            'local_llm' in (proc.info['name'] or '') or
            'local_llm' in ' '.join(proc.info.get('cmdline', []))
            for proc in psutil.process_iter(['pid', 'name', 'cmdline'])
            if current_app.config["SERVICE_INSTANCE"]._safe_process(proc)
        )

        status = "online" if process_found else "offline"
        return jsonify({"status": status})

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
