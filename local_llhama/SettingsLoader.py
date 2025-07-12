# system imports
import json
import torch
import os
import sys

# custom imports
from .LLM import LLM_Class

class SettingLoaderClass:
    """
    @class SettingLoader
    @brief Loads settings from a JSON file and applies them to given objects via reflection.

    The input JSON should be structured with top-level keys as class names and inner
    dictionaries mapping attribute names to a dictionary of value and type.
    Example:
    {
        "MyClass": {
            "foo": {"value": "123", "type": "int"},
            "bar": {"value": "hello", "type": "str"}
        }
    }
    """

    def __init__(self,base_path, json_path ="/settings/object_settings.json"):
        """
        @brief Constructor for SettingLoader.
        @param json_path Path to the JSON file containing configuration data.
        """
        self.json_path = json_path
        self.data = {}
        self.base_model_path = "/mnt/fast_storage/huggingface/hub/"
        self.command_llm_name = "meta-llama/Llama-3.1-8B" 
        self.prompt_guard_model_name="./llama_guard_trained_multilingual"
        self.use_guard_llm = True
        self.load_models_in_8_bit = True
        self.base_path = base_path
        self.settings_file = f"{self.base_path}{self.json_path}"
        # Use CUDA if available, else fall back to CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def load(self):
        """
        @brief Loads and parses the JSON file into internal data.
        @exception Raises ValueError if the file cannot be parsed.
        """
        try:
            with open(f"{self.settings_file}", 'r') as f:
                self.data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to load JSON file: {e}")
        
    def load_llm_models(self, ha_client):
        """
        @brief Loads the command LLM model with given Home Assistant client.

        @param ha_client: An instance of HomeAssistantClient to integrate LLM with home automation.
        @return: A loaded instance of LLM_Class.
        """
        command_llm_path = f"{self.base_model_path}{self.command_llm_name}"
        print(f"Loading command LLM model from {command_llm_path}")
        command_llm = LLM_Class(
            model_path=self.base_model_path,
            model_name=self.command_llm_name,
            device=self.device,
            ha_client=ha_client,
            prompt_guard_model_name=self.prompt_guard_model_name                      
        )        
        return command_llm

    def apply(self, objects):
        """
        @brief Applies loaded settings to a list of objects.
        @param objects List of instances to update.
        Also applies to self if SettingLoader is included.
        """
        # Include self in the list if the user wants to load into loader's own vars
        all_objects = objects + [self]

        for obj in all_objects:
            cls_name = obj.__class__.__name__
            if cls_name not in self.data:
                continue

            config = self.data[cls_name]

            for attr, info in config.items():
                if not hasattr(obj, attr):
                    print(f"[Warning] '{cls_name}' has no attribute '{attr}'")
                    continue

                raw_value = info.get("value")
                expected_type = info.get("type")

                try:
                    converted_value = self.cast_value(raw_value, expected_type)
                    setattr(obj, attr, converted_value)
                except Exception as e:
                    print(f"[Error] Failed to set '{cls_name}.{attr}': {e}")



    @staticmethod
    def cast_value(value, type_str):
        """
        @brief Converts a value to a Python object of the specified type.

        @param value The value to convert (can already be a list, etc.)
        @param type_str The expected type as a string: "int", "float", "bool", "str", "list".
        @return The value converted to the correct type.
        @exception Raises ValueError on unsupported or invalid conversion.
        """
        if type_str == "int":
            return int(value)
        elif type_str == "float":
            return float(value)
        elif type_str == "bool":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        elif type_str == "str":
            return str(value)
        elif type_str == "list":
            if isinstance(value, list):
                return value
            elif isinstance(value, str):
                # Optional: allow comma-separated string to become list
                return [item.strip() for item in value.split(',')]
            else:
                raise ValueError(f"Cannot convert {value} to list")
        else:
            raise ValueError(f"Unsupported type: {type_str}")
