"""
@file memory_service.py
@brief Service for semantic memory search in conversation history.

This service handles searching through conversation history using
embeddings and hybrid keyword/semantic search.
"""

from local_llhama.utils import memory_search_helpers as mem_helpers
from local_llhama.shared_logger import LogLevel


CLASS_PREFIX_MESSAGE = "[MemoryService]"


class MemoryService:
    """Service for semantic memory search."""

    def __init__(
        self,
        pg_client,
        ollama_host: str,
        ollama_embedding_model: str,
        similarity_threshold: float = 0.7,
    ):
        """
        Initialize the memory service.

        @param pg_client PostgreSQL client for database queries
        @param ollama_host Ollama server host URL
        @param ollama_embedding_model Name of the embedding model
        @param similarity_threshold Minimum similarity score for matches
        """
        self.pg_client = pg_client
        self.ollama_host = ollama_host
        self.ollama_embedding_model = ollama_embedding_model
        self.similarity_threshold = similarity_threshold

    def find_in_memory(self, query, user_id, limit=3, role=None, days_back=None):
        """
        @brief Search for semantically similar messages in conversation history.

        Uses hybrid search combining:
        - Semantic similarity via embeddings (cosine distance)
        - Keyword matching for specific terms
        - Optional filtering by role and date range

        @param query Search query string
        @param user_id User ID to search within
        @param limit Maximum number of results to return
        @param role Optional role filter ('user' or 'assistant')
        @param days_back Optional number of days to search back
        @return Formatted string with matching messages or error message
        """
        # Generate embedding from query
        embedding = mem_helpers.generate_query_embedding(
            query, self.ollama_host, self.ollama_embedding_model
        )
        if not embedding:
            return "Could not generate embedding for search."

        try:
            # Extract keywords for hybrid search
            keywords = mem_helpers.extract_keywords(query)
            keyword_where, keyword_params = mem_helpers.build_keyword_conditions(
                keywords
            )

            # Build filter conditions
            role_condition, role_params, date_condition, date_params = (
                mem_helpers.build_filter_conditions(role, days_back)
            )

            # Build SQL query
            sql_query = mem_helpers.build_memory_search_query(
                keywords, keyword_where, role_condition, date_condition
            )

            # Build parameters
            params_tuple = mem_helpers.build_query_params(
                embedding,
                user_id,
                role_params,
                date_params,
                keyword_params,
                self.similarity_threshold,
                limit,
            )

            # Debug output
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] SQL placeholders: {sql_query.count('%s')}, Params length: {len(params_tuple)}"
            )

            # Execute query
            results = self.pg_client.execute_query(sql_query, tuple(params_tuple))

            # Process and format results
            memories = mem_helpers.process_memory_results(results)
            return mem_helpers.format_memory_response(
                memories, self.similarity_threshold
            )

        except Exception as e:
            import traceback

            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Error finding similar messages: {e}"
            )
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Traceback:\n{traceback.format_exc()}"
            )
            return "Could not find previous messages for this topic."
