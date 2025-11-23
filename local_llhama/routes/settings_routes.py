# settings_routes.py
import json
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required

settings_bp = Blueprint("settings", __name__)

@settings_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    """
    Returns the current settings JSON.
    """
    service = current_app.config["SERVICE_INSTANCE"]
    return service.settings_data

@settings_bp.route('/settings', methods=['POST'])
@login_required
def save_settings():
    """
    Saves incoming settings JSON to a file.
    """
    data = request.get_json()
    service = current_app.config["SERVICE_INSTANCE"]

    with open(service.settings_file, 'w') as f:
        json.dump(data, f, indent=2)

    return jsonify({"status": "ok"})
