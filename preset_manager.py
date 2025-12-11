#!/usr/bin/env python3
"""
Preset Manager CLI

Command-line tool to manage configuration presets for the Local LLHAMA system.
"""

import argparse
import json
import sys
from pathlib import Path

# Direct imports to avoid loading the entire local_llhama package
sys.path.insert(0, str(Path(__file__).parent))


class SimplePresetLoader:
    """Lightweight preset loader for CLI usage without heavy dependencies."""

    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.presets_dir = self.base_path / "local_llhama" / "settings" / "presets"

    def list_presets(self):
        """List all available presets."""
        presets = []
        if not self.presets_dir.exists():
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
                print(f"Error loading {preset_file.name}: {e}")
        return presets

    def load_preset(self, preset_id):
        """Load a specific preset."""
        preset_file = self.presets_dir / f"{preset_id}.json"
        if not preset_file.exists():
            return None
        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def get_preset_info(self, preset_id):
        """Get preset information."""
        preset_data = self.load_preset(preset_id)
        if not preset_data:
            return None
        return {
            "id": preset_id,
            "name": preset_data.get("name", preset_id),
            "description": preset_data.get("description", ""),
            "requirements": preset_data.get("requirements", {}),
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

    def apply_preset(self, preset_id, target_settings_file):
        """Apply a preset to settings file."""
        preset_data = self.load_preset(preset_id)
        if not preset_data:
            return False

        preset_settings = preset_data.get("settings", {})
        if not preset_settings:
            return False

        # Load existing settings
        existing_settings = {}
        if Path(target_settings_file).exists():
            try:
                with open(target_settings_file, "r", encoding="utf-8") as f:
                    existing_settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # Merge settings
        merged_settings = self._merge_settings(existing_settings, preset_settings)

        # Store the active preset ID
        if "_system" not in merged_settings:
            merged_settings["_system"] = {}
        merged_settings["_system"]["active_preset"] = {
            "value": preset_id,
            "type": "str",
        }

        # Save
        try:
            with open(target_settings_file, "w", encoding="utf-8") as f:
                json.dump(merged_settings, f, indent=2)
            return True
        except IOError:
            return False

    def _merge_settings(self, base, overlay):
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in overlay.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        return result

    def validate_preset(self, preset_id):
        """Validate preset structure."""
        errors = []
        preset_data = self.load_preset(preset_id)
        if not preset_data:
            return False, ["Preset not found"]

        required_fields = ["name", "description", "requirements", "settings"]
        for field in required_fields:
            if field not in preset_data:
                errors.append(f"Missing required field: {field}")

        if "settings" in preset_data:
            settings = preset_data["settings"]
            if (
                "SettingLoaderClass" not in settings
                or "ollama_model" not in settings.get("SettingLoaderClass", {})
            ):
                errors.append("Missing ollama_model in SettingLoaderClass")
            if (
                "AudioTranscriptionClass" not in settings
                or "whisper_model" not in settings.get("AudioTranscriptionClass", {})
            ):
                errors.append("Missing whisper_model in AudioTranscriptionClass")
            if "TextToSpeech" not in settings or "language_models" not in settings.get(
                "TextToSpeech", {}
            ):
                errors.append("Missing language_models in TextToSpeech")

        return len(errors) == 0, errors


def list_presets(base_path):
    """List all available presets."""
    loader = SimplePresetLoader(base_path)
    presets = loader.list_presets()

    if not presets:
        print("No presets found.")
        return

    print(f"\nAvailable Presets ({len(presets)}):")
    print("=" * 80)
    for preset in presets:
        print(f"\nID: {preset['id']}")
        print(f"Name: {preset['name']}")
        print(f"Description: {preset['description']}")

        req = preset.get("requirements", {})
        if req:
            print(f"Requirements:")
            if "gpu_count" in req:
                print(f"  - GPUs: {req['gpu_count']}")
            if "vram_per_gpu" in req:
                print(f"  - VRAM per GPU: {req['vram_per_gpu']}")
            if "languages" in req:
                print(f"  - Languages: {', '.join(req['languages'])}")
        print("-" * 80)


def show_preset(base_path, preset_id):
    """Show detailed information about a specific preset."""
    loader = SimplePresetLoader(base_path)
    info = loader.get_preset_info(preset_id)

    if not info:
        print(f"Preset '{preset_id}' not found.")
        return 1

    print(f"\nPreset: {info['name']}")
    print("=" * 80)
    print(f"ID: {info['id']}")
    print(f"Description: {info['description']}")

    req = info.get("requirements", {})
    if req:
        print(f"\nRequirements:")
        if "gpu_count" in req:
            print(f"  GPU Count: {req['gpu_count']}")
        if "vram_per_gpu" in req:
            print(f"  VRAM per GPU: {req['vram_per_gpu']}")
        if "languages" in req:
            print(f"  Languages: {', '.join(req['languages'])}")

    summary = info.get("settings_summary", {})
    if summary:
        print(f"\nConfiguration:")
        print(f"  LLM Model: {summary.get('llm_model', 'unknown')}")
        print(f"  Whisper Model: {summary.get('whisper_model', 'unknown')}")
        print(f"  TTS Languages: {', '.join(summary.get('languages', []))}")

    return 0


def apply_preset(base_path, preset_id):
    """Apply a preset to the current configuration."""
    settings_file = f"{base_path}/local_llhama/settings/object_settings.json"

    loader = SimplePresetLoader(base_path)

    # Show what will be applied
    info = loader.get_preset_info(preset_id)
    if not info:
        print(f"Preset '{preset_id}' not found.")
        return 1

    print(f"\nApplying preset: {info['name']}")
    print(f"Description: {info['description']}")

    summary = info.get("settings_summary", {})
    if summary:
        print(f"\nThis will configure:")
        print(f"  LLM Model: {summary.get('llm_model', 'unknown')}")
        print(f"  Whisper Model: {summary.get('whisper_model', 'unknown')}")
        print(f"  TTS Languages: {', '.join(summary.get('languages', []))}")

    # Confirm
    response = input("\nApply this preset? [y/N]: ")
    if response.lower() != "y":
        print("Cancelled.")
        return 0

    # Apply the preset
    success = loader.apply_preset(preset_id, settings_file)

    if success:
        print(f"\n✓ Preset '{info['name']}' applied successfully!")
        print(f"Settings saved to: {settings_file}")
        print("\nNote: Restart the system for changes to take effect.")
        return 0
    else:
        print(f"\n✗ Failed to apply preset '{preset_id}'")
        return 1


def validate_preset(base_path, preset_id):
    """Validate a preset's structure."""
    loader = SimplePresetLoader(base_path)
    is_valid, errors = loader.validate_preset(preset_id)

    if is_valid:
        print(f"✓ Preset '{preset_id}' is valid.")
        return 0
    else:
        print(f"✗ Preset '{preset_id}' has validation errors:")
        for error in errors:
            print(f"  - {error}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Manage configuration presets for Local LLHAMA system"
    )
    parser.add_argument(
        "--base-path",
        default="/home/llhama-usr/Local_LLHAMA",
        help="Base path of the Local LLHAMA installation (default: /home/llhama-usr/Local_LLHAMA)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all available presets")

    # Show command
    show_parser = subparsers.add_parser(
        "show", help="Show detailed information about a preset"
    )
    show_parser.add_argument("preset_id", help="Preset ID to show")

    # Apply command
    apply_parser = subparsers.add_parser(
        "apply", help="Apply a preset to current configuration"
    )
    apply_parser.add_argument("preset_id", help="Preset ID to apply")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate a preset's structure"
    )
    validate_parser.add_argument("preset_id", help="Preset ID to validate")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    base_path = args.base_path

    if args.command == "list":
        list_presets(base_path)
        return 0
    elif args.command == "show":
        return show_preset(base_path, args.preset_id)
    elif args.command == "apply":
        return apply_preset(base_path, args.preset_id)
    elif args.command == "validate":
        return validate_preset(base_path, args.preset_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
