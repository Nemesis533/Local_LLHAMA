"""
@file LLM_Prompts.py
@brief Prompt templates for language model interactions.

Loads prompts from prompts.py and injects assistant name from object_settings.json.
"""

import json
from pathlib import Path


def _load_assistant_name(settings_loader=None):
    """Load assistant name from settings_loader if available, else read from file."""
    if settings_loader is not None:
        name = getattr(settings_loader, "assistant_name", None)
        if name:
            return name

    try:
        settings_file = Path(__file__).parent / "settings" / "object_settings.json"
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "SettingLoaderClass" in data:
                    assistant_config = data["SettingLoaderClass"].get(
                        "assistant_name", {}
                    )
                    if (
                        isinstance(assistant_config, dict)
                        and "value" in assistant_config
                    ):
                        return assistant_config["value"]
    except Exception as e:
        print(f"[LLM_Prompts] Error loading assistant name: {e}")

    return "Assistant"


def _inject_assistant_name(prompt_text, assistant_name):
    """Replace {assistant_name} placeholder in prompt text."""
    if isinstance(prompt_text, str):
        return prompt_text.replace("{assistant_name}", assistant_name)
    return prompt_text


def _load_and_inject(assistant_name: str) -> dict:
    """
    Import all prompts from settings/prompts.py, inject assistant_name, and
    return a dict of prompt-name → final string.  Raises on import failure.
    """
    import importlib

    from local_llhama.settings import prompts as prompts_module

    importlib.reload(prompts_module)

    from local_llhama.settings.prompts import CALENDAR_EVENT_PROMPT as _RAW_CALENDAR
    from local_llhama.settings.prompts import CONTEXT_SUMMARY_PROMPT
    from local_llhama.settings.prompts import (
        CONVERSATION_PROCESSOR_PROMPT as _RAW_CONVERSATION,
    )
    from local_llhama.settings.prompts import (
        IMAGE_ANALYSIS_PROMPT as _RAW_IMAGE_ANALYSIS,
    )
    from local_llhama.settings.prompts import (
        IMAGE_ANALYSIS_SAFETY_PROMPT as _RAW_IMAGE_ANALYSIS_SAFETY,
    )
    from local_llhama.settings.prompts import IMAGE_INTRO_USER_PROMPT
    from local_llhama.settings.prompts import (
        RESPONSE_PROCESSOR_PROMPT as _RAW_RESPONSE_PROCESSOR,
    )
    from local_llhama.settings.prompts import RESUME_CONVERSATION_PROMPT as _RAW_RESUME
    from local_llhama.settings.prompts import SAFETY_INSTRUCTION_PROMPT as _RAW_SAFETY
    from local_llhama.settings.prompts import (
        SMART_HOME_DECISION_MAKING_EXTENSION as _RAW_DECISION,
    )
    from local_llhama.settings.prompts import (
        SMART_HOME_PROMPT_TEMPLATE as _RAW_SMART_HOME,
    )

    inject = lambda t: _inject_assistant_name(t, assistant_name)
    return {
        "RESPONSE_PROCESSOR_PROMPT": inject(_RAW_RESPONSE_PROCESSOR),
        "SMART_HOME_PROMPT_TEMPLATE": inject(_RAW_SMART_HOME),
        "CONVERSATION_PROCESSOR_PROMPT": inject(_RAW_CONVERSATION),
        "CALENDAR_EVENT_PROMPT": inject(_RAW_CALENDAR),
        "RESUME_CONVERSATION_PROMPT": inject(_RAW_RESUME),
        "SMART_HOME_DECISION_MAKING_EXTENSION": inject(_RAW_DECISION),
        "SAFETY_INSTRUCTION_PROMPT": inject(_RAW_SAFETY),
        "CONTEXT_SUMMARY_PROMPT": CONTEXT_SUMMARY_PROMPT,
        "IMAGE_ANALYSIS_PROMPT": _RAW_IMAGE_ANALYSIS,
        "IMAGE_ANALYSIS_SAFETY_PROMPT": _RAW_IMAGE_ANALYSIS_SAFETY,
        "IMAGE_INTRO_USER_PROMPT": IMAGE_INTRO_USER_PROMPT,
    }


def _apply_prompts(prompts: dict):
    """Write the prompts dict into module-level globals."""
    global RESPONSE_PROCESSOR_PROMPT, SMART_HOME_PROMPT_TEMPLATE
    global CONVERSATION_PROCESSOR_PROMPT, CALENDAR_EVENT_PROMPT, RESUME_CONVERSATION_PROMPT
    global SMART_HOME_DECISION_MAKING_EXTENSION, SAFETY_INSTRUCTION_PROMPT, CONTEXT_SUMMARY_PROMPT
    global IMAGE_ANALYSIS_PROMPT, IMAGE_ANALYSIS_SAFETY_PROMPT, IMAGE_INTRO_USER_PROMPT
    for name, value in prompts.items():
        globals()[name] = value


# ── Module-level initialisation ──────────────────────────────────────────────

_assistant_name = _load_assistant_name()

try:
    _apply_prompts(_load_and_inject(_assistant_name))
    print(f"[LLM_Prompts] Loaded 11 prompts (assistant: {_assistant_name})")

except Exception as e:
    print(f"[LLM_Prompts] Error importing prompts: {e}, using defaults")

    # Fallback defaults
    RESPONSE_PROCESSOR_PROMPT = f"You are {_assistant_name}, a helpful assistant."
    SMART_HOME_PROMPT_TEMPLATE = f"You are {_assistant_name}, a smart home assistant."
    CONVERSATION_PROCESSOR_PROMPT = (
        f"You are {_assistant_name}, a conversational assistant."
    )
    CALENDAR_EVENT_PROMPT = "Remind about calendar events."
    RESUME_CONVERSATION_PROMPT = "Continue conversation."
    SMART_HOME_DECISION_MAKING_EXTENSION = ""
    SAFETY_INSTRUCTION_PROMPT = ""
    CONTEXT_SUMMARY_PROMPT = "Summarize the following context: {context_text}"
    IMAGE_ANALYSIS_PROMPT = "Analyze the image and answer the user's question."
    IMAGE_ANALYSIS_SAFETY_PROMPT = "Do not assist with harmful content in images."
    IMAGE_INTRO_USER_PROMPT = (
        'An image is being generated with this description:\n"{description}"\n\n'
        "{title_instruction}\n"
        "Also write a single friendly sentence introducing the image to the user.\n"
        "Respond with exactly this JSON format:\n"
        '{{"title": "...", "comment": "..."}}'
    )


def is_safety_enabled(settings_loader=None):
    """Check if safety prompt is enabled.

    Uses settings_loader.system_settings when available; falls back to file read.
    """
    try:
        if settings_loader is not None:
            system_settings = getattr(settings_loader, "system_settings", None)
            if system_settings:
                safety_config = system_settings.get("safety", {})
                safety_enabled = safety_config.get("safety_prompt_enabled", {})
                if isinstance(safety_enabled, dict):
                    return safety_enabled.get("value", True)
                return safety_enabled

        settings_file = Path(__file__).parent / "settings" / "system_settings.json"
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                safety_config = data.get("safety", {})
                safety_enabled = safety_config.get("safety_prompt_enabled", {})

                if isinstance(safety_enabled, dict):
                    return safety_enabled.get("value", True)
                return safety_enabled
    except Exception as e:
        print(
            f"[LLM_Prompts] Error checking safety setting: {e}, defaulting to enabled"
        )

    return True


def reload_prompts(settings_loader=None, system_settings=None):
    """Reload prompts from file. Call this after updating prompts.py or assistant name."""
    global _assistant_name

    _assistant_name = _load_assistant_name(settings_loader)

    try:
        _apply_prompts(_load_and_inject(_assistant_name))
        print(
            f"[LLM_Prompts] Prompts reloaded successfully (assistant: {_assistant_name})"
        )
        return True
    except Exception as e:
        print(f"[LLM_Prompts] Error reloading prompts: {e}")
        return False
