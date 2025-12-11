"""
Chat History routes

Handles loading and displaying conversation history for the web UI.
Provides endpoints for listing conversations and retrieving full conversation details.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

chat_history_bp = Blueprint('chat_history', __name__, url_prefix='/api/chat')

# Global reference to conversation loader (will be set during init)
_conversation_loader = None

def init_chat_history_routes(conversation_loader):
    """Initialize chat history routes with conversation loader"""
    global _conversation_loader
    _conversation_loader = conversation_loader

def get_conversation_loader():
    """Get the conversation loader instance"""
    global _conversation_loader
    return _conversation_loader

@chat_history_bp.route('/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Get list of all conversations for current user"""
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return jsonify({
                'success': False,
                'error': 'Conversation loader not initialized'
            }), 500
            
        limit = request.args.get('limit', default=50, type=int)
        conversations = conversation_loader.get_user_conversations(
            user_id=current_user.id,
            limit=limit
        )
        
        # Return as list of dicts without messages (for listing)
        conv_list = [conv.to_dict(include_messages=False) for conv in conversations]
        
        return jsonify({
            'success': True,
            'conversations': conv_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_history_bp.route('/conversations/<conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    """Get full conversation with all messages"""
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return jsonify({
                'success': False,
                'error': 'Conversation loader not initialized'
            }), 500
            
        conversation = conversation_loader.load_conversation(conversation_id)
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        # Verify ownership
        if conversation.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict(include_messages=True)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_history_bp.route('/conversations/<conversation_id>/delete', methods=['POST'])
@login_required
def delete_conversation(conversation_id):
    """Delete a conversation (only if it belongs to current user)"""
    try:
        conversation_loader = get_conversation_loader()
        if not conversation_loader:
            return jsonify({
                'success': False,
                'error': 'Conversation loader not initialized'
            }), 500
        
        # Verify ownership first by loading conversation
        conversation = conversation_loader.load_conversation(conversation_id)
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        if conversation.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        # Delete in correct order: embeddings first, then messages, then conversation
        pg_client = conversation_loader.pg_client
        
        try:
            # Delete embeddings for messages in this conversation
            pg_client.execute_write(
                '''DELETE FROM message_embeddings 
                   WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = %s)''',
                (conversation_id,)
            )
            
            # Delete all messages in this conversation
            pg_client.execute_write(
                'DELETE FROM messages WHERE conversation_id = %s',
                (conversation_id,)
            )
            
            # Delete the conversation
            pg_client.execute_write(
                'DELETE FROM conversations WHERE id = %s',
                (conversation_id,)
            )
            
            return jsonify({
                'success': True,
                'message': 'Conversation deleted successfully'
            }), 200
        except Exception as e:
            print(f"[chat_history_routes] Error deleting conversation {conversation_id}: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Failed to delete conversation: {str(e)}'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

