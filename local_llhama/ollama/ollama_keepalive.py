"""
Ollama Model Keepalive Manager

This module manages keepalive pings to Ollama models to keep them loaded in memory.
"""

import threading
import time

import requests

from ..shared_logger import LogLevel


class ModelKeepaliveManager:
    """
    Manages keepalive pings to Ollama models to prevent them from being unloaded.
    
    Runs a background thread that periodically sends minimal requests to registered
    models (both text generation and embedding models) to keep them in memory.
    """

    def __init__(
        self,
        host: str,
        interval: int = 180,
        enabled: bool = True,
        log_prefix: str = "[ModelKeepaliveManager]",
    ):
        """
        Initialize the keepalive manager.

        @param host Ollama server URL
        @param interval Seconds between keepalive pings
        @param enabled Whether keepalive is enabled
        @param log_prefix Prefix for log messages
        """
        self.host = host.rstrip("/")
        self.interval = interval
        self.enabled = enabled
        self.log_prefix = log_prefix
        
        self.models = []
        self.running = False
        self.thread = None

    def register_model(self, model_name: str, model_type: str = "text", description: str = ""):
        """
        Register a model for keepalive monitoring.

        @param model_name Name of the model
        @param model_type Type of model ("text" or "embedding")
        @param description Optional description of the model's purpose
        """
        # Check if model is already registered
        for model in self.models:
            if model["name"] == model_name and model["type"] == model_type:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Model already registered: {model_name}"
                )
                return

        self.models.append({
            "name": model_name,
            "type": model_type,
            "description": description
        })
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Registered model for keepalive: {model_name} ({model_type})"
        )

    def unregister_model(self, model_name: str, model_type: str = None):
        """
        Unregister a model from keepalive monitoring.

        @param model_name Name of the model to unregister
        @param model_type Optional type filter
        """
        original_count = len(self.models)
        self.models = [
            m for m in self.models
            if not (m["name"] == model_name and (model_type is None or m["type"] == model_type))
        ]
        
        if len(self.models) < original_count:
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Unregistered model: {model_name}"
            )

    def start(self):
        """Start the keepalive background thread."""
        if not self.enabled:
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Keepalive is disabled, not starting"
            )
            return

        if self.running:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Keepalive already running"
            )
            return

        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Model keepalive started (interval: {self.interval}s, {len(self.models)} models)"
        )

    def stop(self):
        """Stop the keepalive thread."""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Model keepalive stopped"
        )

    def _worker(self):
        """Background worker that sends keepalive requests to models."""
        while self.running:
            try:
                # Wait for the interval
                for _ in range(self.interval):
                    if not self.running:
                        return
                    time.sleep(1)

                # Send keepalive to all registered models
                for model_info in self.models:
                    if not self.running:
                        return
                    
                    is_embedding = model_info["type"] == "embedding"
                    self._send_keepalive(
                        model_info["name"],
                        is_embedding=is_embedding,
                        description=model_info["description"]
                    )

            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Keepalive error: {type(e).__name__}: {e}"
                )

    def _send_keepalive(self, model_name: str, is_embedding: bool = False, description: str = ""):
        """
        Send a minimal request to keep a model loaded.

        @param model_name Name of the model to ping
        @param is_embedding Whether this is an embedding model
        @param description Optional description of the model's purpose
        """
        try:
            url = f"{self.host}/api/{'embed' if is_embedding else 'generate'}"

            if is_embedding:
                # For embedding models, embed a single character
                payload = {"model": model_name, "input": "1"}
            else:
                # For LLM models, generate a minimal response
                payload = {
                    "model": model_name,
                    "prompt": "Reply only with the number 1, nothing else.",
                    "stream": False,
                    "options": {"num_predict": 2, "temperature": 0},
                }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                desc_suffix = f" ({description})" if description else ""
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Keepalive ping successful: {model_name}{desc_suffix}"
                )
            else:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Keepalive ping failed for {model_name}: HTTP {response.status_code}"
                )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Keepalive failed for {model_name}: {type(e).__name__}: {e}"
            )
