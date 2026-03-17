"""
Model Registry - Central tracking system for all AI model states

This module provides a singleton registry to track the loading/unloading state
of all AI models (LLMs, embedding models, diffusion pipelines) to prevent
race conditions and coordinate resource usage across components.
"""

import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, Optional

from .shared_logger import LogLevel


class ModelState(Enum):
    """Possible states for a model."""

    UNLOADED = "unloaded"  # Not in memory
    LOADING = "loading"  # Currently being loaded
    LOADED = "loaded"  # Fully loaded and ready
    UNLOADING = "unloading"  # Currently being unloaded
    ERROR = "error"  # Failed to load/unload


class ModelType(Enum):
    """Types of models managed by the registry."""

    LLM = "llm"  # Text generation model (Ollama)
    EMBEDDING = "embedding"  # Embedding model (Ollama)
    DIFFUSION = "diffusion"  # Image generation pipeline (SD3.5)
    VLM = "vlm"  # Vision-language model


class ModelInfo:
    """Information about a registered model."""

    def __init__(
        self,
        name: str,
        model_type: ModelType,
        host: Optional[str] = None,
        description: str = "",
    ):
        self.name = name
        self.model_type = model_type
        self.host = host
        self.description = description
        self.state = ModelState.UNLOADED
        self.last_state_change = datetime.now(timezone.utc)
        self.last_used = None
        self.lock = threading.Lock()
        self.load_count = 0
        self.error_message = None

    def update_state(self, new_state: ModelState, error_msg: Optional[str] = None):
        """Thread-safe state update."""
        with self.lock:
            self.state = new_state
            self.last_state_change = datetime.now(timezone.utc)
            self.error_message = error_msg

    def mark_used(self):
        """Mark the model as recently used."""
        with self.lock:
            self.last_used = datetime.now(timezone.utc)

    def can_use(self) -> bool:
        """Check if model is ready to use."""
        with self.lock:
            return self.state == ModelState.LOADED

    def is_transitioning(self) -> bool:
        """Check if model is currently loading or unloading."""
        with self.lock:
            return self.state in (ModelState.LOADING, ModelState.UNLOADING)


class ModelRegistry:
    """
    Singleton registry for tracking all AI model states.

    Provides thread-safe operations for:
    - Registering models
    - Tracking load/unload state
    - Preventing concurrent operations
    - Coordinating resource usage
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.models: Dict[str, ModelInfo] = {}
        self.global_lock = threading.RLock()
        self.log_prefix = "[ModelRegistry]"

        # Callbacks for model state changes
        self.state_change_callbacks = []

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Model registry initialized")

    def register_model(
        self,
        name: str,
        model_type: ModelType,
        host: Optional[str] = None,
        description: str = "",
        initial_state: ModelState = ModelState.UNLOADED,
    ) -> ModelInfo:
        """
        Register a model with the registry.

        @param name Unique identifier for the model
        @param model_type Type of model (LLM, embedding, diffusion, etc.)
        @param host Optional host URL for the model
        @param description Human-readable description
        @param initial_state Initial state of the model
        @return ModelInfo object for the registered model
        """
        with self.global_lock:
            if name in self.models:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] "
                    f"Model already registered: {name}"
                )
                return self.models[name]

            model_info = ModelInfo(name, model_type, host, description)
            model_info.state = initial_state
            self.models[name] = model_info

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] "
                f"Registered model: {name} (type={model_type.value}, state={initial_state.value})"
            )

            return model_info

    def get_model(self, name: str) -> Optional[ModelInfo]:
        """Get model info by name."""
        with self.global_lock:
            return self.models.get(name)

    def set_model_state(
        self, name: str, state: ModelState, error_msg: Optional[str] = None
    ) -> bool:
        """
        Update model state.

        @param name Model identifier
        @param state New state
        @param error_msg Optional error message if state is ERROR
        @return True if successful, False if model not found
        """
        model = self.get_model(name)
        if not model:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                f"Cannot set state for unregistered model: {name}"
            )
            return False

        old_state = model.state
        model.update_state(state, error_msg)

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Model {name}: {old_state.value} → {state.value}"
        )

        # Trigger callbacks
        self._trigger_state_change_callbacks(name, old_state, state)

        return True

    def mark_model_used(self, name: str):
        """Mark a model as recently used."""
        model = self.get_model(name)
        if model:
            model.mark_used()

    def can_use_model(self, name: str) -> bool:
        """
        Check if a model is loaded and ready to use.

        @param name Model identifier
        @return True if model is in LOADED state, False otherwise
        """
        model = self.get_model(name)
        if not model:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                f"Cannot check state for unregistered model: {name}"
            )
            return False
        return model.can_use()

    def wait_for_model_ready(
        self, name: str, timeout: float = 120.0, check_interval: float = 0.5
    ) -> bool:
        """
        Wait for a model to be ready (LOADED state).

        @param name Model identifier
        @param timeout Maximum time to wait in seconds
        @param check_interval Time between state checks in seconds
        @return True if model became ready, False if timeout or error
        """
        model = self.get_model(name)
        if not model:
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            if model.can_use():
                return True

            if model.state == ModelState.ERROR:
                print(
                    f"{self.log_prefix} [{LogLevel.ERROR.name}] "
                    f"Model {name} failed to load: {model.error_message}"
                )
                return False

            time.sleep(check_interval)

        print(
            f"{self.log_prefix} [{LogLevel.WARNING.name}] "
            f"Timeout waiting for model {name} to be ready (current state: {model.state.value})"
        )
        return False

    def acquire_loading_lock(self, name: str, timeout: float = 300.0) -> bool:
        """
        Try to acquire exclusive loading lock for a model.

        Transitions model from UNLOADED to LOADING if not already transitioning.

        @param name Model identifier
        @param timeout Maximum time to wait for lock
        @return True if lock acquired, False otherwise
        """
        model = self.get_model(name)
        if not model:
            return False

        with model.lock:
            if model.is_transitioning():
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] "
                    f"Model {name} is already transitioning (state={model.state.value})"
                )
                return False

            if model.state == ModelState.LOADED:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] "
                    f"Model {name} is already loaded"
                )
                return False

            # Transition to LOADING
            model.update_state(ModelState.LOADING)
            model.load_count += 1

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] "
                f"Acquired loading lock for {name} (load count: {model.load_count})"
            )

            return True

    def acquire_unloading_lock(self, name: str) -> bool:
        """
        Try to acquire exclusive unloading lock for a model.

        Transitions model from LOADED to UNLOADING if not already transitioning.

        @param name Model identifier
        @return True if lock acquired, False otherwise
        """
        model = self.get_model(name)
        if not model:
            return False

        with model.lock:
            if model.is_transitioning():
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] "
                    f"Model {name} is already transitioning (state={model.state.value})"
                )
                return False

            if model.state == ModelState.UNLOADED:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] "
                    f"Model {name} is already unloaded"
                )
                return False

            # Transition to UNLOADING
            model.update_state(ModelState.UNLOADING)

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] "
                f"Acquired unloading lock for {name}"
            )

            return True

    def get_all_models_by_type(self, model_type: ModelType) -> list:
        """Get all models of a specific type."""
        with self.global_lock:
            return [
                model
                for model in self.models.values()
                if model.model_type == model_type
            ]

    def get_loaded_models(self) -> list:
        """Get all currently loaded models."""
        with self.global_lock:
            return [
                model
                for model in self.models.values()
                if model.state == ModelState.LOADED
            ]

    def has_loaded_model_of_type(self, model_type: ModelType) -> bool:
        """Check if any model of the given type is currently loaded."""
        with self.global_lock:
            return any(
                model.state == ModelState.LOADED and model.model_type == model_type
                for model in self.models.values()
            )

    def add_state_change_callback(self, callback: Callable):
        """
        Add a callback to be called when model state changes.

        Callback signature: callback(model_name: str, old_state: ModelState, new_state: ModelState)
        """
        with self.global_lock:
            self.state_change_callbacks.append(callback)

    def _trigger_state_change_callbacks(
        self, model_name: str, old_state: ModelState, new_state: ModelState
    ):
        """Trigger all registered state change callbacks."""
        for callback in self.state_change_callbacks:
            try:
                callback(model_name, old_state, new_state)
            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                    f"State change callback failed: {e}"
                )

    def get_status_summary(self) -> dict:
        """Get a summary of all models and their states."""
        with self.global_lock:
            summary = {}
            for name, model in self.models.items():
                summary[name] = {
                    "type": model.model_type.value,
                    "state": model.state.value,
                    "description": model.description,
                    "last_used": (
                        model.last_used.isoformat() if model.last_used else None
                    ),
                    "last_state_change": model.last_state_change.isoformat(),
                    "load_count": model.load_count,
                    "error": model.error_message,
                }
            return summary

    def print_status(self):
        """Print current status of all models."""
        summary = self.get_status_summary()
        print(
            f"\n{self.log_prefix} [{LogLevel.INFO.name}] === Model Status Summary ==="
        )
        for name, info in summary.items():
            state_indicator = {
                "loaded": "✓",
                "unloaded": "○",
                "loading": "↻",
                "unloading": "↓",
                "error": "✗",
            }.get(info["state"], "?")

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}]   {state_indicator} {name} "
                f"({info['type']}) - {info['state']}"
            )
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] ============================\n"
        )


# Global singleton instance
_registry_instance = None


def get_model_registry() -> ModelRegistry:
    """Get the global model registry singleton."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance
