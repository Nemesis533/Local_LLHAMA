# === System Imports ===
import json
import os

from dotenv import load_dotenv

# === Custom Imports ===
from .ollama import OllamaClient
from .postgresql_client import PostgreSQLClient
from .settings.PresetLoader import PresetLoader
from .shared_logger import LogLevel
from .state_components.conversation_loader import ConversationLoader


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

    def __init__(self, base_path, json_path="/settings/object_settings.json"):
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
        self.base_path = base_path
        self.allow_internet_searches = True
        self.ollama_ip = ""
        self.ollama_model = ""
        self.ollama_embedding_model = ""
        self.ollama_decision_model = ""
        self.use_separate_decision_model = False
        self.settings_file = f"{self.base_path}{self.json_path}"
        self.system_settings = {}
        self.assistant_name = ""  # Assistant name from settings
        self.web_search_config = {}  # Web search configuration

        # Initialize preset loader
        self.preset_loader = PresetLoader(base_path)

    def _validate_environment_variables(self):
        """
        @brief Validate that required environment variables are set.
        @raises EnvironmentError if critical environment variables are missing or invalid.
        """
        missing_vars = []
        warnings = []

        # Check for Home Assistant credentials (critical for HA integration)
        ha_base_url = os.getenv("HA_BASE_URL", "").strip()
        ha_token = os.getenv("HA_TOKEN", "").strip()

        if not ha_base_url:
            missing_vars.append("HA_BASE_URL")
        elif not ha_base_url.startswith(("http://", "https://")):
            warnings.append(
                f"HA_BASE_URL should start with http:// or https:// (got: {ha_base_url})"
            )

        if not ha_token:
            missing_vars.append("HA_TOKEN")
        elif len(ha_token) < 20:
            warnings.append(
                "HA_TOKEN seems too short - verify it's a valid Long-Lived Access Token"
            )

        # Check for allowed IP prefixes
        allowed_ips = os.getenv("ALLOWED_IP_PREFIXES", "").strip()
        if not allowed_ips:
            warnings.append(
                "ALLOWED_IP_PREFIXES not set - web UI will use default (may be insecure)"
            )

        # Print warnings
        if warnings:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Environment variable warnings:"
            )
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

        print(
            f"{self.class_prefix_message} {LogLevel.INFO} Environment variable validation passed"
        )

    def load(self):
        """
        @brief Loads and parses the JSON file into internal data.
        @exception Raises ValueError if the file cannot be parsed.
        """
        try:
            # Check if file exists
            if not os.path.exists(self.settings_file):
                raise FileNotFoundError(
                    f"Settings file not found: {self.settings_file}"
                )

            # Check if path is actually a file
            if not os.path.isfile(self.settings_file):
                raise ValueError(f"Settings path is not a file: {self.settings_file}")

            # Check file permissions
            if not os.access(self.settings_file, os.R_OK):
                raise PermissionError(
                    f"No read permission for settings file: {self.settings_file}"
                )

            # Check file size
            file_size = os.path.getsize(self.settings_file)
            if file_size == 0:
                raise ValueError(f"Settings file is empty: {self.settings_file}")
            elif file_size > 10 * 1024 * 1024:  # 10MB limit
                print(
                    f"{self.class_prefix_message} {LogLevel.WARNING} Settings file is very large ({file_size} bytes)"
                )

            with open(self.settings_file, "r", encoding="utf-8") as f:
                try:
                    self.data = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON in settings file: {e}\n"
                        f"Line {e.lineno}, column {e.colno}: {e.msg}"
                    )

            # Validate structure
            if not isinstance(self.data, dict):
                raise ValueError(
                    f"Settings file must contain a JSON object, got {type(self.data).__name__}"
                )

            if len(self.data) == 0:
                print(
                    f"{self.class_prefix_message} {LogLevel.WARNING} Settings file is empty (no configuration found)"
                )

            # Load system settings
            self.system_settings = self._load_system_settings()

            # Load web search config
            self.web_search_config = self._load_web_search_config()

            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Settings loaded successfully from {self.settings_file}"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Loaded {len(self.data)} configuration section(s)"
            )

        except FileNotFoundError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Expected location: {self.settings_file}"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Base path: {self.base_path}"
            )
            raise
        except PermissionError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Check file permissions: ls -l {self.settings_file}"
            )
            raise
        except ValueError as e:
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {e}")
            raise
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Unexpected error loading settings: {type(e).__name__}: {repr(e)}"
            )
            import traceback

            traceback.print_exc()
            raise ValueError(f"Failed to load JSON file: {repr(e)}") from e

    def get_language_models(self):
        """
        @brief Get language-to-TTS-model mapping from settings.

        @return: Dictionary mapping language codes (e.g., 'en', 'fr') to TTS model filenames.
        """
        if "TextToSpeech" not in self.data:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} TextToSpeech settings not found, using defaults"
            )
            return {
                "en": "en_US-amy-medium.onnx",
                "fr": "fr_FR-siwis-medium.onnx",
                "de": "de_DE-thorsten-high.onnx",
                "it": "it_IT-paola-medium.onnx",
                "es": "es_AR-daniela-high.onnx",
                "ru": "ru_RU-ruslan-medium.onnx",
            }

        tts_settings = self.data.get("TextToSpeech", {})
        language_models = tts_settings.get("language_models", {})

        if not language_models or "value" not in language_models:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} language_models not configured, using defaults"
            )
            return {
                "en": "en_US-amy-medium.onnx",
                "fr": "fr_FR-siwis-medium.onnx",
                "de": "de_DE-thorsten-high.onnx",
                "it": "it_IT-paola-medium.onnx",
                "es": "es_AR-daniela-high.onnx",
                "ru": "ru_RU-ruslan-medium.onnx",
            }

        lang_models = language_models.get("value", {})
        print(
            f"{self.class_prefix_message} {LogLevel.INFO} Loaded {len(lang_models)} language model mappings"
        )
        return lang_models

    def update_language_models(self, language_models):
        """
        @brief Update language-to-TTS-model mapping in settings and save to file.

        @param language_models: Dictionary mapping language codes to TTS model filenames.
        @return: True if successful, False otherwise.
        """
        try:
            # Ensure TextToSpeech section exists
            if "TextToSpeech" not in self.data:
                self.data["TextToSpeech"] = {}

            # Update language_models
            self.data["TextToSpeech"]["language_models"] = {
                "value": language_models,
                "type": "dict",
            }

            # Save to file
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)

            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Updated and saved {len(language_models)} language model mappings"
            )
            return True

        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to update language models: {repr(e)}"
            )
            return False

    def update_assistant_name(self, assistant_name):
        """
        @brief Update assistant name in settings and save to file.

        @param assistant_name: String name for the assistant (e.g., 'LLHAMA', 'Jarvis').
        @return: True if successful, False otherwise.
        """
        try:
            # Ensure SettingLoaderClass section exists
            if "SettingLoaderClass" not in self.data:
                self.data["SettingLoaderClass"] = {}

            # Update assistant_name
            self.data["SettingLoaderClass"]["assistant_name"] = {
                "value": assistant_name.strip(),
                "type": "str",
            }

            # Save to file
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)

            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Updated assistant name to '{assistant_name}'"
            )
            return True

        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to update assistant name: {repr(e)}"
            )
            return False

    def _load_system_settings(self):
        """Load system settings from system_settings.json file."""
        try:
            settings_file = f"{self.base_path}/settings/system_settings.json"

            if not os.path.exists(settings_file):
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] System settings file not found: {settings_file}"
                )
                raise FileNotFoundError(
                    f"System settings file not found: {settings_file}"
                )

            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded system settings"
            )
            return data

        except FileNotFoundError:
            raise
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error loading system settings: {e}"
            )
            raise

    def _load_web_search_config(self):
        """Load web search configuration from web_search_config.json file."""
        try:
            config_file = f"{self.base_path}/settings/web_search_config.json"

            if not os.path.exists(config_file):
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Web search config file not found: {config_file}"
                )
                # Return default configuration
                return {
                    "allowed_websites": [],
                    "max_results": 3,
                    "timeout": 10,
                    "api_tokens": {},
                }

            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded web search config"
            )
            return data

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Error loading web search config: {e}"
            )
            # Return default configuration on error
            return {
                "allowed_websites": [],
                "max_results": 3,
                "timeout": 10,
                "api_tokens": {},
            }

    def get_system_settings(self):
        """Get the loaded system settings."""
        return self.system_settings

    def get_system_setting(self, category, setting_key, default=None):
        """
        Get a specific system setting value.

        @param category: The top-level category (e.g., 'safety', 'chat', 'hardware')
        @param setting_key: The setting key within the category
        @param default: Default value if setting is not found
        @return: The setting value
        """
        try:
            category_data = self.system_settings.get(category, {})
            setting_data = category_data.get(setting_key, {})

            if isinstance(setting_data, dict) and "value" in setting_data:
                return setting_data["value"]
            return default
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Error getting system setting {category}.{setting_key}: {e}"
            )
            return default

    def get_cuda_device(self):
        """Get the configured CUDA device setting."""
        return self.get_system_setting("hardware", "cuda_device", "auto")

    def get_max_full_conversations(self):
        """Get the maximum number of conversations to load fully."""
        return self.get_system_setting("chat", "max_full_conversations", 10)

    def get_history_exchanges(self):
        """Get the number of conversation exchanges to keep in memory."""
        return self.get_system_setting("chat", "history_exchanges", 3)

    def get_ha_allowed_domains(self):
        """Get the list of allowed Home Assistant domains."""
        return self.get_system_setting(
            "home_assistant",
            "allowed_domains",
            ["light", "climate", "switch", "fan", "media_player", "thermostat"],
        )

    def get_ha_exclusion_dict(self):
        """Get the Home Assistant entity exclusion dictionary."""
        return self.get_system_setting("home_assistant", "exclusion_dict", {})

    def get_ha_allowed_entities(self):
        """Get the list of explicitly allowed Home Assistant entities."""
        return self.get_system_setting("home_assistant", "allowed_entities", [])

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
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} PostgreSQL client initialized successfully"
            )
        except ValueError as e:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} PostgreSQL not configured: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Message storage and embeddings will be disabled"
            )
            pg_client = None
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Failed to initialize PostgreSQL client: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Message storage and embeddings will be disabled"
            )
            pg_client = None

        # Load ollama host from system_settings.json or object_settings
        ollama_ip = self.get_system_setting("ollama", "host") or self.ollama_ip

        if not ollama_ip:
            error_msg = (
                "Ollama host is not configured.\n"
                "Please set ollama.host in system_settings.json (e.g., 192.168.88.239:11434)"
            )
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {error_msg}")
            raise ValueError(error_msg)

        # Validate format (should contain colon for IP:PORT)
        if ":" not in ollama_ip:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} OLLAMA_IP ({ollama_ip}) doesn't contain port. Expected format: IP:PORT"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Adding default port :11434"
            )
            ollama_ip = f"{ollama_ip}:11434"

        # Validate model name
        if not self.ollama_model or not self.ollama_model.strip():
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} No Ollama model specified, using default"
            )
            self.ollama_model = "llama2"

        # Validate embedding model name
        if not self.ollama_embedding_model or not self.ollama_embedding_model.strip():
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} No Ollama embedding model specified, using default"
            )
            self.ollama_embedding_model = "nomic-embed-text"

        try:
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Connecting to Ollama at {ollama_ip} with model {self.ollama_model}"
            )
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Using embedding model: {self.ollama_embedding_model}"
            )

            # Get decision model settings
            decision_model = getattr(
                self, "ollama_decision_model", "phi4-mini:3.8b-q4_K_M"
            )
            use_separate_decision_model = getattr(
                self, "use_separate_decision_model", False
            )

            if use_separate_decision_model:
                print(
                    f"{self.class_prefix_message} {LogLevel.INFO} Using separate decision model: {decision_model}"
                )

            # Get keepalive settings
            keepalive_enabled = self.get_setting(
                "OllamaClient", "model_keepalive_enabled"
            )
            if keepalive_enabled is None:
                keepalive_enabled = True

            keepalive_interval = self.get_setting(
                "OllamaClient", "model_keepalive_interval"
            )
            if keepalive_interval is None:
                keepalive_interval = 180

            # Create ConversationLoader for chat history
            conversation_loader = ConversationLoader(pg_client) if pg_client else None
            # Pass conversation_loader to OllamaClient
            command_llm = OllamaClient(
                ha_client,
                host=ollama_ip,
                model=self.ollama_model,
                pg_client=pg_client,
                conversation_loader=conversation_loader,
                embedding_model=self.ollama_embedding_model,
                decision_model=decision_model,
                use_separate_decision_model=use_separate_decision_model,
                keepalive_enabled=keepalive_enabled,
                keepalive_interval=keepalive_interval,
            )
            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Ollama client created successfully"
            )
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to create Ollama client: {repr(e)}"
            )
            raise ValueError(f"Ollama client initialization failed: {repr(e)}") from e

        return command_llm

    def apply(self, objects):
        """
        Applies settings from self.data to given objects (and self).
        Reflection-based: looks at each attribute in the class config
        and assigns it if the object has a matching attribute.
        """
        if not isinstance(objects, list):
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} apply() expects a list, got {type(objects).__name__}"
            )
            objects = [objects] if objects else []

        all_objects = objects + [self]
        applied_count = 0
        error_count = 0

        for obj in all_objects:
            if obj is None:
                print(
                    f"{self.class_prefix_message} {LogLevel.WARNING} Skipping None object in apply list"
                )
                continue

            cls_name = obj.__class__.__name__

            # Skip if this object's class has no section in data
            if cls_name not in self.data:
                continue

            class_config = self.data[cls_name]
            if not isinstance(class_config, dict):
                print(
                    f"{self.class_prefix_message} {LogLevel.WARNING} Config for '{cls_name}' is not a dict, skipping"
                )
                continue

            for attr, info in class_config.items():
                if not isinstance(info, dict):
                    print(
                        f"{self.class_prefix_message} {LogLevel.WARNING} Config for '{cls_name}.{attr}' is not a dict, skipping"
                    )
                    error_count += 1
                    continue

                if not hasattr(obj, attr):
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] '{cls_name}' has no attribute '{attr}'"
                    )
                    error_count += 1
                    continue

                raw_value = info.get("value")
                expected_type = info.get("type")

                if expected_type is None:
                    print(
                        f"{self.class_prefix_message} {LogLevel.WARNING} No type specified for '{cls_name}.{attr}', skipping"
                    )
                    error_count += 1
                    continue

                try:
                    converted_value = self.cast_value(raw_value, expected_type)
                    setattr(obj, attr, converted_value)  # reflection
                    applied_count += 1
                except ValueError as e:
                    print(
                        f"{self.class_prefix_message} {LogLevel.WARNING} Value error setting '{cls_name}.{attr}': {e}"
                    )
                    error_count += 1
                except TypeError as e:
                    print(
                        f"{self.class_prefix_message} {LogLevel.WARNING} Type error setting '{cls_name}.{attr}': {e}"
                    )
                    error_count += 1
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} {LogLevel.WARNING} Failed to set '{cls_name}.{attr}': {repr(e)}"
                    )
                    error_count += 1

        print(
            f"{self.class_prefix_message} {LogLevel.INFO} Applied {applied_count} setting(s), {error_count} error(s)"
        )

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
                    return [item.strip() for item in value.split(",")]
                else:
                    raise ValueError(f"Cannot convert {type(value).__name__} to list")
            elif type_str == "dict":
                if value is None:
                    return {}
                if isinstance(value, dict):
                    return value
                else:
                    raise ValueError(f"Cannot convert {type(value).__name__} to dict")
            else:
                raise ValueError(f"Unsupported type: {type_str}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to convert '{value}' to {type_str}: {e}") from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error converting '{value}' to {type_str}: {repr(e)}"
            ) from e

    # === Preset Management Methods ===

    def list_presets(self):
        """
        @brief List all available configuration presets.
        @return List of preset information dictionaries.
        """
        return self.preset_loader.list_presets()

    def load_preset(self, preset_id: str):
        """
        @brief Load a preset configuration.
        @param preset_id The preset identifier to load.
        @return Preset data dictionary or None if not found.
        """
        return self.preset_loader.load_preset(preset_id)

    def apply_preset(self, preset_id: str):
        """
        @brief Apply a preset to the current settings file and reload.
        @param preset_id The preset identifier to apply.
        @return True if successful, False otherwise.
        """
        success = self.preset_loader.apply_preset(preset_id, self.settings_file)
        if success:
            # Reload settings from file after applying preset
            # Note: We only reload the data, not apply to objects
            # Full application happens on system restart
            try:
                self.load()
                print(
                    f"{self.class_prefix_message} {LogLevel.INFO} Preset '{preset_id}' applied and settings reloaded. Restart required for changes to take effect."
                )
            except Exception as e:
                print(
                    f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to reload settings after preset application: {e}"
                )
                return False
        return success

    def get_preset_info(self, preset_id: str):
        """
        @brief Get information about a specific preset.
        @param preset_id The preset identifier.
        @return Preset information dictionary or None.
        """
        return self.preset_loader.get_preset_info(preset_id)

    def validate_preset(self, preset_id: str):
        """
        @brief Validate a preset's structure.
        @param preset_id The preset identifier to validate.
        @return Tuple of (is_valid, list_of_errors).
        """
        return self.preset_loader.validate_preset(preset_id)

    def get_setting(self, section: str, key: str):
        """
        @brief Get a specific setting value from the loaded data.
        @param section The section/class name (e.g., '_system', 'HomeAssistantClient').
        @param key The setting key within that section.
        @return The setting value, or None if not found.
        """
        if section not in self.data:
            return None

        section_data = self.data[section]
        if key not in section_data:
            return None

        setting = section_data[key]
        if isinstance(setting, dict) and "value" in setting:
            return setting["value"]

        return setting

    # === Whisper Model Configuration ===

    def get_whisper_model(self):
        """
        @brief Get the configured Whisper model name.
        @return Whisper model name (e.g., 'turbo', 'medium', 'small').
        """
        if "AudioTranscriptionClass" not in self.data:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} AudioTranscriptionClass settings not found, using default 'turbo'"
            )
            return "turbo"

        atc_settings = self.data.get("AudioTranscriptionClass", {})
        whisper_model = atc_settings.get("whisper_model", {})

        if not whisper_model or "value" not in whisper_model:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} whisper_model not configured, using default 'turbo'"
            )
            return "turbo"

        model_name = whisper_model.get("value", "turbo")
        print(
            f"{self.class_prefix_message} {LogLevel.INFO} Using Whisper model: {model_name}"
        )
        return model_name

    def update_whisper_model(self, model_name: str):
        """
        @brief Update the Whisper model configuration and save to file.
        @param model_name The Whisper model name (e.g., 'turbo', 'medium', 'small').
        @return True if successful, False otherwise.
        """
        valid_models = ["turbo", "large", "medium", "small", "base", "tiny"]
        if model_name not in valid_models:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} Invalid Whisper model '{model_name}'. Valid options: {valid_models}"
            )
            return False

        try:
            # Ensure AudioTranscriptionClass section exists
            if "AudioTranscriptionClass" not in self.data:
                self.data["AudioTranscriptionClass"] = {}

            # Update whisper_model
            self.data["AudioTranscriptionClass"]["whisper_model"] = {
                "value": model_name,
                "type": "str",
            }

            # Save to file
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)

            print(
                f"{self.class_prefix_message} {LogLevel.INFO} Updated Whisper model to '{model_name}' and saved to file"
            )
            return True

        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to update Whisper model: {repr(e)}"
            )
            return False

    def get_chat_handler_config(self):
        """
        @brief Get ChatHandler configuration from settings.

        @return Dictionary with ChatHandler configuration (max_tokens, context parameters).
        """
        # Default configuration
        defaults = {
            "max_tokens": 4096,
            "default_context_words": 400,
            "min_context_words": 100,
            "context_reduction_factor": 0.7,
            "context_management_mode": "truncate",
            "context_summarization_model": "decision",
            "context_summary_target_words": 150,
        }

        if "ChatHandler" not in self.data:
            print(
                f"{self.class_prefix_message} {LogLevel.WARNING} ChatHandler settings not found, using defaults"
            )
            # Add history_exchanges from system settings
            defaults["history_exchanges"] = self.get_history_exchanges()
            return defaults

        ch_settings = self.data.get("ChatHandler", {})

        config = {}
        for key, default_value in defaults.items():
            setting = ch_settings.get(key, {})
            if not setting or "value" not in setting:
                print(
                    f"{self.class_prefix_message} {LogLevel.INFO} ChatHandler.{key} not configured, using default: {default_value}"
                )
                config[key] = default_value
            else:
                config[key] = setting.get("value", default_value)

        # Always get history_exchanges from system settings
        config["history_exchanges"] = self.get_history_exchanges()

        print(
            f"{self.class_prefix_message} {LogLevel.INFO} ChatHandler config: max_tokens={config['max_tokens']}, "
            f"default_context_words={config['default_context_words']}, min_context_words={config['min_context_words']}, "
            f"history_exchanges={config['history_exchanges']}, "
            f"context_reduction_factor={config['context_reduction_factor']}, "
            f"context_management_mode={config['context_management_mode']}, "
            f"context_summarization_model={config['context_summarization_model']}, "
            f"context_summary_target_words={config['context_summary_target_words']}"
        )
        return config
