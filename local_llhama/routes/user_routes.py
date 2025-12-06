# user_routes.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

user_bp = Blueprint("user", __name__)

@user_bp.route('/from_user_text', methods=['POST'])
@login_required
def from_user_text():
    """
    Receives user text from the frontend and processes it.
    Uses dedicated chat handler to avoid state machine conflicts.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    user_text = data['text']
    # Use authenticated user's ID as client_id for per-user conversation tracking
    client_id = str(current_user.id)

    with current_app.app_context():
        service = current_app.config["SERVICE_INSTANCE"]
        # Route to dedicated chat handler instead of state machine
        service.send_chat_message(text=user_text, client_id=client_id)

    return jsonify({"success": True})

@user_bp.route('/api/current_user', methods=['GET'])
@login_required
def get_current_user():
    """
    Returns information about the currently authenticated user.
    """
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin
    })
