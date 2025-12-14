"""
Chat Context Manager

Manages conversation history, context windows, and database persistence
for the ChatHandler component.
"""

from ..shared_logger import LogLevel


class ChatContextManager:
    """
    Manages conversation context, history, and adaptive context windows for chat sessions.
    """

    def __init__(
        self,
        pg_client,
        conversation_loader,
        log_prefix="[Chat Context]",
        default_context_words=400,
        min_context_words=100,
        context_reduction_factor=0.7,
        history_exchanges=3,
    ):
        """
        Initialize the context manager.

        @param pg_client PostgreSQL client for database operations
        @param conversation_loader ConversationLoader instance for loading history
        @param log_prefix Prefix for log messages
        @param default_context_words Default context window size in words
        @param min_context_words Minimum context window size in words
        @param context_reduction_factor Factor to reduce context on timeout
        @param history_exchanges Number of recent exchanges to keep in memory
        """
        self.pg_client = pg_client
        self.conversation_loader = conversation_loader
        self.log_prefix = log_prefix

        self.conversation_history = {}

        self.client_conversations = {}

        self.first_message_after_load = {}

        # Adaptive context window management
        self.context_word_limits = {}

        # Context window configuration
        self.DEFAULT_CONTEXT_WORDS = default_context_words
        self.MIN_CONTEXT_WORDS = min_context_words
        self.CONTEXT_REDUCTION_FACTOR = context_reduction_factor
        self.HISTORY_EXCHANGES = history_exchanges
        self.CONTEXT_REDUCTION_FACTOR = context_reduction_factor

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Context manager initialized")

    def ensure_conversation_exists(self, client_id, passed_conversation_id=None):
        """
        Ensure a conversation exists for the client.

        @param client_id The client identifier
        @param passed_conversation_id Optional conversation_id from frontend
        @return conversation_id The conversation UUID
        """
        # If passed_conversation_id is provided, use it (continuing existing chat)
        if passed_conversation_id:
            old_conversation_id = self.client_conversations.get(client_id)

            if old_conversation_id != passed_conversation_id:
                # Conversation changed - clear context cache and in-memory history
                if client_id in self.conversation_history:
                    del self.conversation_history[client_id]

                # Clear cached persistent context for this client
                if (
                    hasattr(self, "_persistent_context_cache")
                    and client_id in self._persistent_context_cache
                ):
                    del self._persistent_context_cache[client_id]

                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Switched to conversation {passed_conversation_id}, cleared cache, will load full context"
                )
            else:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Continuing conversation {passed_conversation_id}"
                )

            self.client_conversations[client_id] = passed_conversation_id
            return passed_conversation_id

        elif client_id not in self.client_conversations:
            # Fallback: create new conversation if needed
            if self.pg_client:
                try:
                    user_id = int(client_id)
                    from datetime import datetime

                    now = datetime.now()
                    conv_datetime = now.strftime("%b %d, %Y at %H:%M")
                    conversation_id = self.pg_client.create_conversation(
                        user_id=user_id, title=f"Chat - {conv_datetime}"
                    )
                    self.client_conversations[client_id] = conversation_id
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] Created conversation {conversation_id} for user {user_id}"
                    )
                    return conversation_id
                except Exception as e:
                    print(
                        f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to create conversation: {e}"
                    )
                    self.client_conversations[client_id] = None
                    return None
            else:
                self.client_conversations[client_id] = None
                return None

        return self.client_conversations.get(client_id)

    def get_context_for_prompt(self, client_id, text):
        """
        Get conversation context to include in the LLM prompt.
        Always combines persistent DB context with recent in-memory history.

        @param client_id The client identifier
        @param text Current user message
        @return tuple of (prompt, used_persistent_context)
        """
        conversation_id = self.client_conversations.get(client_id)

        # Cache persistent context per client after first load
        if not hasattr(self, "_persistent_context_cache"):
            self._persistent_context_cache = {}

        persistent_context = self._persistent_context_cache.get(client_id)

        # Load full context from DB if not already cached
        if persistent_context is None and self.conversation_loader and conversation_id:
            try:
                # Get current context word limit for this client
                if client_id not in self.context_word_limits:
                    self.context_word_limits[client_id] = self.DEFAULT_CONTEXT_WORDS

                max_words = self.context_word_limits[client_id]

                persistent_context = (
                    self.conversation_loader.get_conversation_context_for_llm(
                        conversation_id, max_words=max_words
                    )
                )

                if persistent_context:
                    # Cache it for subsequent messages
                    self._persistent_context_cache[client_id] = persistent_context

                    context_chars = len(persistent_context)
                    context_words = len(persistent_context.split())
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] Loaded and cached full context ({context_chars} chars, ~{context_words} words, limit: {max_words})"
                    )
                else:
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] No persistent context for conversation {conversation_id}"
                    )

            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to load conversation context: {repr(e)}"
                )

        # Build prompt combining cached persistent context + in-memory history
        if persistent_context:
            from ..llm_prompts import RESUME_CONVERSATION_PROMPT

            # Start with persistent context from DB (cached)
            prompt = f"{RESUME_CONVERSATION_PROMPT}\n\n{persistent_context}"

            # Add recent in-memory history if available
            if (
                client_id in self.conversation_history
                and self.conversation_history[client_id]
            ):
                history = self.conversation_history[client_id]
                prompt += (
                    "\n\n---\n\nMost recent interactions (after the above history):\n"
                )
                for interaction in history:
                    prompt += f"User: {interaction['user']}\n"
                    prompt += f"Assistant: {interaction['assistant']}\n"

                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Using cached persistent context + {len(history)} in-memory interactions"
                )
            else:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Using cached persistent context only"
                )

            # Add current message
            prompt += f"\n---\n\nThis is the user's next message: {text}"
            return prompt, True

        # No persistent context - use only in-memory history
        elif (
            client_id in self.conversation_history
            and self.conversation_history[client_id]
        ):
            history = self.conversation_history[client_id]
            history_text = "Previous interactions with the user:\n"
            for interaction in history:
                history_text += f"User: {interaction['user']}\n"
                history_text += f"Assistant: {interaction['assistant']}\n"

            prompt = f"{history_text}\nThis is the last thing the user asked: {text}"
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Using in-memory history ({len(history)} interactions)"
            )
            return prompt, False

        # No context available, use original text
        return text, False

    def add_to_history(self, client_id, user_text, assistant_text):
        """
        Add interaction to conversation history, keeping last N exchanges.

        @param client_id Client identifier
        @param user_text User's message
        @param assistant_text Assistant's response
        """
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []

        self.conversation_history[client_id].append(
            {"user": user_text, "assistant": assistant_text}
        )

        # Keep only last N interactions (configurable)
        if len(self.conversation_history[client_id]) > self.HISTORY_EXCHANGES:
            self.conversation_history[client_id] = self.conversation_history[client_id][
                -self.HISTORY_EXCHANGES :
            ]

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Stored interaction (history size: {len(self.conversation_history[client_id])})"
        )

    def reduce_context_window(self, client_id):
        """
        Reduce the context window for a client after timeout.

        @param client_id Client identifier
        """
        if client_id not in self.context_word_limits:
            self.context_word_limits[client_id] = self.DEFAULT_CONTEXT_WORDS

        old_limit = self.context_word_limits[client_id]
        new_limit = max(
            int(old_limit * self.CONTEXT_REDUCTION_FACTOR), self.MIN_CONTEXT_WORDS
        )
        self.context_word_limits[client_id] = new_limit

        print(
            f"{self.log_prefix} [{LogLevel.WARNING.name}] Context window reduced: {old_limit} -> {new_limit} words"
        )

    def clear_client_data(self, client_id):
        """
        Clear all cached data for a specific client.

        @param client_id Client identifier
        """
        if client_id in self.conversation_history:
            del self.conversation_history[client_id]
        if client_id in self.client_conversations:
            del self.client_conversations[client_id]
        if client_id in self.first_message_after_load:
            del self.first_message_after_load[client_id]
        if client_id in self.context_word_limits:
            del self.context_word_limits[client_id]
        if (
            hasattr(self, "_persistent_context_cache")
            and client_id in self._persistent_context_cache
        ):
            del self._persistent_context_cache[client_id]

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Cleared data for client {client_id}"
        )
