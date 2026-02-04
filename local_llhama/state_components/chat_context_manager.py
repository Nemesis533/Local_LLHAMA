"""
Chat Context Manager

Manages conversation history, context windows, and database persistence
for the ChatHandler component.
"""

from ..shared_logger import LogLevel
from .context_summarizer import ContextSummarizer


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
        context_management_mode="truncate",
        context_summarization_model="decision",
        context_summary_target_words=150,
        main_llm_client=None,
        decision_llm_client=None,
        message_handler=None,
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
        @param context_management_mode Mode for context handling: "truncate" or "summarize"
        @param context_summarization_model Which model to use for summarization: "main", "decision", or "auto"
        @param context_summary_target_words Target word count for context summaries
        @param main_llm_client Main LLM client for summarization
        @param decision_llm_client Decision LLM client for summarization
        @param message_handler MessageHandler instance for sending user notifications
        """
        self.pg_client = pg_client
        self.conversation_loader = conversation_loader
        self.log_prefix = log_prefix
        self.message_handler = message_handler

        self.conversation_history = {}

        self.client_conversations = {}

        self.first_message_after_load = {}

        # Adaptive context window management
        self.context_word_limits = {}

        # Context window configuration
        self.default_context_words = default_context_words
        self.min_context_words = min_context_words
        self.context_reduction_factor = context_reduction_factor
        self.history_exchanges = history_exchanges

        # Context summarization configuration
        self.context_management_mode = context_management_mode
        self.context_summarization_model = context_summarization_model
        self.context_summary_target_words = context_summary_target_words

        # Initialize context summarizer if summarization is enabled
        self.context_summarizer = None
        if context_management_mode == "summarize" and (
            main_llm_client or decision_llm_client
        ):
            self.context_summarizer = ContextSummarizer(
                main_llm_client=main_llm_client,
                decision_llm_client=decision_llm_client,
                log_prefix=f"{log_prefix} [Summarizer]",
            )

        # Store context summaries for clients
        self.client_context_summaries = {}

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Context manager initialized (mode: {context_management_mode})"
        )

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
        # Load persistent context from DB if not cached
        persistent_context = self._load_persistent_context_from_db(client_id)

        # Build appropriate prompt based on available context
        if persistent_context:
            return self._build_prompt_with_persistent_context(
                client_id, text, persistent_context
            )
        elif self._has_memory_history(client_id):
            return self._build_prompt_with_memory_only(client_id, text)
        else:
            return text, False

    def _load_persistent_context_from_db(self, client_id):
        """
        Load and cache persistent context from database.

        @param client_id The client identifier
        @return Cached or newly loaded persistent context, or None
        """
        conversation_id = self.client_conversations.get(client_id)

        # Initialize cache if needed
        if not hasattr(self, "_persistent_context_cache"):
            self._persistent_context_cache = {}

        # Return cached context if available
        persistent_context = self._persistent_context_cache.get(client_id)
        if persistent_context is not None:
            return persistent_context

        # Load from DB if available
        if not (self.conversation_loader and conversation_id):
            return None

        try:
            # Get current context word limit for this client
            if client_id not in self.context_word_limits:
                self.context_word_limits[client_id] = self.default_context_words

            max_words = self.context_word_limits[client_id]

            persistent_context = (
                self.conversation_loader.get_conversation_context_for_llm(
                    conversation_id, max_words=max_words
                )
            )

            if persistent_context:
                # Cache for subsequent messages
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

            return persistent_context

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to load conversation context: {repr(e)}"
            )
            return None

    def _build_prompt_with_persistent_context(
        self, client_id, text, persistent_context
    ):
        """
        Build prompt combining persistent DB context with in-memory history.

        @param client_id The client identifier
        @param text Current user message
        @param persistent_context Cached persistent context from DB
        @return tuple of (prompt, used_persistent_context)
        """
        from ..llm_prompts import RESUME_CONVERSATION_PROMPT

        # Start with persistent context from DB
        prompt = f"{RESUME_CONVERSATION_PROMPT}\n\n{persistent_context}"

        # Add recent in-memory history if available
        if self._has_memory_history(client_id):
            history = self.conversation_history[client_id]
            prompt += (
                "\n\n---\n\nMost recent interactions (after the above history):\n"
            )
            prompt += self._format_history_text(history)

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Using cached persistent context + {len(history)} in-memory interactions"
            )
        else:
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Using cached persistent context only"
            )

        # Add current message and handle overflow
        current_msg_marker = "\n---\n\nThis is the user's next message: "
        prompt = self._check_and_handle_overflow(
            client_id, prompt, text, current_msg_marker, reserve_words=50
        )

        return prompt, True

    def _build_prompt_with_memory_only(self, client_id, text):
        """
        Build prompt using only in-memory history (no DB context).

        @param client_id The client identifier
        @param text Current user message
        @return tuple of (prompt, used_persistent_context)
        """
        history = self.conversation_history[client_id]
        history_text = "Previous interactions with the user:\n"
        history_text += self._format_history_text(history)

        # Add current message and handle overflow
        current_msg_marker = "\nThis is the last thing the user asked: "
        prompt = self._check_and_handle_overflow(
            client_id, history_text, text, current_msg_marker, reserve_words=30
        )

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Using in-memory history ({len(history)} interactions)"
        )
        return prompt, False

    def _has_memory_history(self, client_id):
        """
        Check if client has in-memory conversation history.

        @param client_id The client identifier
        @return True if history exists, False otherwise
        """
        return (
            client_id in self.conversation_history
            and self.conversation_history[client_id]
        )

    def _format_history_text(self, history):
        """
        Format conversation history as text.

        @param history List of interaction dictionaries
        @return Formatted history string
        """
        formatted = ""
        for interaction in history:
            formatted += f"User: {interaction['user']}\n"
            formatted += f"Assistant: {interaction['assistant']}\n"
        return formatted

    def _check_and_handle_overflow(
        self, client_id, context_text, current_message, message_marker, reserve_words
    ):
        """
        Check if prompt exceeds limits and handle overflow if needed.

        @param client_id The client identifier
        @param context_text Context text (without current message)
        @param current_message Current user message
        @param message_marker Marker text to separate context from message
        @param reserve_words Words to reserve for current message
        @return Final prompt with overflow handling applied
        """
        # Build full prompt
        prompt = f"{context_text}{message_marker}{current_message}"

        # Check if within limits
        prompt_words = len(prompt.split())
        target_words = self.context_word_limits.get(
            client_id, self.default_context_words
        )

        if prompt_words <= target_words:
            return prompt

        # Handle overflow
        overflow_type = (
            "Context overflow"
            if "persistent" in context_text.lower()
            else "In-memory context overflow"
        )
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] {overflow_type} detected ({prompt_words} > {target_words} words)"
        )

        processed_context = self.handle_context_overflow(
            client_id, context_text, target_words - reserve_words
        )
        return f"{processed_context}{message_marker}{current_message}"

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
        if len(self.conversation_history[client_id]) > self.history_exchanges:
            self.conversation_history[client_id] = self.conversation_history[client_id][
                -self.history_exchanges :
            ]

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Stored interaction (history size: {len(self.conversation_history[client_id])})"
        )

    def handle_context_overflow(
        self, client_id, context_text: str, target_words: int
    ) -> str:
        """
        Handle context overflow either by summarization or truncation based on mode.

        @param client_id Client identifier
        @param context_text Full context text that exceeds limits
        @param target_words Target word count for reduced context
        @return Processed context (summarized or truncated)
        """
        if self.context_management_mode == "summarize" and self.context_summarizer:
            return self._handle_context_with_summarization(
                client_id, context_text, target_words
            )
        else:
            return self._handle_context_with_truncation(context_text, target_words)

    def _handle_context_with_summarization(
        self, client_id: str, context_text: str, target_words: int
    ) -> str:
        """
        Handle context overflow using summarization.

        @param client_id Client identifier
        @param context_text Full context text
        @param target_words Target word count
        @return Summarized context with recent history
        """
        try:
            # Notify user that summarization is happening
            if self.message_handler:
                self.message_handler.send_message(
                    client_id,
                    {
                        "type": "system",
                        "message": "⏳ Summarizing conversation context...",
                    },
                )

            # Check if we already have a summary for this client
            existing_summary = self.client_context_summaries.get(client_id)

            # Determine how much context to summarize vs keep recent
            recent_words = min(target_words // 3, 300)  # Keep ~1/3 as recent context
            summary_words = target_words - recent_words

            # Split context into older (to summarize) and recent (to keep)
            words = context_text.split()
            if len(words) <= target_words:
                return context_text  # No need to process if within limits

            # Keep recent words as-is, summarize the older portion
            recent_text = " ".join(words[-recent_words:])
            older_text = " ".join(words[:-recent_words])

            # If we have an existing summary, combine it with older text for new summary
            if existing_summary:
                text_to_summarize = f"{existing_summary}\n\n---\n\n{older_text}"
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Combining existing summary with new context for re-summarization"
                )
            else:
                text_to_summarize = older_text

            # Generate new summary
            summary = self.context_summarizer.summarize_context(
                context_text=text_to_summarize,
                target_words=summary_words,
                model_preference=self.context_summarization_model,
            )

            if summary:
                # Store the new summary for this client
                self.client_context_summaries[client_id] = summary

                # Combine summary with recent context
                final_context = (
                    f"{summary}\n\n---\n\nRecent conversation:\n{recent_text}"
                )

                # Log compression stats
                stats = self.context_summarizer.get_summary_stats(
                    context_text, final_context
                )
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Context summarized: "
                    f"{stats['original_words']} → {stats['summary_words']} words "
                    f"({stats['compression_ratio']:.1f}% reduction)"
                )

                return final_context
            else:
                # Fallback to truncation if summarization fails
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Summarization failed, falling back to truncation"
                )
                return self._handle_context_with_truncation(context_text, target_words)

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Context summarization error: {e}"
            )
            return self._handle_context_with_truncation(context_text, target_words)

    def _handle_context_with_truncation(
        self, context_text: str, target_words: int
    ) -> str:
        """
        Handle context overflow using simple truncation.

        @param context_text Full context text
        @param target_words Target word count
        @return Truncated context
        """
        words = context_text.split()
        if len(words) <= target_words:
            return context_text

        truncated = " ".join(words[-target_words:])
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Context truncated: {len(words)} → {target_words} words"
        )
        return truncated

    def reduce_context_window(self, client_id):
        """
        Reduce the context window for a client after timeout.

        @param client_id Client identifier
        """
        if client_id not in self.context_word_limits:
            self.context_word_limits[client_id] = self.default_context_words

        old_limit = self.context_word_limits[client_id]
        new_limit = max(
            int(old_limit * self.context_reduction_factor), self.min_context_words
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
        if client_id in self.client_context_summaries:
            del self.client_context_summaries[client_id]

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Cleared data for client {client_id}"
        )
