"""
Preset Routes

Web API endpoints for managing configuration presets.
Uses message queue pattern to communicate with main process.
"""

import time
import uuid
from queue import Empty

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

preset_bp = Blueprint("preset", __name__)


def _send_preset_request(
    action_message_queue, preset_response_queue, request_type, data=None, timeout=5.0
):
    """
    Send a preset request via queue and wait for response.

    Uses dedicated response queue with request ID for clean communication.
    """
    # Generate unique request ID
    request_id = str(uuid.uuid4())

    message = {
        "type": "preset_request",
        "request_type": request_type,
        "request_id": request_id,
        "data": data,
    }

    try:
        # Send request
        action_message_queue.put(message, timeout=1.0)

        # Poll response queue for our request ID
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = preset_response_queue.get(timeout=0.1)
                # Check if this response is for this request type
                if response.get("request_id") == request_id:
                    return response
                else:
                    # Not the right response type, re-queue it
                    preset_response_queue.put(response)
                    time.sleep(0.05)
            except Empty:
                continue

        return {"status": "error", "message": "Request timed out"}
    except Exception as e:
        return {"status": "error", "message": f"Request failed: {str(e)}"}


@preset_bp.route("/presets", methods=["GET"])
@login_required
def list_presets():
    """
    Get list of all available configuration presets.
    """
    try:
        service = current_app.config["SERVICE_INSTANCE"]

        if not service.action_message_queue:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Action message queue not initialized",
                    }
                ),
                500,
            )
        if not service.preset_response_queue:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Preset response queue not initialized",
                    }
                ),
                500,
            )

        response = _send_preset_request(
            service.action_message_queue, service.preset_response_queue, "list_presets"
        )

        if response["status"] == "ok":
            return jsonify(response)
        else:
            return jsonify(response), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@preset_bp.route("/presets/<preset_id>", methods=["GET"])
@login_required
def get_preset_info(preset_id):
    """
    Get detailed information about a specific preset.
    """
    try:
        service = current_app.config["SERVICE_INSTANCE"]
        response = _send_preset_request(
            service.action_message_queue,
            service.preset_response_queue,
            "get_preset_info",
            {"preset_id": preset_id},
        )

        if response["status"] == "ok":
            return jsonify(response)
        elif response.get("not_found"):
            return jsonify(response), 404
        else:
            return jsonify(response), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@preset_bp.route("/presets/<preset_id>/apply", methods=["POST"])
@login_required
def apply_preset(preset_id):
    """
    Apply a preset to the current configuration.

    Note: Requires system restart for changes to take effect.
    """
    try:
        service = current_app.config["SERVICE_INSTANCE"]
        response = _send_preset_request(
            service.action_message_queue,
            service.preset_response_queue,
            "apply_preset",
            {"preset_id": preset_id},
            timeout=10.0,  # Longer timeout for file operations
        )

        if response["status"] == "ok":
            return jsonify(response)
        elif response.get("not_found"):
            return jsonify(response), 404
        else:
            return jsonify(response), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@preset_bp.route("/presets/<preset_id>/validate", methods=["GET"])
@login_required
def validate_preset(preset_id):
    """
    Validate a preset's structure and configuration.
    """
    try:
        service = current_app.config["SERVICE_INSTANCE"]
        response = _send_preset_request(
            service.action_message_queue,
            service.preset_response_queue,
            "validate_preset",
            {"preset_id": preset_id},
        )

        return jsonify(response)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@preset_bp.route("/presets/current", methods=["GET"])
@login_required
def get_current_config():
    """
    Get the current configuration summary.
    """
    try:
        service = current_app.config["SERVICE_INSTANCE"]
        response = _send_preset_request(
            service.action_message_queue,
            service.preset_response_queue,
            "get_current_config",
        )

        return jsonify(response)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@preset_bp.route("/presets", methods=["POST"])
@login_required
def create_preset():
    """
    Create a new preset from provided configuration.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        service = current_app.config["SERVICE_INSTANCE"]
        response = _send_preset_request(
            service.action_message_queue,
            service.preset_response_queue,
            "create_preset",
            data,
        )

        if response["status"] == "ok":
            return jsonify(response), 201
        else:
            return jsonify(response), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
