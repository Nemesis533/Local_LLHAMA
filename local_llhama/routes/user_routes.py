# user_routes.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required

user_bp = Blueprint("user", __name__)

@user_bp.route('/from_user_text', methods=['POST'])
@login_required
def from_user_text():
    """
    Receives user text from the frontend and processes it.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    user_text = data['text']
    # WebUI requests are always marked as from_webui=True
    from_webui = data.get('from_webui', True)

    with current_app.app_context():
        service = current_app.config["SERVICE_INSTANCE"]
        service.send_ollama_command(text=user_text, from_webui=from_webui)

    return jsonify({"success": True})
