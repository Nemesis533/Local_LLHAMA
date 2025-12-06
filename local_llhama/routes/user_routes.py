# user_routes.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required

user_bp = Blueprint("user", __name__)

@user_bp.route('/from_user_text', methods=['POST'])
@login_required
def from_user_text():
    """
    Receives user text from the frontend and processes it.
    Uses dedicated chat handler to avoid state machine conflicts.
    """
    from flask import session
    
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    user_text = data['text']
    # Get client_id from session
    client_id = data.get('client_id') or session.get('_id')

    with current_app.app_context():
        service = current_app.config["SERVICE_INSTANCE"]
        # Route to dedicated chat handler instead of state machine
        service.send_chat_message(text=user_text, client_id=client_id)

    return jsonify({"success": True})
