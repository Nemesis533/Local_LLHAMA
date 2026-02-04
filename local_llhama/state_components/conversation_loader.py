"""
Conversation Loader Component

Loads and manages conversation history from PostgreSQL for display and context resumption.
Handles fetching conversations, messages, and embedding summaries for LLM context.
"""

from datetime import datetime
from typing import Dict, List, Optional

from ..postgresql_client import PostgreSQLClient
from ..shared_logger import LogLevel


class ConversationMessage:
    """
    @brief Represents a single message in a conversation.
    """

    def __init__(
        self,
        message_id: int,
        conversation_id: str,
        user_id: int,
        role: str,
        content: str,
        timestamp: datetime,
        embedding_id: Optional[int] = None,
    ):
        self.message_id = message_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.role = role  # 'user' or 'assistant'
        self.content = content
        self.timestamp = timestamp
        self.embedding_id = embedding_id

    def to_dict(self) -> Dict:
        """
        @brief Convert message to dictionary for JSON serialization.
        """
        return {
            "id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": (
                self.timestamp.isoformat()
                if isinstance(self.timestamp, datetime)
                else str(self.timestamp)
            ),
        }


class Conversation:
    """
    @brief Represents a full conversation with all its messages.
    """

    def __init__(
        self,
        conversation_id: str,
        user_id: int,
        username: str,
        title: Optional[str] = None,
        created_at: Optional[datetime] = None,
        last_updated: Optional[datetime] = None,
    ):
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
        """
        @brief Add a message to the conversation.
        @param message ConversationMessage object to add
        """
        self.messages.append(message)

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

    def to_dict(self, include_messages: bool = True) -> Dict:
        """
        @brief Convert conversation to dictionary for JSON serialization.
        @param include_messages Whether to include full message list
        @return Dictionary representation of the conversation
        """
        data = {
            "id": self.conversation_id,
            "user_id": self.user_id,
            "username": self.username,
            "title": self.title,
            "created_at": (
                self.created_at.isoformat()
                if isinstance(self.created_at, datetime)
                else str(self.created_at)
            ),
            "last_updated": (
                self.last_updated.isoformat()
                if isinstance(self.last_updated, datetime)
                else str(self.last_updated)
            ),
            "message_count": len(self.messages),
        }

        if include_messages:
            data["messages"] = [msg.to_dict() for msg in self.messages]

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
        self.last_log_message = None  # Track last log message to avoid duplicates

        if pg_client is None:
            self.pg_client = PostgreSQLClient()
        else:
            self.pg_client = pg_client

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Conversation loader initialized"
        )

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Load a complete conversation with all messages.

        @param conversation_id UUID of the conversation to load
        @return Conversation object with messages, or None if not found
        """
        try:
            # Get conversation metadata
            conv_results = self.pg_client.execute_query_dict(
                """SELECT c.id, c.user_id, u.username, c.title, c.created_at
                   FROM conversations c
                   JOIN users u ON c.user_id = u.id
                   WHERE c.id = %s""",
                (conversation_id,),
            )

            if not conv_results or len(conv_results) == 0:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Conversation not found: {conversation_id}"
                )
                return None

            conv_data = conv_results[0]
            conversation = Conversation(
                conversation_id=conv_data["id"],
                user_id=conv_data["user_id"],
                username=conv_data["username"],
                title=conv_data["title"],
                created_at=conv_data["created_at"],
                last_updated=conv_data["created_at"],  # Use created_at as last_updated
            )

            # Load all messages for this conversation
            msg_results = self.pg_client.execute_query_dict(
                """SELECT id, conversation_id, role, content, created_at
                   FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at ASC""",
                (conversation_id,),
            )

            if msg_results:
                for msg_data in msg_results:
                    message = ConversationMessage(
                        message_id=msg_data["id"],
                        conversation_id=msg_data["conversation_id"],
                        user_id=conversation.user_id,  # Use conversation's user_id
                        role=msg_data["role"],
                        content=msg_data["content"],
                        timestamp=msg_data["created_at"],
                        embedding_id=None,
                    )
                    conversation.add_message(message)

            return conversation

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Failed to load conversation: {repr(e)}"
            )
            return None

    def get_user_conversations_with_limit(
        self, user_id: int, limit: int = 100, full_message_limit: int = 40
    ) -> List[Conversation]:
        """
        Get conversations for a user with selective message loading.
        First N conversations include full messages, rest are metadata only.

        @param user_id User ID
        @param limit Maximum number of conversations to return
        @param full_message_limit Number of recent conversations to load with full messages
        @return List of Conversation objects (first N with messages, rest without)
        """
        try:
            results = self.pg_client.execute_query_dict(
                """SELECT c.id, c.user_id, u.username, c.title, c.created_at, COUNT(m.id) as message_count
                   FROM conversations c
                   JOIN users u ON c.user_id = u.id
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   WHERE c.user_id = %s
                   GROUP BY c.id, c.user_id, u.username, c.title, c.created_at
                   ORDER BY c.created_at DESC
                   LIMIT %s""",
                (user_id, limit),
            )

            conversations = []
            if results:
                for idx, conv_data in enumerate(results):
                    conversation = Conversation(
                        conversation_id=conv_data["id"],
                        user_id=conv_data["user_id"],
                        username=conv_data["username"],
                        title=conv_data["title"],
                        created_at=conv_data["created_at"],
                        last_updated=conv_data[
                            "created_at"
                        ],  # Use created_at as last_updated
                    )

                    # Load full messages only for the first N conversations
                    if idx < full_message_limit:
                        msg_results = self.pg_client.execute_query_dict(
                            """SELECT id, conversation_id, role, content, created_at
                               FROM messages
                               WHERE conversation_id = %s
                               ORDER BY created_at ASC""",
                            (conv_data["id"],),
                        )

                        if msg_results:
                            for msg_data in msg_results:
                                message = ConversationMessage(
                                    message_id=msg_data["id"],
                                    conversation_id=msg_data["conversation_id"],
                                    user_id=conversation.user_id,
                                    role=msg_data["role"],
                                    content=msg_data["content"],
                                    timestamp=msg_data["created_at"],
                                    embedding_id=None,
                                )
                                conversation.add_message(message)

                    conversations.append(conversation)

            return conversations

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Failed to load user conversations with limit: {repr(e)}"
            )
            return []

    def get_conversation_context_for_llm(
        self, conversation_id: str, max_words: int = 80000
    ) -> str:
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
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to get conversation context: {repr(e)}"
            )
            return ""
