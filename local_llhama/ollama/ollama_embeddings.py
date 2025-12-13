"""
Ollama Embedding Client

This module provides non-blocking embedding generation using Ollama's
embedding models. Processes embeddings asynchronously and stores them
in PostgreSQL database.
"""

# === System Imports ===
import threading
from queue import Queue
from typing import List, Optional

import requests

# === Custom Imports ===
from ..shared_logger import LogLevel


class EmbeddingClient:
    """
    Non-blocking embedding client using embedding models via Ollama.

    Processes embedding requests asynchronously via queue to avoid blocking main thread.
    Automatically saves embeddings to PostgreSQL via callback.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "embeddinggemma",
        pg_client=None,
    ):
        """
        Initialize embedding client with Ollama connection.

        @param host Ollama server URL
        @param model Embedding model name (default: nomic-embed-text)
        @param pg_client PostgreSQLClient instance for storing embeddings
        """
        self.class_prefix_message = "[EmbeddingClient]"
        # Ensure host has http:// scheme for requests library
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        self.host = host.rstrip("/")
        self.model = model
        self.pg_client = pg_client

        # Queue for embedding requests (message_id, text, user_data)
        self.embedding_queue = Queue()

        # Results cache (message_id -> embedding)
        self.results_cache = {}

        self._cache_lock = threading.Lock()

        self.worker_thread = threading.Thread(
            target=self._embedding_worker, daemon=True
        )
        self.worker_thread.start()

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initialized with host={self.host}, model={self.model}"
        )

    def _embedding_worker(self) -> None:
        """
        Worker thread that processes embedding requests from queue.

        Runs continuously, pulls message batches from queue, inserts messages to DB,
        generates embeddings, saves to PostgreSQL, and stores in results cache.
        """
        while True:
            try:
                item = self.embedding_queue.get()

                if item is None:  # Shutdown signal
                    break

                batch = item

                try:

                    user_msg_id = self.pg_client.insert_message(
                        conversation_id=batch.get("conversation_id", 0),
                        role="user",
                        content=batch.get("user_message", ""),
                    )
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Inserted user message {user_msg_id}"
                    )

                    assistant_msg_id = self.pg_client.insert_message(
                        conversation_id=batch.get("conversation_id", 0),
                        role="assistant",
                        content=batch.get("assistant_response", ""),
                    )
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Inserted assistant response {assistant_msg_id}"
                    )

                    user_embedding = self._get_embedding_from_ollama(
                        batch.get("user_message", "")
                    )
                    assistant_embedding = self._get_embedding_from_ollama(
                        batch.get("assistant_response", "")
                    )

                    if user_embedding:
                        self.pg_client.insert_message_embedding(
                            user_msg_id, user_embedding
                        )
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Saved embedding for user message {user_msg_id}"
                        )

                    if assistant_embedding:
                        self.pg_client.insert_message_embedding(
                            assistant_msg_id, assistant_embedding
                        )
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Saved embedding for assistant response {assistant_msg_id}"
                        )

                    # Store in cache for retrieval if needed
                    with self._cache_lock:
                        self.results_cache[user_msg_id] = user_embedding
                        self.results_cache[assistant_msg_id] = assistant_embedding

                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error processing message batch: {str(e)}"
                    )

                finally:
                    self.embedding_queue.task_done()

            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Worker thread error: {str(e)}"
                )

    def _get_embedding_from_ollama(self, text: str) -> Optional[List[float]]:
        """
        Get embedding vector from Ollama server.

        @param text Text to embed
        @return List of floats representing embedding, or None if failed
        """
        try:
            response = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if embedding:
                    return embedding
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned status {response.status_code}"
                )

        except requests.exceptions.RequestException as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request failed: {str(e)}"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Embedding error: {str(e)}"
            )

        return None

    def queue_embedding(self, text: str) -> None:
        """
        Queue a message for embedding (non-blocking).

        Processing happens asynchronously in worker thread.

        @param message_id ID of the message being embedded
        @param text Text content to embed

        @deprecated Use queue_messages() instead for batch processing
        """
        # Legacy method - convert to batch format
        batch = {"user_message": text, "assistant_response": "", "conversation_id": 0}
        self.queue_messages(batch)

    def queue_messages(self, batch: dict) -> None:
        """
        Queue a batch of messages for DB insertion and embedding.

        Processes both user message and assistant response in single transaction.

        @param batch Dictionary with keys:
            - user_message: User's message text (str)
            - assistant_response: LLM's response text (str)
            - conversation_id: UUID of conversation (str, required)
        """
        self.embedding_queue.put(batch)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Queued message batch for processing"
        )

    def get_embedding(
        self, message_id: int, timeout: float = 30.0
    ) -> Optional[List[float]]:
        """
        Get embedding result (blocking with timeout).

        Waits for embedding to complete or timeout.

        @param message_id ID of the message to retrieve embedding for
        @param timeout Maximum seconds to wait for result
        @return Embedding vector or None if not found/timeout
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._cache_lock:
                if message_id in self.results_cache:
                    embedding = self.results_cache[message_id]
                    # Clean up cache
                    del self.results_cache[message_id]
                    return embedding

            time.sleep(0.1)

        print(
            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Timeout waiting for embedding {message_id}"
        )
        return None

    def shutdown(self) -> None:
        """
        Gracefully shutdown embedding worker thread.

        Waits for queue to empty before shutting down.
        """
        self.embedding_queue.join()  # Wait for all pending items
        self.embedding_queue.put(None)  # Shutdown signal
        self.worker_thread.join(timeout=5)

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Shutdown complete")
