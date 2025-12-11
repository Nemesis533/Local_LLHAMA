# user_routes.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

user_bp = Blueprint("user", __name__)

@user_bp.route('/new_conversation', methods=['POST'])
@login_required
def new_conversation():
    """
    Create a new conversation immediately and return its ID.
    Frontend should call this when "new chat" button is clicked,
    then use the returned conversation_id for subsequent messages.
    """
    try:
        with current_app.app_context():
            service = current_app.config["SERVICE_INSTANCE"]
            if not service.pg_client:
                return jsonify({
                    "success": False,
                    "error": "Database not available"
                }), 500
            
            # Create new conversation
            user_id = current_user.id
            from datetime import datetime
            now = datetime.now()
            conv_datetime = now.strftime("%b %d, %Y at %H:%M")
            conversation_id = service.pg_client.create_conversation(
                user_id=user_id,
                title=f"Chat - {conv_datetime}"
            )
            
            return jsonify({
                "success": True,
                "conversation_id": conversation_id
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@user_bp.route('/from_user_text', methods=['POST'])
@login_required
def from_user_text():
    """
    Receives user text from the frontend and processes it.
    Uses dedicated chat handler to avoid state machine conflicts.
    
    Returns the conversation_id so frontend can store and send it with next message.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    user_text = data['text']
    conversation_id = data.get('conversation_id')  # Get conversation_id from frontend (may be None for new)
    # Use authenticated user's ID as client_id for per-user conversation tracking
    client_id = str(current_user.id)

    with current_app.app_context():
        service = current_app.config["SERVICE_INSTANCE"]
        # Route to dedicated chat handler instead of state machine
        # send_chat_message now returns the conversation_id
        returned_conversation_id = service.send_chat_message(text=user_text, client_id=client_id, conversation_id=conversation_id)

    # Return success + conversation_id for frontend to store
    return jsonify({
        "success": True,
        "conversation_id": returned_conversation_id
    })

@user_bp.route('/api/current_user', methods=['GET'])
@login_required
def get_current_user():
    """
    Returns information about the currently authenticated user.
    """
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "can_access_dashboard": current_user.can_access_dashboard
    })
