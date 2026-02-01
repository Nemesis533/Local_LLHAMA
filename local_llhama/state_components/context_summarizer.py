"""
Context Summarizer Component

Provides context summarization functionality using either the main model
or decision model to create concise summaries when context exceeds limits.
"""

from typing import Optional
from ..shared_logger import LogLevel


class ContextSummarizer:
    """
    Handles context summarization using LLM models to create concise summaries
    when conversation context exceeds target length limits.
    """

    def __init__(
        self,
        main_llm_client,
        decision_llm_client=None,
        log_prefix="[Context Summarizer]",
    ):
        """
        Initialize the context summarizer.

        @param main_llm_client Main LLM client for summarization
        @param decision_llm_client Optional separate decision model client
        @param log_prefix Prefix for log messages
        """
        self.main_llm_client = main_llm_client
        self.decision_llm_client = decision_llm_client
        self.log_prefix = log_prefix

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Context summarizer initialized")

    def summarize_context(
        self,
        context_text: str,
        target_words: int = 150,
        model_preference: str = "decision"
    ) -> Optional[str]:
        """
        Summarize context text into a concise bullet point summary.

        @param context_text The full context text to summarize
        @param target_words Target number of words for the summary
        @param model_preference Which model to use: "main", "decision", or "auto"
        @return Summarized context as string, or None if summarization fails
        """
        if not context_text or not context_text.strip():
            return None

        # Select the appropriate model
        llm_client = self._select_model(model_preference)
        if not llm_client:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] No suitable model available for summarization")
            return None

        # Build summarization prompt
        summary_prompt = self._build_summary_prompt(context_text, target_words)

        try:
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Generating context summary (~{target_words} words target)")
            
            # Use the selected model to generate summary (non-streaming for complete response)
            response = llm_client.send_message(
                user_message=summary_prompt,
                temperature=0.3,  # Lower temperature for more focused summaries
                max_tokens=target_words * 2,  # Allow some buffer
            )

            if response and "response" in response:
                summary = response["response"].strip()
                word_count = len(summary.split())
                
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] Context summary generated ({word_count} words)")
                return summary
            else:
                print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to generate summary - no valid response")
                return None

        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Context summarization failed: {type(e).__name__}: {e}")
            return None

    def _select_model(self, model_preference: str):
        """
        Select the appropriate model based on user preference.

        @param model_preference User's model preference
        @return Selected LLM client or None
        """
        if model_preference == "decision" and self.decision_llm_client:
            return self.decision_llm_client
        elif model_preference == "main" and self.main_llm_client:
            return self.main_llm_client
        elif model_preference == "auto":
            # Prefer decision model if available (faster), fallback to main
            if self.decision_llm_client:
                return self.decision_llm_client
            elif self.main_llm_client:
                return self.main_llm_client
        
        # Fallback: use any available model
        return self.decision_llm_client or self.main_llm_client

    def _build_summary_prompt(self, context_text: str, target_words: int) -> str:
        """
        Build the summarization prompt for the LLM.

        @param context_text The context to summarize
        @param target_words Target word count for summary
        @return Formatted prompt string
        """
        return f"""You are a context summarization assistant. Your task is to create a concise summary of the conversation context provided below.

REQUIREMENTS:
- Create exactly 3-4 bullet points
- Target length: approximately {target_words} words total
- Focus on key topics, important decisions, and ongoing context
- Preserve critical information that would be needed for future responses
- Use clear, concise language
- Each bullet point should capture a distinct aspect of the conversation

CONTEXT TO SUMMARIZE:
{context_text}

Provide your summary as 3-4 bullet points below:"""

    def get_summary_stats(self, original_text: str, summary_text: str) -> dict:
        """
        Get statistics comparing original text to summary.

        @param original_text Original context text
        @param summary_text Generated summary text
        @return Dictionary with compression statistics
        """
        original_words = len(original_text.split()) if original_text else 0
        summary_words = len(summary_text.split()) if summary_text else 0
        
        compression_ratio = (
            (original_words - summary_words) / original_words * 100
            if original_words > 0 else 0
        )
        
        return {
            "original_words": original_words,
            "summary_words": summary_words,
            "compression_ratio": compression_ratio,
            "words_saved": original_words - summary_words
        }