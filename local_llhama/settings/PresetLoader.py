"""
@file PresetLoader.py
@brief Manages configuration presets for different system capabilities and language requirements.

This module provides functionality to load, list, and apply preset configurations that
optimize the system for different hardware setups (single/multi-GPU) and language support.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from ..shared_logger import LogLevel


class PresetLoader:
    """
    @class PresetLoader
    @brief Loads and manages configuration presets for the LLHAMA system.

    Presets define complete configuration sets optimized for specific use cases:
    - Multi-lingual multi-GPU: High-performance multilingual with multiple GPUs
    - Multi-lingual single-GPU: Balanced multilingual for single GPU
    - English-only large: High-quality English with large models
    - English-only small: Lightweight English for lower-end systems

    Each preset includes:
    - LLM model selection (GPT-OSS 20B or Qwen 14B)
    - Whisper model size (turbo, medium, small)
    - TTS language models
    - Other system settings
    """

    def __init__(self, base_path: str):
        """
        @brief Initialize the preset loader.
        @param base_path Base path of the application (the local_llhama directory itself).
        """
        self.class_prefix_message = "[PresetLoader]"
        self.base_path = Path(base_path)
        self.presets_dir = self.base_path / "settings" / "presets"

        # Ensure presets directory exists
        if not self.presets_dir.exists():
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Presets directory not found at {self.presets_dir}"
            )
            self.presets_dir.mkdir(parents=True, exist_ok=True)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Created presets directory"
            )

    def list_presets(self) -> List[Dict]:
        """
        @brief List all available presets with their metadata.
        @return List of dictionaries containing preset information (name, description, requirements).
        """
        presets = []

        if not self.presets_dir.exists():
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No presets directory found"
            )
            return presets

        for preset_file in self.presets_dir.glob("*.json"):
            try:
                with open(preset_file, "r", encoding="utf-8") as f:
                    preset_data = json.load(f)
                    presets.append(
                        {
                            "id": preset_file.stem,
                            "name": preset_data.get("name", preset_file.stem),
                            "description": preset_data.get("description", ""),
                            "requirements": preset_data.get("requirements", {}),
                            "file": str(preset_file),
                        }
                    )
            except (json.JSONDecodeError, IOError) as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to load preset {preset_file.name}: {e}"
                )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Found {len(presets)} available presets"
        )
        return presets

    def load_preset(self, preset_id: str) -> Optional[Dict]:
        """
        @brief Load a specific preset by its ID.
        @param preset_id The preset identifier (filename without extension).
        @return Dictionary containing the full preset data, or None if not found.
        """
        preset_file = self.presets_dir / f"{preset_id}.json"

        if not preset_file.exists():
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Preset '{preset_id}' not found at {preset_file}"
            )
            return None

        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                preset_data = json.load(f)
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded preset '{preset_data.get('name', preset_id)}'"
                )
                return preset_data
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to load preset '{preset_id}': {e}"
            )
            return None

    def apply_preset(self, preset_id: str, target_settings_file: str) -> bool:
        """
        @brief Apply a preset by merging it with existing settings and saving to file.
        @param preset_id The preset identifier to apply.
        @param target_settings_file Path to the settings file to update.
        @return True if successful, False otherwise.
        """
        # Load the preset
        preset_data = self.load_preset(preset_id)
        if not preset_data:
            return False

        preset_settings = preset_data.get("settings", {})
        if not preset_settings:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Preset '{preset_id}' has no settings to apply"
            )
            return False

        # Load existing settings
        existing_settings = {}
        if os.path.exists(target_settings_file):
            try:
                with open(target_settings_file, "r", encoding="utf-8") as f:
                    existing_settings = json.load(f)
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded existing settings from {target_settings_file}"
                )
            except (json.JSONDecodeError, IOError) as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not load existing settings: {e}"
                )

        # Merge preset settings with existing settings
        # Preset settings take precedence
        merged_settings = self._merge_settings(existing_settings, preset_settings)

        # Store the active preset ID for UI highlighting
        if "_system" not in merged_settings:
            merged_settings["_system"] = {}
        merged_settings["_system"]["active_preset"] = {
            "value": preset_id,
            "type": "str",
        }

        # Save merged settings
        try:
            with open(target_settings_file, "w", encoding="utf-8") as f:
                json.dump(merged_settings, f, indent=2)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Applied preset '{preset_data.get('name')}' to {target_settings_file}"
            )
            return True
        except IOError as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to save settings: {e}"
            )
            return False

    def _merge_settings(self, base: Dict, overlay: Dict) -> Dict:
        """
        @brief Deep merge two settings dictionaries, with overlay taking precedence.
        @param base Base settings dictionary.
        @param overlay Settings to overlay on top of base.
        @return Merged settings dictionary.
        """
        result = base.copy()

        for key, value in overlay.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dictionaries
                result[key] = self._merge_settings(result[key], value)
            else:
                # Override with overlay value
                result[key] = value

        return result

    def get_preset_info(self, preset_id: str) -> Optional[Dict]:
        """
        @brief Get detailed information about a specific preset without fully loading it.
        @param preset_id The preset identifier.
        @return Dictionary with preset metadata, or None if not found.
        """
        preset_file = self.presets_dir / f"{preset_id}.json"

        if not preset_file.exists():
            return None

        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                preset_data = json.load(f)
                return {
                    "id": preset_id,
                    "name": preset_data.get("name", preset_id),
                    "description": preset_data.get("description", ""),
                    "requirements": preset_data.get("requirements", {}),
                    "settings": preset_data.get("settings", {}),
                    "settings_summary": {
                        "llm_model": preset_data.get("settings", {})
                        .get("SettingLoaderClass", {})
                        .get("ollama_model", {})
                        .get("value", "unknown"),
                        "whisper_model": preset_data.get("settings", {})
                        .get("AudioTranscriptionClass", {})
                        .get("whisper_model", {})
                        .get("value", "unknown"),
                        "languages": list(
                            preset_data.get("settings", {})
                            .get("TextToSpeech", {})
                            .get("language_models", {})
                            .get("value", {})
                            .keys()
                        ),
                    },
                }
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to get preset info for '{preset_id}': {e}"
            )
            return None

    def validate_preset(self, preset_id: str) -> tuple[bool, List[str]]:
        """
        @brief Validate a preset's structure and required fields.
        @param preset_id The preset identifier to validate.
        @return Tuple of (is_valid, list_of_errors).
        """
        errors = []

        preset_data = self.load_preset(preset_id)
        if not preset_data:
            errors.append("Preset file not found or could not be loaded")
            return False, errors

        # Check required top-level fields
        required_fields = ["name", "description", "requirements", "settings"]
        for field in required_fields:
            if field not in preset_data:
                errors.append(f"Missing required field: {field}")

        # Validate settings structure
        if "settings" in preset_data:
            settings = preset_data["settings"]

            # Check for SettingLoaderClass settings
            if "SettingLoaderClass" not in settings:
                errors.append("Missing SettingLoaderClass in settings")
            else:
                slc = settings["SettingLoaderClass"]
                if "ollama_model" not in slc:
                    errors.append("Missing ollama_model in SettingLoaderClass")

            # Check for AudioTranscriptionClass settings
            if "AudioTranscriptionClass" not in settings:
                errors.append("Missing AudioTranscriptionClass in settings")
            else:
                atc = settings["AudioTranscriptionClass"]
                if "whisper_model" not in atc:
                    errors.append("Missing whisper_model in AudioTranscriptionClass")

            # Check for TextToSpeech settings
            if "TextToSpeech" not in settings:
                errors.append("Missing TextToSpeech in settings")
            else:
                tts = settings["TextToSpeech"]
                if "language_models" not in tts:
                    errors.append("Missing language_models in TextToSpeech")

        is_valid = len(errors) == 0
        if is_valid:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Preset '{preset_id}' is valid"
            )
        else:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Preset '{preset_id}' has {len(errors)} validation errors"
            )

        return is_valid, errors

    def create_preset(self, preset_data: Dict) -> tuple[bool, str]:
        """
        @brief Create a new preset file from provided data.
        @param preset_data Dictionary containing preset configuration.
        @return Tuple of (success, message).
        """
        try:
            # Validate required fields
            if "id" not in preset_data:
                return False, "Preset ID is required"
            if "name" not in preset_data:
                return False, "Preset name is required"
            if "settings" not in preset_data:
                return False, "Settings configuration is required"

            preset_id = preset_data["id"]

            # Check if preset already exists
            preset_file = self.presets_dir / f"{preset_id}.json"
            if preset_file.exists():
                return False, f"Preset '{preset_id}' already exists"

            # Create preset structure
            preset = {
                "name": preset_data["name"],
                "description": preset_data.get("description", ""),
                "requirements": preset_data.get("requirements", {}),
                "settings": preset_data["settings"],
            }

            # Save to file
            with open(preset_file, "w", encoding="utf-8") as f:
                json.dump(preset, f, indent=2)

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Created new preset '{preset_id}'"
            )
            return True, f"Preset '{preset_id}' created successfully"

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Failed to create preset: {e}"
            )
            return False, f"Failed to create preset: {str(e)}"
