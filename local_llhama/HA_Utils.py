# === System Imports ===
import requests
import time
import json

# === Custom Imports ===
from .Shared_Logger import LogLevel


class HARequestHandler:
    """
    @class HARequestHandler
    @brief Handles HTTP requests to Home Assistant with retry logic and error handling.
    
    Provides robust HTTP request handling with exponential backoff retry logic,
    timeout management, and comprehensive error handling for communication with
    Home Assistant API.
    """

    def __init__(self, base_url: str, token: str, timeout: int = 10, max_retries: int = 3, retry_delay: int = 2):
        """
        @brief Initialize the request handler with configuration.
        
        @param base_url Base URL for Home Assistant API
        @param token Authentication token
        @param timeout Request timeout in seconds
        @param max_retries Maximum number of retry attempts
        @param retry_delay Initial delay between retries in seconds
        """
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.class_prefix_message = "[HomeAssistant]"

    def retry_request(self, method: str, url: str, **kwargs):
        """
        @brief Execute HTTP request with retry logic and exponential backoff.
        
        @param method HTTP method ('GET' or 'POST')
        @param url The URL to request
        @param kwargs Additional arguments for requests (json, headers, etc.)
        @return Response object if successful
        @raises requests.exceptions.RequestException after all retries fail
        """
        kwargs.setdefault('timeout', self.timeout)
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, **kwargs)
                elif method.upper() == 'POST':
                    response = requests.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Timeout on attempt {attempt + 1}/{self.max_retries}: {url}")
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Connection error on attempt {attempt + 1}/{self.max_retries}: {e}")
                
            except requests.exceptions.HTTPError as e:
                # Don't retry 4xx errors (client errors like auth failure)
                if 400 <= e.response.status_code < 500:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Client error {e.response.status_code}: {e}")
                    raise
                last_exception = e
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] HTTP error on attempt {attempt + 1}/{self.max_retries}: {e}")
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Request error on attempt {attempt + 1}/{self.max_retries}: {e}")
            
            # Exponential backoff before retry
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Retrying in {delay} seconds...")
                time.sleep(delay)
        
        # All retries failed
        error_msg = f"Failed to connect to Home Assistant at {self.base_url} after {self.max_retries} attempts"
        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
        if last_exception:
            raise requests.exceptions.RequestException(error_msg) from last_exception
        raise requests.exceptions.RequestException(error_msg)


class HAEntityFilter:
    """
    @class HAEntityFilter
    @brief Provides filtering and exclusion logic for Home Assistant entities.
    
    Handles entity filtering based on domains, explicit entity lists, and
    exclusion patterns based on friendly names.
    """

    @staticmethod
    def should_exclude_entity(friendly_name: str, exclusion_dict: dict) -> bool:
        """
        @brief Check if an entity should be excluded based on its friendly name.
        
        @param friendly_name The entity's friendly name
        @param exclusion_dict Dictionary of exclusion patterns
        @return True if entity should be excluded, False otherwise
        """
        if not exclusion_dict:
            return False
        return any(excluded_name.lower() in friendly_name.lower() 
                   for excluded_name in exclusion_dict.values())

    @staticmethod
    def should_include_entity(entity_id: str, domain: str, filter_mode: str, 
                             allowed_domains: list, allowed_entities: list) -> bool:
        """
        @brief Check if an entity should be included based on filter mode.
        
        @param entity_id The entity's ID
        @param domain The entity's domain
        @param filter_mode Filter mode: 'domain', 'entity', or 'none'
        @param allowed_domains List of allowed domains
        @param allowed_entities List of allowed entity IDs
        @return True if entity should be included, False otherwise
        """
        if filter_mode == 'domain':
            return domain in allowed_domains
        elif filter_mode == 'entity':
            return entity_id in allowed_entities
        elif filter_mode == 'none':
            return True
        else:
            raise ValueError(f"Invalid filter_mode: {filter_mode}")


class HADataFormatter:
    """
    @class HADataFormatter
    @brief Formats Home Assistant data for display and processing.
    
    Provides utility methods to format entity maps, service information,
    and generate prompt fragments for LLM interactions.
    """

    @staticmethod
    def generate_devices_prompt_fragment(entity_map: dict) -> str:
        """
        @brief Generate JSON fragment describing devices and their actions.
        
        @param entity_map Dictionary mapping entity names to their information
        @return JSON-formatted string with device names and supported actions
        """
        devices = {}
        for name, info in entity_map.items():
            # Replace underscores with spaces for readability in action names
            actions = [action.replace('_', ' ') for action in info['actions']]
            devices[name] = actions
        return json.dumps({"devices": devices}, indent=2)

    @staticmethod
    def format_command_result(target: str, action: str, success: bool = None, 
                            error: str = None, **kwargs) -> dict:
        """
        @brief Format a command execution result consistently.
        
        @param target The target entity
        @param action The action performed
        @param success Whether the command succeeded
        @param error Error message if failed
        @param kwargs Additional result data
        @return Formatted result dictionary
        """
        result = {
            "target": target,
            "action": action,
        }
        
        if error:
            result["error"] = error
        elif success is not None:
            result["success"] = success
            
        result.update(kwargs)
        return result


class HAServiceValidator:
    """
    @class HAServiceValidator
    @brief Validates Home Assistant service calls and parameters.
    
    Checks if actions are supported by entities and validates required
    parameters for service calls.
    """

    @staticmethod
    def validate_action_for_entity(action: str, entity_info: dict) -> tuple:
        """
        @brief Validate if an action is supported for an entity.
        
        @param action The action to validate
        @param entity_info Entity information dictionary
        @return Tuple of (is_valid, error_message)
        """
        if action not in entity_info.get('actions', []):
            return False, f"Action '{action}' not supported for this entity"
        return True, None

    @staticmethod
    def validate_required_fields(service_info: dict, extra_data: dict) -> tuple:
        """
        @brief Validate that all required fields are present for a service call.
        
        @param service_info Service information from Home Assistant
        @param extra_data Data provided for the service call
        @return Tuple of (is_valid, list_of_missing_fields)
        """
        if not service_info:
            return True, []
        
        missing_fields = []
        required_fields = service_info.get('fields', {}).keys()
        
        for field in required_fields:
            if field == 'entity_id':
                continue
            if service_info['fields'][field].get('required', False) and field not in extra_data:
                missing_fields.append(field)
        
        return len(missing_fields) == 0, missing_fields
