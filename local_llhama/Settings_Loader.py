# === System Imports ===
import json
import torch
import os
from dotenv import load_dotenv

# === Custom Imports ===
from .LLM_Handler import LLM_Class
from .Ollama_Client import OllamaClient
from .PostgreSQL_Client import PostgreSQLClient
from .state_components.conversation_loader import ConversationLoader
from .Shared_Logger import LogLevel

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
        self.class_prefix_message = "[SettingLoaderClass]"
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
        self.allow_internet_searches = True
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
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Environment variable warnings:")
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
        
        print(f"{self.class_prefix_message} {LogLevel.INFO} Environment variable validation passed")

    def load(self):
        """
        @brief Loads and parses the JSON file into internal data.
        @exception Raises ValueError if the file cannot be parsed.
        """
        try:
            # Check if file exists
            if not os.path.exists(self.settings_file):
                raise FileNotFoundError(f"Settings file not found: {self.settings_file}")
            
            # Check if path is actually a file
            if not os.path.isfile(self.settings_file):
                raise ValueError(f"Settings path is not a file: {self.settings_file}")
            
            # Check file permissions
            if not os.access(self.settings_file, os.R_OK):
                raise PermissionError(f"No read permission for settings file: {self.settings_file}")
            
            # Check file size
            file_size = os.path.getsize(self.settings_file)
            if file_size == 0:
                raise ValueError(f"Settings file is empty: {self.settings_file}")
            elif file_size > 10 * 1024 * 1024:  # 10MB limit
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Settings file is very large ({file_size} bytes)")
            
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                try:
                    self.data = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON in settings file: {e}\n"
                        f"Line {e.lineno}, column {e.colno}: {e.msg}"
                    )
            
            # Validate structure
            if not isinstance(self.data, dict):
                raise ValueError(f"Settings file must contain a JSON object, got {type(self.data).__name__}")
            
            if len(self.data) == 0:
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Settings file is empty (no configuration found)")
            
            print(f"{self.class_prefix_message} {LogLevel.INFO} Settings loaded successfully from {self.settings_file}")
            print(f"{self.class_prefix_message} {LogLevel.INFO} Loaded {len(self.data)} configuration section(s)")
            
        except FileNotFoundError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            print(f"{self.class_prefix_message} {LogLevel.INFO} Expected location: {self.settings_file}")
            print(f"{self.class_prefix_message} {LogLevel.INFO} Base path: {self.base_path}")
            raise
        except PermissionError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            print(f"{self.class_prefix_message} {LogLevel.INFO} Check file permissions: ls -l {self.settings_file}")
            raise
        except ValueError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            raise
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} Unexpected error loading settings: {type(e).__name__}: {repr(e)}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to load JSON file: {repr(e)}") from e
        
    def load_llm_models(self, ha_client):
        """
        @brief Loads the command LLM model with given Home Assistant client.

        @param ha_client: An instance of HomeAssistantClient to integrate LLM with home automation.
        @return: A loaded instance of LLM_Class or OllamaClient.
        @raises ValueError: If configuration is invalid or model loading fails.
        """
        # Initialize PostgreSQL client for message storage and embeddings
        pg_client = None
        try:
            pg_client = PostgreSQLClient()
            print(f"{self.class_prefix_message} {LogLevel.INFO} PostgreSQL client initialized successfully")
        except ValueError as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} PostgreSQL not configured: {repr(e)}")
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Message storage and embeddings will be disabled")
            pg_client = None
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Failed to initialize PostgreSQL client: {repr(e)}")
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Message storage and embeddings will be disabled")
            pg_client = None
        
        if self.use_ollama:
            # Load ollama_ip from environment variable if not set in JSON
            ollama_ip = self.ollama_ip or os.getenv('OLLAMA_IP', '').strip()
            
            if not ollama_ip:
                error_msg = (
                    "Ollama is enabled but OLLAMA_IP is not configured.\n"
                    "Please set OLLAMA_IP in your .env file (e.g., OLLAMA_IP=192.168.88.239:11434)"
                )
                print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {error_msg}")
                raise ValueError(error_msg)
            
            # Validate format (should contain colon for IP:PORT)
            if ':' not in ollama_ip:
                print(f"{self.class_prefix_message} {LogLevel.WARNING} OLLAMA_IP ({ollama_ip}) doesn't contain port. Expected format: IP:PORT")
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Adding default port :11434")
                ollama_ip = f"{ollama_ip}:11434"
            
            # Validate model name
            if not self.ollama_model or not self.ollama_model.strip():
                print(f"{self.class_prefix_message} {LogLevel.WARNING} No Ollama model specified, using default")
                self.ollama_model = "llama2"
            
            try:
                print(f"{self.class_prefix_message} {LogLevel.INFO} Connecting to Ollama at {ollama_ip} with model {self.ollama_model}")
                # Create ConversationLoader for chat history
                conversation_loader = ConversationLoader(pg_client) if pg_client else None
                # Pass conversation_loader to OllamaClient
                command_llm = OllamaClient(ha_client, host=ollama_ip, model=self.ollama_model, pg_client=pg_client, conversation_loader=conversation_loader)
                print(f"{self.class_prefix_message} {LogLevel.INFO} Ollama client created successfully")
            except Exception as e:
                print(f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to create Ollama client: {repr(e)}")
                raise ValueError(f"Ollama client initialization failed: {repr(e)}") from e
        else:
            # Local LLM loading
            if not self.command_llm_name or not self.command_llm_name.strip():
                raise ValueError("Command LLM name not configured")
            
            if not self.base_model_path or not os.path.exists(self.base_model_path):
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Base model path may not exist: {self.base_model_path}")
            
            command_llm_path = f"{self.base_model_path}{self.command_llm_name}"
            print(f"{self.class_prefix_message} {LogLevel.INFO} Loading command LLM model from {command_llm_path}")
            
            try:
                command_llm = LLM_Class(
                    model_path=self.base_model_path,
                    model_name=self.command_llm_name,
                    device=self.device,
                    ha_client=ha_client,
                    prompt_guard_model_name=self.prompt_guard_model_name,
                    load_guard=self.use_guard_llm                       
                )
                
                # Load the model
                if not command_llm.load_model(use_int8=self.load_models_in_8_bit):
                    raise ValueError("LLM model loading returned False")
                    
                print(f"{self.class_prefix_message} {LogLevel.INFO} Command LLM loaded successfully")
                
            except Exception as e:
                print(f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to load command LLM: {repr(e)}")
                raise ValueError(f"Command LLM loading failed: {repr(e)}") from e
                
        return command_llm

    def apply(self, objects):
        """
        Applies settings from self.data to given objects (and self).
        Reflection-based: looks at each attribute in the class config
        and assigns it if the object has a matching attribute.
        """
        if not isinstance(objects, list):
            print(f"{self.class_prefix_message} {LogLevel.WARNING} apply() expects a list, got {type(objects).__name__}")
            objects = [objects] if objects else []
        
        all_objects = objects + [self]
        applied_count = 0
        error_count = 0

        for obj in all_objects:
            if obj is None:
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Skipping None object in apply list")
                continue
            
            cls_name = obj.__class__.__name__

            # Skip if this object's class has no section in data
            if cls_name not in self.data:
                continue
            
            class_config = self.data[cls_name]
            if not isinstance(class_config, dict):
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Config for '{cls_name}' is not a dict, skipping")
                continue

            for attr, info in class_config.items():
                if not isinstance(info, dict):
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} Config for '{cls_name}.{attr}' is not a dict, skipping")
                    error_count += 1
                    continue
                
                if not hasattr(obj, attr):
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} '{cls_name}' has no attribute '{attr}'")
                    error_count += 1
                    continue

                raw_value = info.get("value")
                expected_type = info.get("type")
                
                if expected_type is None:
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} No type specified for '{cls_name}.{attr}', skipping")
                    error_count += 1
                    continue

                try:
                    converted_value = self.cast_value(raw_value, expected_type)
                    setattr(obj, attr, converted_value)  # reflection
                    applied_count += 1
                except ValueError as e:
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} Value error setting '{cls_name}.{attr}': {e}")
                    error_count += 1
                except TypeError as e:
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} Type error setting '{cls_name}.{attr}': {e}")
                    error_count += 1
                except Exception as e:
                    print(f"{self.class_prefix_message} {LogLevel.WARNING} Failed to set '{cls_name}.{attr}': {repr(e)}")
                    error_count += 1
        
        print(f"{self.class_prefix_message} {LogLevel.INFO} Applied {applied_count} setting(s), {error_count} error(s)")

    @staticmethod
    def cast_value(value, type_str):
        """
        @brief Converts a value to a Python object of the specified type.

        @param value The value to convert (can already be a list, etc.)
        @param type_str The expected type as a string: "int", "float", "bool", "str", "list".
        @return The value converted to the correct type.
        @exception Raises ValueError on unsupported or invalid conversion.
        """
        if type_str is None or not isinstance(type_str, str):
            raise ValueError(f"Invalid type specification: {type_str}")
        
        type_str = type_str.strip().lower()
        
        try:
            if type_str == "int":
                if value is None:
                    raise ValueError("Cannot convert None to int")
                return int(value)
            elif type_str == "float":
                if value is None:
                    raise ValueError("Cannot convert None to float")
                return float(value)
            elif type_str == "bool":
                if value is None:
                    return False
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)
            elif type_str == "str":
                if value is None:
                    return ""
                return str(value)
            elif type_str == "list":
                if value is None:
                    return []
                if isinstance(value, list):
                    return value
                elif isinstance(value, str):
                    # Allow comma-separated string to become list
                    if not value.strip():
                        return []
                    return [item.strip() for item in value.split(',')]
                else:
                    raise ValueError(f"Cannot convert {type(value).__name__} to list")
            else:
                raise ValueError(f"Unsupported type: {type_str}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to convert '{value}' to {type_str}: {e}") from e
        except Exception as e:
            raise ValueError(f"Unexpected error converting '{value}' to {type_str}: {repr(e)}") from e
