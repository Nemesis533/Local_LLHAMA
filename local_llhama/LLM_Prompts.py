"""
@file LLM_Prompts.py
@brief Prompt templates for language model interactions.

Loads prompts from prompts.json configuration file with fallback defaults.
Injects assistant name from object_settings.json into prompts.
"""

import json
from pathlib import Path


class PromptLoader:
    """Loads and manages LLM prompts from configuration file."""

    def __init__(self, settings_loader=None, system_settings=None):
        self.settings_loader = settings_loader
        self.assistant_name = self._load_assistant_name()
        self.prompts = self._load_prompts()
        self.system_settings = system_settings

    def _load_assistant_name(self):
        """Load assistant name from settings, with fallback to 'Assistant'."""
        try:
            if self.settings_loader:
                assistant_name = self.settings_loader.get_setting(
                    "SettingLoaderClass", "assistant_name"
                )
                if assistant_name:
                    return assistant_name

            # Fallback: try to load directly from object_settings.json
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

    def _load_prompts(self):
        """Load prompts from prompts.json file and inject assistant name."""
        try:
            prompts_file = Path(__file__).parent / "settings" / "prompts.json"

            if prompts_file.exists():
                with open(prompts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Extract values from the structure and inject assistant name
                prompts = {}
                for key, config in data.items():
                    if isinstance(config, dict) and "value" in config:
                        prompts[key] = config["value"]
                    else:
                        prompts[key] = config

                    # Inject assistant name into prompts
                    if isinstance(prompts[key], str):
                        prompts[key] = prompts[key].replace(
                            "{assistant_name}", self.assistant_name
                        )

                print(
                    f"[LLM_Prompts] Loaded {len(prompts)} prompts (assistant: {self.assistant_name})"
                )
                return prompts
            else:
                print(f"[LLM_Prompts] Prompts file not found, using defaults")
                return self._get_default_prompts()

        except Exception as e:
            print(f"[LLM_Prompts] Error loading prompts: {e}, using defaults")
            return self._get_default_prompts()

    def _get_default_prompts(self):
        """Return hardcoded default prompts as fallback with assistant name injected."""
        return {
            "response_processor_prompt": f"You are {self.assistant_name}, a helpful assistant.",
            "smart_home_prompt_template": f"You are {self.assistant_name}, a smart home assistant.",
            "conversation_processor_prompt": f"You are {self.assistant_name}, a conversational assistant.",
            "calendar_event_prompt": "Remind about calendar events.",
            "resume_conversation_prompt": "Continue conversation.",
        }

    def get(self, prompt_name, default=""):
        """Get a prompt by name."""
        return self.prompts.get(prompt_name, default)

    def is_safety_enabled(self):
        """Check if safety prompt is enabled."""
        try:
            safety_config = self.system_settings.get("safety", {})
            safety_enabled = safety_config.get("safety_prompt_enabled", {})

            if isinstance(safety_enabled, dict):
                return safety_enabled.get("value", True)
            return safety_enabled
        except Exception as e:
            print(
                f"[LLM_Prompts] Error checking safety setting: {e}, defaulting to enabled"
            )
            return True

    def reload(self, settings_loader=None, system_settings=None):
        """Reload prompts and assistant name from files."""
        if settings_loader:
            self.settings_loader = settings_loader
        if system_settings is not None:
            self.system_settings = system_settings
        self.assistant_name = self._load_assistant_name()
        self.prompts = self._load_prompts()
        print(f"[LLM_Prompts] Prompts reloaded (assistant: {self.assistant_name})")
        return True


# Create global prompt loader instance
_prompt_loader = PromptLoader()

# Export prompts for backward compatibility
RESPONSE_PROCESSOR_PROMPT = _prompt_loader.get("response_processor_prompt")
SMART_HOME_PROMPT_TEMPLATE = _prompt_loader.get("smart_home_prompt_template")
CONVERSATION_PROCESSOR_PROMPT = _prompt_loader.get("conversation_processor_prompt")
CALENDAR_EVENT_PROMPT = _prompt_loader.get("calendar_event_prompt")
RESUME_CONVERSATION_PROMPT = _prompt_loader.get("resume_conversation_prompt")
SMART_HOME_DECISION_MAKING_EXTENSION = _prompt_loader.get(
    "smart_home_decision_making_extension"
)
SAFETY_INSTRUCTION_PROMPT = _prompt_loader.get("safety_instruction_prompt")


def is_safety_enabled():
    """Check if safety prompt is enabled."""
    return _prompt_loader.is_safety_enabled()


def reload_prompts(settings_loader=None, system_settings=None):
    """Reload prompts from file. Call this after updating prompts.json or assistant name."""
    global _prompt_loader, RESPONSE_PROCESSOR_PROMPT, SMART_HOME_PROMPT_TEMPLATE
    global CONVERSATION_PROCESSOR_PROMPT, CALENDAR_EVENT_PROMPT, RESUME_CONVERSATION_PROMPT
    global SMART_HOME_DECISION_MAKING_EXTENSION, SAFETY_INSTRUCTION_PROMPT

    _prompt_loader.reload(settings_loader, system_settings)
    RESPONSE_PROCESSOR_PROMPT = _prompt_loader.get("response_processor_prompt")
    SMART_HOME_PROMPT_TEMPLATE = _prompt_loader.get("smart_home_prompt_template")
    CONVERSATION_PROCESSOR_PROMPT = _prompt_loader.get("conversation_processor_prompt")
    CALENDAR_EVENT_PROMPT = _prompt_loader.get("calendar_event_prompt")
    RESUME_CONVERSATION_PROMPT = _prompt_loader.get("resume_conversation_prompt")
    SMART_HOME_DECISION_MAKING_EXTENSION = _prompt_loader.get(
        "smart_home_decision_making_extension"
    )
    SAFETY_INSTRUCTION_PROMPT = _prompt_loader.get("safety_instruction_prompt")

    print("[LLM_Prompts] Prompts reloaded successfully")
    return True
