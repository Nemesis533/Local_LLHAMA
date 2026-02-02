# system_routes.py
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from ..error_handler import FlaskErrorHandler
from ..system_metrics import SystemMetrics

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


@system_bp.route("/api/system-metrics", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_system_metrics():
    """
    Get current system metrics (CPU, RAM, GPU).
    Admin only endpoint.
    """
    # Check if user is admin
    if not current_user.is_admin:
        return jsonify({"error": "Admin access required"}), 403

    metrics = SystemMetrics.get_all_metrics()
    return jsonify(metrics)
