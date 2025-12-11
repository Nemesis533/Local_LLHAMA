# system_routes.py
from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from ..error_handler import FlaskErrorHandler

system_bp = Blueprint("system", __name__)


@system_bp.route("/restart-system", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def restart_system():
    """
    Enqueues a restart command to the LLM system.
    """
    data = request.get_json()
    service = current_app.config["SERVICE_INSTANCE"]

    if data and data.get("action") == "restart":
        message = {"type": "restart_system", "data": None}
        service.action_message_queue.put(message, timeout=2.0)
        return {}
    else:
        return jsonify({"success": False, "error": "Invalid action"}), 400
