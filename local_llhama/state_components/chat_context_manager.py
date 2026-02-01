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
        self.DEFAULT_CONTEXT_WORDS = default_context_words
        self.MIN_CONTEXT_WORDS = min_context_words
        self.CONTEXT_REDUCTION_FACTOR = context_reduction_factor
        self.HISTORY_EXCHANGES = history_exchanges
        self.CONTEXT_REDUCTION_FACTOR = context_reduction_factor

        # Context summarization configuration
        self.CONTEXT_MANAGEMENT_MODE = context_management_mode
        self.CONTEXT_SUMMARIZATION_MODEL = context_summarization_model
        self.CONTEXT_SUMMARY_TARGET_WORDS = context_summary_target_words

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

            # Check if prompt exceeds target length and process accordingly
            prompt_words = len(prompt.split())
            target_words = self.context_word_limits.get(
                client_id, self.DEFAULT_CONTEXT_WORDS
            )

            if prompt_words > target_words:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Context overflow detected ({prompt_words} > {target_words} words)"
                )
                # Extract just the context part (without current message) for processing
                context_part = prompt.replace(
                    f"\n---\n\nThis is the user's next message: {text}", ""
                )
                processed_context = self.handle_context_overflow(
                    client_id, context_part, target_words - 50
                )  # Reserve words for current message
                prompt = f"{processed_context}\n---\n\nThis is the user's next message: {text}"

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

            # Check if prompt exceeds target length and process accordingly
            prompt_words = len(prompt.split())
            target_words = self.context_word_limits.get(
                client_id, self.DEFAULT_CONTEXT_WORDS
            )

            if prompt_words > target_words:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] In-memory context overflow detected ({prompt_words} > {target_words} words)"
                )
                # Extract just the history part for processing
                history_part = prompt.replace(
                    f"\nThis is the last thing the user asked: {text}", ""
                )
                processed_history = self.handle_context_overflow(
                    client_id, history_part, target_words - 30
                )  # Reserve words for current message
                prompt = f"{processed_history}\nThis is the last thing the user asked: {text}"

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
        if self.CONTEXT_MANAGEMENT_MODE == "summarize" and self.context_summarizer:
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
                model_preference=self.CONTEXT_SUMMARIZATION_MODEL,
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
        if client_id in self.client_context_summaries:
            del self.client_context_summaries[client_id]

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Cleared data for client {client_id}"
        )
