# settings_routes.py
import json
import subprocess
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from ..error_handler import FlaskErrorHandler

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings", methods=["GET"])
@login_required
def get_settings():
    """
    Returns the current settings JSON.
    """
    service = current_app.config["SERVICE_INSTANCE"]
    return service.settings_data


@settings_bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    """
    Saves incoming settings JSON to a file.
    Preserves TextToSpeech settings that may not be included in the web UI.
    """
    data = request.get_json()
    service = current_app.config["SERVICE_INSTANCE"]

    # Load existing settings to preserve TextToSpeech section
    try:
        with open(service.settings_file, "r", encoding="utf-8") as f:
            existing_settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_settings = {}

    # Preserve TextToSpeech settings if they exist and aren't in the new data
    if "TextToSpeech" in existing_settings and "TextToSpeech" not in data:
        data["TextToSpeech"] = existing_settings["TextToSpeech"]

    with open(service.settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return jsonify({"status": "ok"})


@settings_bp.route("/settings/language-models", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_language_models():
    """
    Get current language-to-TTS-model mappings.
    """
    service = current_app.config["SERVICE_INSTANCE"]
    loader = service.loader

    language_models = loader.get_language_models()

    return {"status": "ok", "language_models": language_models}


@settings_bp.route("/settings/language-models", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def update_language_models():
    """
    Update language-to-TTS-model mappings.
    Expects JSON: {"language_models": {"en": "en_US-amy-medium.onnx", ...}}
    """
    data = request.get_json()

    if not data or "language_models" not in data:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Missing 'language_models' in request",
                }
            ),
            400,
        )

    language_models = data["language_models"]

    # Validate structure
    if not isinstance(language_models, dict):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "language_models must be a dictionary",
                }
            ),
            400,
        )

    service = current_app.config["SERVICE_INSTANCE"]
    loader = service.loader

    success = loader.update_language_models(language_models)

    if success:
        return {"status": "ok", "message": "Language models updated successfully"}
    else:
        return (
            jsonify({"status": "error", "message": "Failed to update language models"}),
            500,
        )


@settings_bp.route("/settings/available-voices", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_available_voices():
    """
    Get list of available voice model files in the piper_voices directory.
    """
    # Get voice directory path
    voice_dir = Path("/home/llhama-usr/Local_LLHAMA/piper_voices")

    if not voice_dir.exists():
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Voice directory not found: {voice_dir}",
                }
            ),
            500,
        )

    # Get all .onnx files
    voice_files = sorted([f.name for f in voice_dir.glob("*.onnx")])

    return {"status": "ok", "voices": voice_files}


@settings_bp.route("/settings/prompts", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_prompts():
    """
    Get current LLM prompts configuration.
    """
    try:
        from local_llhama.settings import prompts

        # Build response with all prompts
        prompts_data = {
            "response_processor_prompt": prompts.RESPONSE_PROCESSOR_PROMPT,
            "smart_home_prompt_template": prompts.SMART_HOME_PROMPT_TEMPLATE,
            "conversation_processor_prompt": prompts.CONVERSATION_PROCESSOR_PROMPT,
            "calendar_event_prompt": prompts.CALENDAR_EVENT_PROMPT,
            "resume_conversation_prompt": prompts.RESUME_CONVERSATION_PROMPT,
            "smart_home_decision_making_extension": prompts.SMART_HOME_DECISION_MAKING_EXTENSION,
            "safety_instruction_prompt": prompts.SAFETY_INSTRUCTION_PROMPT,
        }

        return {"status": "ok", "prompts": prompts_data}
    except Exception as e:
        return (
            jsonify({"status": "error", "message": f"Error loading prompts: {str(e)}"}),
            500,
        )


@settings_bp.route("/settings/prompts", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def update_prompts():
    """
    Update LLM prompts configuration.
    Expects JSON: {"prompts": {"prompt_name": "value", ...}}
    """
    data = request.get_json()

    if not data or "prompts" not in data:
        return (
            jsonify({"status": "error", "message": "Missing 'prompts' in request"}),
            400,
        )

    prompts = data["prompts"]

    # Validate structure
    if not isinstance(prompts, dict):
        return (
            jsonify({"status": "error", "message": "prompts must be a dictionary"}),
            400,
        )

    prompts_file = Path(__file__).parent.parent / "settings" / "prompts.py"

    # Generate Python file content
    content = '''"""
@file prompts.py
@brief LLM prompt templates with human-readable multi-line format.

All prompts use triple-quoted strings for easy editing and readability.
Use {assistant_name} placeholder which will be replaced at runtime.
"""

'''

    prompt_names = [
        "RESPONSE_PROCESSOR_PROMPT",
        "SMART_HOME_PROMPT_TEMPLATE",
        "CONVERSATION_PROCESSOR_PROMPT",
        "CALENDAR_EVENT_PROMPT",
        "RESUME_CONVERSATION_PROMPT",
        "SMART_HOME_DECISION_MAKING_EXTENSION",
        "SAFETY_INSTRUCTION_PROMPT",
    ]

    for prompt_name in prompt_names:
        key = prompt_name.lower()
        value = prompts.get(key, "")

        # Escape triple quotes in the value
        value = value.replace('"""', r"\"\"\"")

        content += f'{prompt_name} = """{value}"""\n\n\n'

    # Save to file
    with open(prompts_file, "w", encoding="utf-8") as f:
        f.write(content)

    # Reload prompts in the application
    try:
        from local_llhama.llm_prompts import reload_prompts

        reload_prompts()
    except Exception as e:
        print(f"[Settings] Warning: Could not reload prompts: {e}")

    return {"status": "ok", "message": "Prompts updated successfully"}


@settings_bp.route("/settings/web-search", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_web_search_config():
    """
    Get current web search configuration.
    """
    service = current_app.config["SERVICE_INSTANCE"]

    if service.loader and hasattr(service.loader, "web_search_config"):
        config_data = service.loader.web_search_config
        return {"status": "ok", "config": config_data}
    else:
        # Fallback to loading from file if loader not available
        config_file = Path(
            "/home/llhama-usr/Local_LLHAMA/local_llhama/settings/web_search_config.json"
        )

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return {"status": "ok", "config": config_data}
        else:
            return (
                jsonify(
                    {"status": "error", "message": "Web search config file not found"}
                ),
                404,
            )


@settings_bp.route("/settings/web-search", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def update_web_search_config():
    """
    Update web search configuration.
    Expects JSON: {"config": {"allowed_websites": [...], "max_results": 3, "timeout": 10, "api_tokens": {...}}}
    """
    data = request.get_json()

    if not data or "config" not in data:
        return (
            jsonify({"status": "error", "message": "Missing 'config' in request"}),
            400,
        )

    config = data["config"]

    # Validate structure
    if not isinstance(config, dict):
        return (
            jsonify({"status": "error", "message": "config must be a dictionary"}),
            400,
        )

    service = current_app.config["SERVICE_INSTANCE"]

    config_file = Path(
        "/home/llhama-usr/Local_LLHAMA/local_llhama/settings/web_search_config.json"
    )

    # Save to file
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # Update loader's web_search_config if loader is available
    if service.loader and hasattr(service.loader, "web_search_config"):
        service.loader.web_search_config = config

    return {
        "status": "ok",
        "message": "Web search configuration updated successfully",
    }


@settings_bp.route("/settings/model", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_model_config():
    """
    Get current model configuration including assistant name and model settings.
    """
    service = current_app.config["SERVICE_INSTANCE"]
    loader = service.loader

    assistant_name = (
        loader.get_setting("SettingLoaderClass", "assistant_name") or "Assistant"
    )

    ollama_model = loader.get_setting("SettingLoaderClass", "ollama_model") or "unknown"
    embedding_model = (
        loader.get_setting("SettingLoaderClass", "ollama_embedding_model") or "unknown"
    )
    internet_searches = loader.get_setting(
        "SettingLoaderClass", "allow_internet_searches"
    )
    if internet_searches is None:
        internet_searches = True

    # Get decision model settings
    decision_model = (
        loader.get_setting("SettingLoaderClass", "ollama_decision_model")
        or "phi4-mini:3.8b-q4_K_M"
    )
    use_separate_decision_model = loader.get_setting(
        "SettingLoaderClass", "use_separate_decision_model"
    )
    if use_separate_decision_model is None:
        use_separate_decision_model = False

    return {
        "status": "ok",
        "config": {
            "assistant_name": assistant_name,
            "ollama_model": ollama_model,
            "embedding_model": embedding_model,
            "internet_searches": internet_searches,
            "decision_model": decision_model,
            "use_separate_decision_model": use_separate_decision_model,
        },
    }


@settings_bp.route("/settings/model", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def update_model_config():
    """
    Update model configuration (assistant name and decision model settings).
    Expects JSON: {
        "assistant_name": "LLHAMA",
        "use_separate_decision_model": true,
        "decision_model": "phi3:mini"
    }
    """
    data = request.get_json()

    if not data or "assistant_name" not in data:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Missing 'assistant_name' in request",
                }
            ),
            400,
        )

    assistant_name = data["assistant_name"].strip()

    if not assistant_name:
        return (
            jsonify({"status": "error", "message": "Assistant name cannot be empty"}),
            400,
        )

    service = current_app.config["SERVICE_INSTANCE"]
    loader = service.loader

    # Update assistant name
    success = loader.update_assistant_name(assistant_name)

    # Update decision model settings if provided
    if "use_separate_decision_model" in data:
        use_separate = data["use_separate_decision_model"]
        loader.update_setting(
            "SettingLoaderClass", "use_separate_decision_model", use_separate
        )

    if "decision_model" in data:
        decision_model = data["decision_model"].strip()
        if decision_model:
            loader.update_setting(
                "SettingLoaderClass", "ollama_decision_model", decision_model
            )

    if success:
        return {
            "status": "ok",
            "message": "Model configuration updated successfully. Restart system to apply changes.",
        }
    else:
        return (
            jsonify(
                {"status": "error", "message": "Failed to update model configuration"}
            ),
            500,
        )


@settings_bp.route("/settings/system-settings", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_system_settings():
    """
    Get current system settings including safety prompt configuration.
    """
    system_settings_file = Path(
        "/home/llhama-usr/Local_LLHAMA/local_llhama/settings/system_settings.json"
    )

    if system_settings_file.exists():
        with open(system_settings_file, "r", encoding="utf-8") as f:
            settings_data = json.load(f)

        return {"status": "ok", "settings": settings_data}
    else:
        return (
            jsonify({"status": "error", "message": "System settings file not found"}),
            404,
        )


@settings_bp.route("/settings/system-settings", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def update_system_settings():
    """
    Update system settings.
    Expects JSON: {"settings": {"safety": {...}, ...}}
    """
    data = request.get_json()

    if not data or "settings" not in data:
        return (
            jsonify({"status": "error", "message": "Missing 'settings' in request"}),
            400,
        )

    settings = data["settings"]

    # Validate structure
    if not isinstance(settings, dict):
        return (
            jsonify({"status": "error", "message": "settings must be a dictionary"}),
            400,
        )

    system_settings_file = Path(
        "/home/llhama-usr/Local_LLHAMA/local_llhama/settings/system_settings.json"
    )

    # Save to file
    with open(system_settings_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

    return {"status": "ok", "message": "System settings updated successfully"}


@settings_bp.route("/settings/available-gpus", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_available_gpus():
    """
    Detect and return available CUDA GPUs with their names.
    Uses nvidia-smi to avoid CUDA initialization issues in forked processes.
    """

    gpus = []

    # Add auto-detect option
    gpus.append(
        {"id": "auto", "name": "Auto-detect (Recommended)", "is_available": True}
    )

    # Add CPU option
    gpus.append({"id": "cpu", "name": "CPU Only", "is_available": True})

    # Try to detect NVIDIA GPUs using nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if line.strip():
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        gpu_index = parts[0].strip()
                        gpu_name = parts[1].strip()
                        gpus.append(
                            {
                                "id": f"cuda:{gpu_index}",
                                "name": f"GPU {gpu_index}: {gpu_name}",
                                "is_available": True,
                            }
                        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        # nvidia-smi not available or failed, just return basic options
        pass

    return {"status": "ok", "gpus": gpus}


@settings_bp.route("/settings/available-audio-devices", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def get_available_audio_devices():
    """
    Enumerate available audio input and output devices.
    Returns lists of microphones and speakers.
    """
    import pyaudio

    input_devices = []
    output_devices = []

    try:
        p = pyaudio.PyAudio()

        # Add default device option
        input_devices.append(
            {"index": None, "name": "System Default Microphone", "is_default": True}
        )
        output_devices.append(
            {"index": None, "name": "System Default Speaker", "is_default": True}
        )

        # Enumerate all devices
        device_count = p.get_device_count()
        for i in range(device_count):
            try:
                device_info = p.get_device_info_by_index(i)
                device_name = device_info.get("name", f"Device {i}")

                # Check if it's an input device (microphone)
                if device_info.get("maxInputChannels", 0) > 0:
                    input_devices.append(
                        {
                            "index": i,
                            "name": f"{device_name} (Index: {i})",
                            "is_default": False,
                        }
                    )

                # Check if it's an output device (speaker)
                if device_info.get("maxOutputChannels", 0) > 0:
                    output_devices.append(
                        {
                            "index": i,
                            "name": f"{device_name} (Index: {i})",
                            "is_default": False,
                        }
                    )
            except Exception as e:
                # Skip devices that can't be queried
                print(f"Skipping device {i}: {e}")
                continue

        # Don't terminate PyAudio - let garbage collector handle it
        # Just give time for cleanup
        import time

        time.sleep(0.1)

        return {
            "status": "ok",
            "input_devices": input_devices,
            "output_devices": output_devices,
        }

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to enumerate audio devices: {str(e)}",
                }
            ),
            500,
        )
