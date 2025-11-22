# === System Imports ===
import json
import torch
import os
from dotenv import load_dotenv

# === Custom Imports ===
from .LLM_Handler import LLM_Class, OllamaClient

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
        # Load environment variables from .env file
        load_dotenv()
        
        # Validate required environment variables
        self._validate_environment_variables()
        
        self.json_path = json_path
        self.data = {}
        self.base_model_path = "/mnt/fast_storage/huggingface/hub/"
        self.command_llm_name = "meta-llama/Llama-3.1-8B" 
        self.prompt_guard_model_name="./llama_guard_trained_multilingual"
        self.use_guard_llm = True
        self.load_models_in_8_bit = True
        self.base_path = base_path
        self.use_ollama = True
        self.ollama_ip =""
        self.ollama_model =""
        self.settings_file = f"{self.base_path}{self.json_path}"
        # Use CUDA if available, else fall back to CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def _validate_environment_variables(self):
        """
        @brief Validate that required environment variables are set.
        @raises EnvironmentError if critical environment variables are missing or invalid.
        """
        missing_vars = []
        warnings = []
        
        # Check for Home Assistant credentials (critical for HA integration)
        ha_base_url = os.getenv('HA_BASE_URL', '').strip()
        ha_token = os.getenv('HA_TOKEN', '').strip()
        
        if not ha_base_url:
            missing_vars.append('HA_BASE_URL')
        elif not ha_base_url.startswith(('http://', 'https://')):
            warnings.append(f"HA_BASE_URL should start with http:// or https:// (got: {ha_base_url})")
            
        if not ha_token:
            missing_vars.append('HA_TOKEN')
        elif len(ha_token) < 20:
            warnings.append("HA_TOKEN seems too short - verify it's a valid Long-Lived Access Token")
        
        # Check for Ollama IP (warning only, since it may not be used)
        ollama_ip = os.getenv('OLLAMA_IP', '').strip()
        if not ollama_ip:
            warnings.append("OLLAMA_IP not set - Ollama integration will use default or may fail")
        
        # Check for allowed IP prefixes
        allowed_ips = os.getenv('ALLOWED_IP_PREFIXES', '').strip()
        if not allowed_ips:
            warnings.append("ALLOWED_IP_PREFIXES not set - web UI will use default (may be insecure)")
        
        # Print warnings
        if warnings:
            print("[SettingsLoader] [WARNING] Environment variable warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        
        # Raise error if critical variables are missing
        if missing_vars:
            error_msg = (
                f"Critical environment variables missing: {', '.join(missing_vars)}\n"
                f"Please ensure you have a .env file with the required variables.\n"
                f"You can copy .env.example to .env and fill in your credentials:\n"
                f"  cp .env.example .env\n"
                f"Then edit .env with your Home Assistant URL and token."
            )
            raise EnvironmentError(error_msg)
        
        print("[SettingsLoader] [INFO] Environment variable validation passed")

    def load(self):
        """
        @brief Loads and parses the JSON file into internal data.
        @exception Raises ValueError if the file cannot be parsed.
        """
        try:
            with open(f"{self.settings_file}", 'r') as f:
                self.data = json.load(f)
                print("Settings Loading Successful")
        except Exception as e:
            raise ValueError(f"Failed to load JSON file: {e}")
        
    def load_llm_models(self, ha_client):
        """
        @brief Loads the command LLM model with given Home Assistant client.

        @param ha_client: An instance of HomeAssistantClient to integrate LLM with home automation.
        @return: A loaded instance of LLM_Class.
        @raises ValueError: If Ollama configuration is invalid when use_ollama is True.
        """
        if self.use_ollama:
            # Load ollama_ip from environment variable if not set in JSON
            ollama_ip = self.ollama_ip or os.getenv('OLLAMA_IP', '').strip()
            
            if not ollama_ip:
                error_msg = (
                    "Ollama is enabled but OLLAMA_IP is not configured.\n"
                    "Please set OLLAMA_IP in your .env file (e.g., OLLAMA_IP=192.168.88.239:11434)"
                )
                raise ValueError(error_msg)
            
            # Validate format (should contain colon for IP:PORT)
            if ':' not in ollama_ip:
                print(f"[SettingsLoader] [WARNING] OLLAMA_IP ({ollama_ip}) doesn't contain port. Expected format: IP:PORT")
            
            print(f"[SettingsLoader] [INFO] Connecting to Ollama at {ollama_ip} with model {self.ollama_model}")
            command_llm = OllamaClient(ha_client, host=ollama_ip, model=self.ollama_model)
        else:
            command_llm_path = f"{self.base_model_path}{self.command_llm_name}"
            print(f"Loading command LLM model from {command_llm_path}")
            command_llm = LLM_Class(
                model_path=self.base_model_path,
                model_name=self.command_llm_name,
                device=self.device,
                ha_client=ha_client,
                prompt_guard_model_name=self.prompt_guard_model_name,
                load_guard=self.use_guard_llm                       
            )        
        return command_llm

    def apply(self, objects):
        """
        Applies settings from self.data to given objects (and self).
        Reflection-based: looks at each attribute in the class config
        and assigns it if the object has a matching attribute.
        """
        all_objects = objects + [self]

        for obj in all_objects:
            cls_name = obj.__class__.__name__

            # Skip if this object's class has no section in data
            if cls_name not in self.data:
                continue

            for attr, info in self.data[cls_name].items():
                if not hasattr(obj, attr):
                    print(f"[Warning] '{cls_name}' has no attribute '{attr}'")
                    continue

                raw_value = info.get("value")
                expected_type = info.get("type")

                try:
                    converted_value = self.cast_value(raw_value, expected_type)
                    setattr(obj, attr, converted_value)  # reflection
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
