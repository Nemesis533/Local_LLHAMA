"""
Helper functions for memory search functionality using vector similarity and keyword matching.

Contains all the components needed for hybrid memory search including:
- Embedding generation
- Keyword extraction and SQL building
- Query construction and parameter assembly
- Result processing and formatting
"""

import re
import requests

from .shared_logger import LogLevel

CLASS_PREFIX_MESSAGE = "[MemorySearchHelpers]"


def generate_query_embedding(query: str, ollama_host: str, ollama_embedding_model: str):
    """
    Generate embedding vector for a query using Ollama.

    @param query: Text query to embed
    @param ollama_host: Ollama server host URL
    @param ollama_embedding_model: Model name for embeddings
    @return: Embedding vector or None if generation fails
    """
    try:
        ollama_url = (
            ollama_host
            if ollama_host.startswith("http")
            else f"http://{ollama_host}"
        )
        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={"model": ollama_embedding_model, "prompt": query},
            timeout=30,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding")
        return embedding
    except Exception as e:
        print(
            f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Error generating embedding: {e}"
        )
        return None


def extract_keywords(query: str):
    """
    Extract alphanumeric keywords from a query for keyword matching.

    @param query: Text query to extract keywords from
    @return: List of lowercase keywords
    """
    keywords = re.findall(r"\w+", query.lower())
    print(
        f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Parsed keywords: {keywords}"
    )
    return keywords


def build_keyword_conditions(keywords: list):
    """
    Build SQL conditions and params for keyword matching.

    @param keywords: List of keywords to match
    @return: Tuple of (keyword_where_clause, keyword_params)
    """
    keyword_conditions = []
    keyword_params = []
    for keyword in keywords:
        keyword_conditions.append("LOWER(m.content) ILIKE %s")
        keyword_params.append(f"%{keyword}%")
    keyword_where = (
        " OR ".join(keyword_conditions) if keyword_conditions else "1=1"
    )
    return keyword_where, keyword_params


def build_filter_conditions(role: str, days_back: int):
    """
    Build SQL filter conditions for role and date filtering.

    @param role: Optional role filter ('user', 'assistant', or None)
    @param days_back: Optional days to look back (None = all time)
    @return: Tuple of (role_condition, role_params, date_condition, date_params)
    """
    # Build role filter condition
    if role:
        role_condition = "AND m.role = %s"
        role_params = [role, role]  # For both vector_search and keyword_search
    else:
        role_condition = ""
        role_params = []

    # Build date filter condition
    if days_back is not None:
        date_condition = "AND m.created_at >= CURRENT_DATE - INTERVAL '%s days'"
        date_params = [days_back, days_back]  # For both searches
    else:
        date_condition = ""
        date_params = []

    return role_condition, role_params, date_condition, date_params


def build_memory_search_query(
    keywords: list, keyword_where: str, role_condition: str, date_condition: str
) -> str:
    """
    Build the complete SQL query for hybrid memory search.

    Combines vector similarity search with keyword matching for better recall.

    @param keywords: List of keywords for similarity calculation
    @param keyword_where: WHERE clause for keyword matching
    @param role_condition: SQL condition for role filtering
    @param date_condition: SQL condition for date filtering
    @return: Complete SQL query string
    """
    return f"""
            WITH vector_search AS (
                SELECT m.id, m.content, m.role, m.created_at, m.conversation_id,
                    1 - (me.vector <=> %s::vector) AS similarity
                FROM messages m
                JOIN message_embeddings me ON m.id = me.message_id
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.user_id = %s
                {role_condition}
                {date_condition}
                AND (1 - (me.vector <=> %s::vector)) >= %s
            ),
            keyword_search AS (
                SELECT m.id, m.content, m.role, m.created_at, m.conversation_id,
                    0.5 + 0.1 * (
                        {" + ".join([f"(LOWER(m.content) LIKE %s)::int" for _ in keywords])}
                    ) AS similarity
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.user_id = %s
                {role_condition}
                {date_condition}
                AND ({keyword_where})
            ),
            combined AS (
                SELECT id, content, role, created_at, conversation_id, MAX(similarity) as similarity
                FROM (
                    SELECT * FROM vector_search
                    UNION ALL
                    SELECT * FROM keyword_search
                ) all_results
                GROUP BY id, content, role, created_at, conversation_id
            )
            SELECT 
                c.content as user_content,
                c.created_at,
                c.similarity,
                m_next.content as assistant_content,
                c.role as message_role
            FROM combined c
            LEFT JOIN LATERAL (
                SELECT m_next.content
                FROM messages m_next
                WHERE m_next.conversation_id = c.conversation_id
                AND m_next.created_at > c.created_at
                AND m_next.role = 'assistant'
                ORDER BY m_next.created_at ASC
                LIMIT 1
            ) m_next ON TRUE
            ORDER BY c.similarity DESC
            LIMIT %s
            """


def build_query_params(
    embedding: list,
    user_id: int,
    role_params: list,
    date_params: list,
    keyword_params: list,
    similarity_threshold: float,
    limit: int,
) -> list:
    """
    Build the complete parameter tuple for the SQL query.

    @param embedding: Query embedding vector
    @param user_id: User ID to filter by
    @param role_params: Role filter parameters
    @param date_params: Date filter parameters
    @param keyword_params: Keyword matching parameters
    @param similarity_threshold: Minimum similarity threshold for vector search
    @param limit: Maximum number of results
    @return: List of query parameters in correct order
    """
    return [
        embedding,  # vector_search embedding
        user_id,
        *role_params[:1],  # role for vector_search (if any)
        *date_params[:1],  # days_back for vector_search (if any)
        embedding,  # vector_search threshold comparison
        similarity_threshold,
        *keyword_params,  # keyword LIKE params for keyword_search similarity calculation
        user_id,
        *role_params[1:2],  # role for keyword_search (if any)
        *date_params[1:2],  # days_back for keyword_search (if any)
        *keyword_params,  # keyword LIKE params for WHERE clause
        limit,
    ]


def process_memory_results(results: list) -> list:
    """
    Process raw database results into structured memory objects.

    @param results: Raw database query results (list of tuples)
    @return: List of processed memory dictionaries
    """
    filtered_results = []
    for row in results or []:
        if len(row) < 3:
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Skipping malformed row: {row}"
            )
            continue
        filtered_results.append(
            {
                "user_message": row[0],
                "created_at": row[1],
                "similarity": float(row[2]),
                "assistant_response": (
                    row[3] if len(row) > 3 and row[3] else None
                ),
                "message_role": (
                    row[4] if len(row) > 4 else "user"
                ),  # Track what role the message was
            }
        )
    return filtered_results


def format_memory_response(memories: list, similarity_threshold: float) -> str:
    """
    Format memory search results into a natural language response.

    @param memories: List of memory dictionaries
    @param similarity_threshold: Threshold used for filtering
    @return: Formatted response string
    """
    if not memories:
        return f"No memories found with similarity above {similarity_threshold:.2f}."

    print(
        f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Found {len(memories)} memories above threshold {similarity_threshold:.2f}"
    )
    for idx, result in enumerate(memories, 1):
        print(
            f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}]   {idx}. Similarity: {result['similarity']:.4f} (Role: {result.get('message_role', 'unknown')})"
        )

    # Format results as a natural language string
    response_parts = [
        f"I found {len(memories)} relevant memory/memories from our past conversations:"
    ]

    for idx, result in enumerate(memories, 1):
        timestamp = (
            result["created_at"].strftime("%B %d, %Y")
            if hasattr(result["created_at"], "strftime")
            else str(result["created_at"])
        )
        similarity_pct = int(result["similarity"] * 100)
        msg_role = result.get("message_role", "user")

        response_parts.append(f"\n{idx}. (Similarity: {similarity_pct}%)")

        # Format differently based on whether it's a user or assistant message
        if msg_role == "assistant":
            response_parts.append(
                f"   I said: \"{result['user_message'][:300]}{'...' if len(result['user_message']) > 300 else ''}\""
            )
        else:
            response_parts.append(
                f"   You asked: \"{result['user_message']}\""
            )
            if result.get("assistant_response"):
                response_parts.append(
                    f"   I responded: \"{result['assistant_response'][:300]}{'...' if len(result.get('assistant_response', '')) > 300 else ''}\""
                )

        response_parts.append(f"   (from {timestamp})")

    return "\n".join(response_parts)
