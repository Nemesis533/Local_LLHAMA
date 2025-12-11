"""
Conversation Loader Component

Loads and manages conversation history from PostgreSQL for display and context resumption.
Handles fetching conversations, messages, and embedding summaries for LLM context.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json

from ..Shared_Logger import LogLevel
from ..PostgreSQL_Client import PostgreSQLClient


class ConversationMessage:
    """Represents a single message in a conversation."""
    
    def __init__(self, message_id: int, conversation_id: str, user_id: int, 
                 role: str, content: str, timestamp: datetime, embedding_id: Optional[int] = None):
        self.message_id = message_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.role = role  # 'user' or 'assistant'
        self.content = content
        self.timestamp = timestamp
        self.embedding_id = embedding_id
    
    def to_dict(self) -> Dict:
        """Convert message to dictionary for JSON serialization."""
        return {
            'id': self.message_id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        }


class Conversation:
    """Represents a full conversation with all its messages."""
    
    def __init__(self, conversation_id: str, user_id: int, username: str, 
                 title: Optional[str] = None, created_at: Optional[datetime] = None,
                 last_updated: Optional[datetime] = None):
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.username = username
        
        # If no title provided or title is in old format (e.g., "Chat 1"), generate from created_at
        if not title or (title and title.startswith("Chat ") and not " - " in title):
            if created_at:
                # Generate title from created_at timestamp
                if isinstance(created_at, datetime):
                    self.title = created_at.strftime("Chat - %b %d, %Y at %H:%M")
                else:
                    self.title = f"Conversation {conversation_id[:8]}"
            else:
                self.title = f"Conversation {conversation_id[:8]}"
        else:
            self.title = title
        
        self.created_at = created_at
        self.last_updated = last_updated
        self.messages: List[ConversationMessage] = []
    
    def add_message(self, message: ConversationMessage):
        """Add a message to the conversation."""
        self.messages.append(message)
    
    def sort_messages(self):
        """Sort messages by timestamp (oldest first)."""
        self.messages.sort(key=lambda m: m.timestamp)
    
    def get_last_n_words(self, n_words: int = 80000) -> str:
        """
        Get the last n words of the conversation as a concatenated string.
        
        @param n_words Maximum number of words to include
        @return Concatenated string of messages (newest to oldest until word limit)
        """
        total_words = 0
        result_messages = []
        
        # Iterate messages in reverse (newest first)
        for message in reversed(self.messages):
            words_in_message = len(message.content.split())
            if total_words + words_in_message > n_words and result_messages:
                # Stop if we've exceeded the limit and have at least one message
                break
            
            role_label = "User" if message.role == "user" else "Assistant"
            result_messages.append(f"{role_label}: {message.content}")
            total_words += words_in_message
        
        # Reverse back to chronological order
        result_messages.reverse()
        return "\n".join(result_messages)
    
    def get_messages(self, max_words: int = 80000) -> List[ConversationMessage]:
        """
        Get conversation messages as a list (for UI display).
        Returns the last n words worth of messages in chronological order.
        
        @param max_words Maximum number of words to include
        @return List of ConversationMessage objects
        """
        total_words = 0
        result_messages = []
        
        # Iterate messages in reverse (newest first)
        for message in reversed(self.messages):
            words_in_message = len(message.content.split())
            if total_words + words_in_message > max_words and result_messages:
                # Stop if we've exceeded the limit and have at least one message
                break
            
            result_messages.append(message)
            total_words += words_in_message
        
        # Reverse back to chronological order
        result_messages.reverse()
        return result_messages
    
    def to_dict(self, include_messages: bool = True) -> Dict:
        """Convert conversation to dictionary for JSON serialization."""
        data = {
            'id': self.conversation_id,
            'user_id': self.user_id,
            'username': self.username,
            'title': self.title,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            'last_updated': self.last_updated.isoformat() if isinstance(self.last_updated, datetime) else str(self.last_updated),
            'message_count': len(self.messages)
        }
        
        if include_messages:
            data['messages'] = [msg.to_dict() for msg in self.messages]
        
        return data


class ConversationLoader:
    """
    Loads and manages conversations from PostgreSQL.
    
    Provides methods to:
    - Load all conversations for a user
    - Load a specific conversation with all messages
    - Get last n words of a conversation
    - Build LLM context from conversation history
    """
    
    def __init__(self, pg_client: Optional[PostgreSQLClient] = None):
        """
        Initialize conversation loader.
        
        @param pg_client PostgreSQL client instance. If None, creates new one.
        """
        self.log_prefix = "[ConversationLoader]"
        
        if pg_client is None:
            self.pg_client = PostgreSQLClient()
        else:
            self.pg_client = pg_client
        
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Conversation loader initialized")
    
    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Load a complete conversation with all messages.
        
        @param conversation_id UUID of the conversation to load
        @return Conversation object with messages, or None if not found
        """
        try:
            # Get conversation metadata
            conv_results = self.pg_client.execute_query_dict(
                '''SELECT c.id, c.user_id, u.username, c.title, c.created_at
                   FROM conversations c
                   JOIN users u ON c.user_id = u.id
                   WHERE c.id = %s''',
                (conversation_id,)
            )
            
            if not conv_results or len(conv_results) == 0:
                print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Conversation not found: {conversation_id}")
                return None
            
            conv_data = conv_results[0]
            conversation = Conversation(
                conversation_id=conv_data['id'],
                user_id=conv_data['user_id'],
                username=conv_data['username'],
                title=conv_data['title'],
                created_at=conv_data['created_at'],
                last_updated=conv_data['created_at']  # Use created_at as last_updated
            )
            
            # Load all messages for this conversation
            msg_results = self.pg_client.execute_query_dict(
                '''SELECT id, conversation_id, role, content, created_at
                   FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at ASC''',
                (conversation_id,)
            )
            
            if msg_results:
                for msg_data in msg_results:
                    message = ConversationMessage(
                        message_id=msg_data['id'],
                        conversation_id=msg_data['conversation_id'],
                        user_id=conversation.user_id,  # Use conversation's user_id
                        role=msg_data['role'],
                        content=msg_data['content'],
                        timestamp=msg_data['created_at'],
                        embedding_id=None
                    )
                    conversation.add_message(message)
            
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Loaded conversation {conversation_id} with {len(conversation.messages)} messages")
            return conversation
        
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Failed to load conversation: {repr(e)}")
            return None
    
    def get_user_conversations(self, user_id: int, limit: int = 50) -> List[Conversation]:
        """
        Get all conversations for a user (without messages, for listing).
        
        @param user_id User ID
        @param limit Maximum number of conversations to return
        @return List of Conversation objects (without messages loaded)
        """
        try:
            results = self.pg_client.execute_query_dict(
                '''SELECT c.id, c.user_id, u.username, c.title, c.created_at, COUNT(m.id) as message_count
                   FROM conversations c
                   JOIN users u ON c.user_id = u.id
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   WHERE c.user_id = %s
                   GROUP BY c.id, c.user_id, u.username, c.title, c.created_at
                   ORDER BY c.created_at DESC
                   LIMIT %s''',
                (user_id, limit)
            )
            
            conversations = []
            if results:
                for conv_data in results:
                    conversation = Conversation(
                        conversation_id=conv_data['id'],
                        user_id=conv_data['user_id'],
                        username=conv_data['username'],
                        title=conv_data['title'],
                        created_at=conv_data['created_at'],
                        last_updated=conv_data['created_at']  # Use created_at as last_updated
                    )
                    # Add dummy messages to match the count for display purposes
                    for _ in range(int(conv_data.get('message_count', 0))):
                        conversation.messages.append(None)
                    conversations.append(conversation)
            
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Loaded {len(conversations)} conversations for user {user_id}")
            return conversations
        
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Failed to load user conversations: {repr(e)}")
            return []
    
    def get_conversation_word_count(self, conversation_id: str) -> int:
        """
        Get total word count for a conversation.
        
        @param conversation_id Conversation UUID
        @return Total word count
        """
        try:
            results = self.pg_client.execute_query(
                '''SELECT COALESCE(SUM(array_length(string_to_array(content, ' '), 1)), 0) as word_count
                   FROM messages
                   WHERE conversation_id = %s''',
                (conversation_id,)
            )
            
            if results and len(results) > 0:
                return int(results[0][0]) if results[0][0] else 0
            return 0
        
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to get word count: {repr(e)}")
            return 0
    
    def get_conversation_context_for_llm(self, conversation_id: str, max_words: int = 80000) -> str:
        """
        Get formatted conversation context for LLM (last n words).
        
        @param conversation_id Conversation UUID
        @param max_words Maximum words to include
        @return Formatted conversation string for LLM context
        """
        try:
            conversation = self.load_conversation(conversation_id)
            if not conversation:
                return ""
            
            return conversation.get_last_n_words(max_words)
        
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to get conversation context: {repr(e)}")
            return ""
    
    def get_conversation_messages_for_ui(self, conversation_id: str, max_words: int = 80000) -> List[Dict]:
        """
        Get conversation messages as list of dicts for UI display.
        Returns messages in chronological order ready to render as chat bubbles.
        
        @param conversation_id Conversation UUID
        @param max_words Maximum words to include
        @return List of message dicts with role and content
        """
        try:
            conversation = self.load_conversation(conversation_id)
            if not conversation:
                return []
            
            messages = conversation.get_messages(max_words)
            return [{
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat() if isinstance(msg.timestamp, datetime) else str(msg.timestamp)
            } for msg in messages]
        
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to get conversation messages: {repr(e)}")
            return []
