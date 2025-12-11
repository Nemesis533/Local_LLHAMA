"""
Ollama Client Module

This module provides a refactored interface for interacting with Ollama LLM server:
- ollama_core: Main OllamaClient for LLM inference
- ollama_embeddings: EmbeddingClient for async vector embeddings
- ollama_context_builders: Context generation and prompt building

The module handles command parsing, response processing, and embedding generation
for language model interactions.

Usage:
    from local_llhama.ollama import OllamaClient, EmbeddingClient

    # Initialize the client
    ollama_client = OllamaClient(
        ha_client=ha_client,
        host="http://localhost:11434",
        model="qwen3-14b"
    )

    # Send a message
    response = ollama_client.send_message("Turn on the kitchen light")
"""

from .ollama_context_builders import ContextBuilder
from .ollama_core import OllamaClient
from .ollama_embeddings import EmbeddingClient

__all__ = ["OllamaClient", "EmbeddingClient", "ContextBuilder"]
