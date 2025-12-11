"""
@file PostgreSQL_Client.py
@brief PostgreSQL connection manager with sync and async support.

This module provides a client for connecting to PostgreSQL with connection pooling,
parametric queries for security, and support for both synchronous and asynchronous operations.
"""

import os
from contextlib import asynccontextmanager, contextmanager
from typing import Dict, List, Optional, Tuple

import asyncpg
from psycopg2 import extras, pool

from .error_handler import ErrorHandler
from .Shared_Logger import LogLevel


class PostgreSQLClient:
    """
    @brief Thread-safe PostgreSQL client with sync and async support.

    Handles connection pooling, parametric queries, and transaction management
    for both synchronous and asynchronous database operations.
    """

    def __init__(self):
        """
        @brief Initialize PostgreSQL connection pool from environment variables.

        Reads PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE from .env.
        Creates both sync (psycopg2) and async (asyncpg) connection pools.

        @raises ValueError If PG_PASSWORD is not set in environment.
        """
        self.host = os.getenv("PG_HOST", "localhost")
        self.port = int(os.getenv("PG_PORT", 5432))
        self.user = os.getenv("PG_USER", "llhama_usr")
        self.password = os.getenv("PG_PASSWORD")
        self.database = os.getenv("PG_DATABASE", "llhama")
        self.class_prefix_message = "[PostgreSQL Client]"

        if not self.password:
            raise ValueError("PG_PASSWORD environment variable is required")

        # Sync connection pool
        self.sync_pool = self._create_sync_pool()

        # Async pool (created lazily)
        self._async_pool = None
        self._loop = None

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initialized with host={self.host}:{self.port}, db={self.database}"
        )

    def _create_sync_pool(self) -> pool.SimpleConnectionPool:
        """
        @brief Create psycopg2 connection pool for sync operations.

        @return SimpleConnectionPool instance with min 2, max 10 connections.
        @raises Exception If connection pool creation fails.
        """
        try:
            pg_pool = pool.SimpleConnectionPool(
                minconn=2,
                maxconn=10,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Sync connection pool created"
            )
            return pg_pool
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to create sync pool: {str(e)}"
            )
            raise

    async def _get_async_pool(self) -> asyncpg.Pool:
        """
        @brief Get or create async connection pool (lazy initialization).

        @return asyncpg.Pool instance with min 2, max 10 connections.
        @raises Exception If async pool creation fails.
        """
        if self._async_pool is None:
            try:
                self._async_pool = await asyncpg.create_pool(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    min_size=2,
                    max_size=10,
                )
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Async connection pool created"
                )
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to create async pool: {str(e)}"
                )
                raise
        return self._async_pool

    @contextmanager
    def get_sync_connection(self):
        """
        @brief Context manager for acquiring and releasing sync connections.

        Automatically returns connection to pool after use.
        """
        conn = self.sync_pool.getconn()
        try:
            yield conn
        finally:
            self.sync_pool.putconn(conn)

    @asynccontextmanager
    async def get_async_connection(self):
        """
        @brief Context manager for acquiring and releasing async connections.

        Automatically returns connection to pool after use.
        """
        pool = await self._get_async_pool()
        async with pool.acquire() as conn:
            yield conn

    # ============ SYNC METHODS ============

    @ErrorHandler.handle_with_log(
        "[PostgreSQL Client]", context="Query execution", reraise=True
    )
    def execute_query(self, query: str, params: Tuple = ()) -> List[Tuple]:
        """
        @brief Execute SELECT query and return all results.

        @param query SQL query string with %s placeholders for parameters.
        @param params Tuple of parameters for parametric query (prevents SQL injection).
        @return List of result tuples.
        @raises Exception If query execution fails.
        """
        with self.get_sync_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    @ErrorHandler.handle_with_log(
        "[PostgreSQL Client]", context="Query execution (dict)", reraise=True
    )
    def execute_query_dict(self, query: str, params: Tuple = ()) -> List[Dict]:
        """
        @brief Execute SELECT query and return results as dictionaries.

        @param query SQL query with %s placeholders for parameters.
        @param params Tuple of parameters for parametric query.
        @return List of result dictionaries mapped by column name.
        @raises Exception If query execution fails.
        """
        with self.get_sync_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchall()

    @ErrorHandler.handle_with_log(
        "[PostgreSQL Client]", context="Query execution (single)", reraise=True
    )
    def execute_one(self, query: str, params: Tuple = ()) -> Optional[Tuple]:
        """
        @brief Execute query and return single result row.

        @param query SQL query with %s placeholders for parameters.
        @param params Tuple of parameters for parametric query.
        @return Single result tuple or None if no results.
        @raises Exception If query execution fails.
        """
        with self.get_sync_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def execute_one_dict(self, query: str, params: Tuple = ()) -> Optional[Dict]:
        """
        @brief Execute query and return single result row as dictionary.

        @param query SQL query with %s placeholders for parameters.
        @param params Tuple of parameters for parametric query.
        @return Single result dictionary or None if no results.
        @raises Exception If query execution fails.
        """
        try:
            with self.get_sync_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    return cur.fetchone()
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Query execution failed: {str(e)}"
            )
            raise

    def execute_write(self, query: str, params: Tuple = ()) -> int:
        """
        @brief Execute INSERT/UPDATE/DELETE query with automatic commit.

        @param query SQL query with %s placeholders for parameters.
        @param params Tuple of parameters for parametric query.
        @return Number of rows affected.
        @raises Exception If write operation fails (auto-rollback on error).
        """
        try:
            with self.get_sync_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount
        except Exception as e:
            conn.rollback()
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Write operation failed: {str(e)}"
            )
            raise

    def execute_write_returning(
        self, query: str, params: Tuple = ()
    ) -> Optional[Tuple]:
        """
        @brief Execute INSERT with RETURNING clause and get inserted row.

        @param query SQL query with RETURNING clause and %s placeholders.
        @param params Tuple of parameters for parametric query.
        @return Inserted row as tuple.
        @raises Exception If write operation fails (auto-rollback on error).
        """
        try:
            with self.get_sync_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.fetchone()
        except Exception as e:
            conn.rollback()
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Write operation failed: {str(e)}"
            )
            raise

    def execute_write_returning_dict(
        self, query: str, params: Tuple = ()
    ) -> Optional[Dict]:
        """
        @brief Execute INSERT with RETURNING clause and get inserted row as dictionary.

        @param query SQL query with RETURNING clause and %s placeholders.
        @param params Tuple of parameters for parametric query.
        @return Inserted row as dictionary.
        @raises Exception If write operation fails (auto-rollback on error).
        """
        try:
            with self.get_sync_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.fetchone()
        except Exception as e:
            conn.rollback()
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Write operation failed: {str(e)}"
            )
            raise

    def execute_bulk(self, query: str, params_list: List[Tuple]) -> int:
        """
        @brief Execute multiple write operations in single transaction.

        All operations commit together or rollback together on error.

        @param query SQL query with %s placeholders for parameters.
        @param params_list List of parameter tuples for each operation.
        @return Total rows affected across all operations.
        @raises Exception If any operation fails (auto-rollback of entire transaction).
        """
        try:
            with self.get_sync_connection() as conn:
                with conn.cursor() as cur:
                    total_rows = 0
                    for params in params_list:
                        cur.execute(query, params)
                        total_rows += cur.rowcount
                    conn.commit()
                    return total_rows
        except Exception as e:
            conn.rollback()
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Bulk operation failed: {str(e)}"
            )
            raise

    # ============ ASYNC METHODS ============

    async def execute_query_async(self, query: str, params: Tuple = ()) -> List[Tuple]:
        """
        @brief Async version of execute_query for concurrent SELECT operations.

        @param query SQL query with $1, $2, etc. placeholders (asyncpg format).
        @param params Tuple of parameters for parametric query.
        @return List of result tuples.
        @raises Exception If query execution fails.
        """
        try:
            async with await self.get_async_connection() as conn:
                return await conn.fetch(query, *params)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Async query failed: {str(e)}"
            )
            raise

    async def execute_one_async(
        self, query: str, params: Tuple = ()
    ) -> Optional[Tuple]:
        """
        @brief Async version of execute_one for single row SELECT.

        @param query SQL query with $1, $2, etc. placeholders (asyncpg format).
        @param params Tuple of parameters for parametric query.
        @return Single result tuple or None if no results.
        @raises Exception If query execution fails.
        """
        try:
            async with await self.get_async_connection() as conn:
                return await conn.fetchrow(query, *params)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Async query failed: {str(e)}"
            )
            raise

    async def execute_write_async(self, query: str, params: Tuple = ()) -> str:
        """
        @brief Async INSERT/UPDATE/DELETE operation.

        @param query SQL query with $1, $2, etc. placeholders (asyncpg format).
        @param params Tuple of parameters for parametric query.
        @return Command result string (e.g., 'UPDATE 5').
        @raises Exception If write operation fails.
        """
        try:
            async with await self.get_async_connection() as conn:
                return await conn.execute(query, *params)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Async write failed: {str(e)}"
            )
            raise

    async def execute_write_returning_async(
        self, query: str, params: Tuple = ()
    ) -> Optional[Tuple]:
        """
        @brief Async version of execute_write_returning for INSERT...RETURNING.

        @param query SQL query with RETURNING clause and $1, $2, etc. placeholders.
        @param params Tuple of parameters for parametric query.
        @return Inserted row as tuple.
        @raises Exception If write operation fails.
        """
        try:
            async with await self.get_async_connection() as conn:
                return await conn.fetchrow(query, *params)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Async write failed: {str(e)}"
            )
            raise

    async def execute_bulk_async(self, query: str, params_list: List[Tuple]) -> int:
        """
        @brief Async bulk insert/update in single transaction.

        All operations commit together or rollback together on error.

        @param query SQL query with $1, $2, etc. placeholders (asyncpg format).
        @param params_list List of parameter tuples for each operation.
        @return Number of operations executed.
        @raises Exception If any operation fails (auto-rollback of entire transaction).
        """
        try:
            async with await self.get_async_connection() as conn:
                async with conn.transaction():
                    for params in params_list:
                        await conn.execute(query, *params)
                    return len(params_list)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Async bulk operation failed: {str(e)}"
            )
            raise

    # ============ SPECIALIZED METHODS ============

    def insert_message(self, conversation_id: str, role: str, content: str) -> str:
        """
        @brief Insert a raw message into messages table and return its ID.

        @param conversation_id UUID of the conversation.
        @param role Message role ('user', 'assistant', 'system').
        @param content Message content text.
        @return UUID of the newly inserted message.
        @raises Exception If insertion fails.
        """
        query = "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s) RETURNING id"
        result = self.execute_write_returning(query, (conversation_id, role, content))
        return result[0] if result else None

    def insert_message_embedding(self, message_id: int, vector: List[float]) -> None:
        """
        @brief Store embedding vector for a message.

        @param message_id ID of the message to embed.
        @param vector Embedding vector as list of floats.
        @raises Exception If insertion fails.
        """
        query = "INSERT INTO message_embeddings (message_id, vector) VALUES (%s, %s)"
        self.execute_write(query, (message_id, vector))

    def create_conversation(self, user_id: int, title: Optional[str] = None) -> str:
        """
        @brief Create a new conversation for a user.

        @param user_id ID of the user starting the conversation.
        @param title Optional title for the conversation.
        @return UUID of the newly created conversation.
        @raises Exception If insertion fails.
        """
        query = (
            "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id"
        )
        result = self.execute_write_returning(query, (user_id, title))
        return result[0] if result else None

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """
        @brief Get conversation details by ID.

        @param conversation_id UUID of the conversation.
        @return Dictionary with conversation data or None if not found.
        @raises Exception If query fails.
        """
        query = "SELECT id, user_id, title, created_at FROM conversations WHERE id = %s"
        return self.execute_one_dict(query, (conversation_id,))

    def list_user_conversations(self, user_id: int, limit: int = 50) -> List[Dict]:
        """
        @brief List all conversations for a user.

        @param user_id ID of the user.
        @param limit Maximum number of conversations to return (default 50).
        @return List of conversation dictionaries ordered by most recent first.
        @raises Exception If query fails.
        """
        query = "SELECT id, user_id, title, created_at FROM conversations WHERE user_id = %s ORDER BY created_at DESC LIMIT %s"
        return self.execute_query_dict(query, (user_id, limit))

    async def create_conversation_async(
        self, user_id: int, title: Optional[str] = None
    ) -> str:
        """
        @brief Async version of create_conversation.

        @param user_id ID of the user starting the conversation.
        @param title Optional title for the conversation.
        @return UUID of the newly created conversation.
        @raises Exception If insertion fails.
        """
        query = (
            "INSERT INTO conversations (user_id, title) VALUES ($1, $2) RETURNING id"
        )
        result = await self.execute_write_returning_async(query, (user_id, title))
        return (
            result["id"] if isinstance(result, dict) else result[0] if result else None
        )

    async def get_conversation_async(self, conversation_id: str) -> Optional[Dict]:
        """
        @brief Async version of get_conversation.

        @param conversation_id UUID of the conversation.
        @return Dictionary with conversation data or None if not found.
        @raises Exception If query fails.
        """
        query = "SELECT id, user_id, title, created_at FROM conversations WHERE id = $1"
        results = await self.execute_query_async(query, (conversation_id,))
        return results[0] if results else None

    async def list_user_conversations_async(
        self, user_id: int, limit: int = 50
    ) -> List[Dict]:
        """
        @brief Async version of list_user_conversations.

        @param user_id ID of the user.
        @param limit Maximum number of conversations to return (default 50).
        @return List of conversation dictionaries ordered by most recent first.
        @raises Exception If query fails.
        """
        query = "SELECT id, user_id, title, created_at FROM conversations WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2"
        return await self.execute_query_async(query, (user_id, limit))

    async def insert_message_async(
        self, conversation_id: str, role: str, content: str
    ) -> str:
        """
        @brief Async version of insert_message.

        @param conversation_id UUID of the conversation.
        @param role Message role ('user', 'assistant', 'system').
        @param content Message content text.
        @return UUID of the newly inserted message.
        @raises Exception If insertion fails.
        """
        query = "INSERT INTO messages (conversation_id, role, content) VALUES ($1, $2, $3) RETURNING id"
        result = await self.execute_write_returning_async(
            query, (conversation_id, role, content)
        )
        return (
            result["id"] if isinstance(result, dict) else result[0] if result else None
        )

    async def insert_message_embedding_async(
        self, message_id: int, vector: List[float]
    ) -> None:
        """
        @brief Async version of insert_message_embedding.

        @param message_id ID of the message to embed.
        @param vector Embedding vector as list of floats.
        @raises Exception If insertion fails.
        """
        query = "INSERT INTO message_embeddings (message_id, vector) VALUES ($1, $2)"
        await self.execute_write_async(query, (message_id, vector))

    def close(self):
        """
        @brief Close all sync connections in the pool.

        Should be called on application shutdown.
        """
        if self.sync_pool:
            self.sync_pool.closeall()
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Sync pool closed"
            )

    async def close_async(self):
        """
        @brief Close all async connections in the pool.

        Should be called on application shutdown.
        """
        if self._async_pool:
            await self._async_pool.close()
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Async pool closed"
            )
