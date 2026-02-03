"""
@file LLM_Prompts.py
@brief Prompt templates for language model interactions.

Loads prompts from prompts.py and injects assistant name from object_settings.json.
"""

import json
from pathlib import Path


def _load_assistant_name():
    """Load assistant name from settings, with fallback to 'Assistant'."""
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


# Load assistant name
_assistant_name = _load_assistant_name()

# Import prompts from prompts.py
try:
    from local_llhama.settings.prompts import CALENDAR_EVENT_PROMPT as _RAW_CALENDAR
    from local_llhama.settings.prompts import (
        CONVERSATION_PROCESSOR_PROMPT as _RAW_CONVERSATION,
    )
    from local_llhama.settings.prompts import CONTEXT_SUMMARY_PROMPT
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

    # Inject assistant name
    RESPONSE_PROCESSOR_PROMPT = _inject_assistant_name(
        _RAW_RESPONSE_PROCESSOR, _assistant_name
    )
    SMART_HOME_PROMPT_TEMPLATE = _inject_assistant_name(
        _RAW_SMART_HOME, _assistant_name
    )
    CONVERSATION_PROCESSOR_PROMPT = _inject_assistant_name(
        _RAW_CONVERSATION, _assistant_name
    )
    CALENDAR_EVENT_PROMPT = _inject_assistant_name(_RAW_CALENDAR, _assistant_name)
    RESUME_CONVERSATION_PROMPT = _inject_assistant_name(_RAW_RESUME, _assistant_name)
    SMART_HOME_DECISION_MAKING_EXTENSION = _inject_assistant_name(
        _RAW_DECISION, _assistant_name
    )
    SAFETY_INSTRUCTION_PROMPT = _inject_assistant_name(_RAW_SAFETY, _assistant_name)

    print(f"[LLM_Prompts] Loaded 8 prompts (assistant: {_assistant_name})")

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


def is_safety_enabled():
    """Check if safety prompt is enabled."""
    try:
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
    global RESPONSE_PROCESSOR_PROMPT, SMART_HOME_PROMPT_TEMPLATE
    global CONVERSATION_PROCESSOR_PROMPT, CALENDAR_EVENT_PROMPT, RESUME_CONVERSATION_PROMPT
    global SMART_HOME_DECISION_MAKING_EXTENSION, SAFETY_INSTRUCTION_PROMPT, CONTEXT_SUMMARY_PROMPT

    # Reload assistant name
    _assistant_name = _load_assistant_name()

    # Reimport prompts
    try:
        import importlib

        from local_llhama.settings import prompts as prompts_module

        importlib.reload(prompts_module)

        from local_llhama.settings.prompts import CALENDAR_EVENT_PROMPT as _RAW_CALENDAR
        from local_llhama.settings.prompts import (
            CONVERSATION_PROCESSOR_PROMPT as _RAW_CONVERSATION,
        )
        from local_llhama.settings.prompts import CONTEXT_SUMMARY_PROMPT
        from local_llhama.settings.prompts import (
            RESPONSE_PROCESSOR_PROMPT as _RAW_RESPONSE_PROCESSOR,
        )
        from local_llhama.settings.prompts import (
            RESUME_CONVERSATION_PROMPT as _RAW_RESUME,
        )
        from local_llhama.settings.prompts import (
            SAFETY_INSTRUCTION_PROMPT as _RAW_SAFETY,
        )
        from local_llhama.settings.prompts import (
            SMART_HOME_DECISION_MAKING_EXTENSION as _RAW_DECISION,
        )
        from local_llhama.settings.prompts import (
            SMART_HOME_PROMPT_TEMPLATE as _RAW_SMART_HOME,
        )

        # Inject assistant name
        RESPONSE_PROCESSOR_PROMPT = _inject_assistant_name(
            _RAW_RESPONSE_PROCESSOR, _assistant_name
        )
        SMART_HOME_PROMPT_TEMPLATE = _inject_assistant_name(
            _RAW_SMART_HOME, _assistant_name
        )
        CONVERSATION_PROCESSOR_PROMPT = _inject_assistant_name(
            _RAW_CONVERSATION, _assistant_name
        )
        CALENDAR_EVENT_PROMPT = _inject_assistant_name(_RAW_CALENDAR, _assistant_name)
        RESUME_CONVERSATION_PROMPT = _inject_assistant_name(
            _RAW_RESUME, _assistant_name
        )
        SMART_HOME_DECISION_MAKING_EXTENSION = _inject_assistant_name(
            _RAW_DECISION, _assistant_name
        )
        SAFETY_INSTRUCTION_PROMPT = _inject_assistant_name(_RAW_SAFETY, _assistant_name)

        print(
            f"[LLM_Prompts] Prompts reloaded successfully (assistant: {_assistant_name})"
        )
        return True

    except Exception as e:
        print(f"[LLM_Prompts] Error reloading prompts: {e}")
        return False
