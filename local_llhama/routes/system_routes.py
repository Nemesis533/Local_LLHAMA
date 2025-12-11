# system_routes.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required

system_bp = Blueprint("system", __name__)

@system_bp.route("/restart-system", methods=["POST"])
@login_required
def restart_system():
    """
    Enqueues a restart command to the LLM system.
    """
    try:
        data = request.get_json()
        service = current_app.config["SERVICE_INSTANCE"]

        if data and data.get("action") == "restart":
            message = {
                "type": "restart_system",
                "data": None
            }
            service.action_message_queue.put(message, timeout=2.0)
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
