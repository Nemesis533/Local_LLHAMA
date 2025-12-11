"""
Chat History routes

Handles loading and displaying conversation history for the web UI.
Provides endpoints for listing conversations and retrieving full conversation details.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

chat_history_bp = Blueprint("chat_history", __name__, url_prefix="/api/chat")

# Global reference to conversation loader (will be set during init)
_conversation_loader = None


def init_chat_history_routes(conversation_loader):
    """
    @brief Initialize chat history routes with conversation loader.
    @param conversation_loader ConversationLoader instance to use
    """
    global _conversation_loader
    _conversation_loader = conversation_loader


def get_conversation_loader():
    """
    @brief Get the conversation loader instance.
    @return ConversationLoader instance or None
    """
    global _conversation_loader
    return _conversation_loader


@chat_history_bp.route("/conversations", methods=["GET"])
@login_required
def get_conversations():
    """
    @brief Get list of all conversations for current user.
           First 40 conversations include full messages, rest are metadata only.
    @return JSON response with conversation list or error
    """
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return (
                jsonify(
                    {"success": False, "error": "Conversation loader not initialized"}
                ),
                500,
            )

        limit = request.args.get("limit", default=100, type=int)
        full_message_limit = 40

        conversations = conversation_loader.get_user_conversations_with_limit(
            user_id=current_user.id, limit=limit, full_message_limit=full_message_limit
        )

        conv_list = []
        for idx, conv in enumerate(conversations):
            include_messages = idx < full_message_limit
            conv_list.append(conv.to_dict(include_messages=include_messages))

        return jsonify({"success": True, "conversations": conv_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_history_bp.route("/conversations/<conversation_id>", methods=["GET"])
@login_required
def get_conversation(conversation_id):
    """
    @brief Get full conversation with all messages.
    @param conversation_id ID of conversation to retrieve
    @return JSON response with full conversation or error
    """
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return (
                jsonify(
                    {"success": False, "error": "Conversation loader not initialized"}
                ),
                500,
            )

        conversation = conversation_loader.load_conversation(conversation_id)

        if not conversation:
            return jsonify({"success": False, "error": "Conversation not found"}), 404

        # Ensures that user can only access their own conversations
        if conversation.user_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        return jsonify(
            {
                "success": True,
                "conversation": conversation.to_dict(include_messages=True),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_history_bp.route("/conversations/<conversation_id>/delete", methods=["POST"])
@login_required
def delete_conversation(conversation_id):
    """
    @brief Delete a conversation (only if it belongs to current user).
    @param conversation_id ID of conversation to delete
    @return JSON response with deletion result or error
    """
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return (
                jsonify(
                    {"success": False, "error": "Conversation loader not initialized"}
                ),
                500,
            )

        conversation = conversation_loader.load_conversation(conversation_id)

        if not conversation:
            return jsonify({"success": False, "error": "Conversation not found"}), 404

        if conversation.user_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        # Delete in correct order: embeddings first, then messages, then conversation
        pg_client = conversation_loader.pg_client

        try:
            pg_client.execute_write(
                """DELETE FROM message_embeddings 
                   WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = %s)""",
                (conversation_id,),
            )

            pg_client.execute_write(
                "DELETE FROM messages WHERE conversation_id = %s", (conversation_id,)
            )

            pg_client.execute_write(
                "DELETE FROM conversations WHERE id = %s", (conversation_id,)
            )

            return (
                jsonify(
                    {"success": True, "message": "Conversation deleted successfully"}
                ),
                200,
            )
        except Exception as e:
            print(
                f"[chat_history_routes] Error deleting conversation {conversation_id}: {str(e)}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Failed to delete conversation: {str(e)}",
                    }
                ),
                500,
            )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
