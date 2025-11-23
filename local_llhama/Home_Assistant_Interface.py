# === System Imports ===
import requests
import json
import os
import time
from dotenv import load_dotenv

# === Custom Imports ===
from .Shared_Logger import LogLevel
from .Simple_Functions import SimpleFunctions

class HomeAssistantClient:
    """
    @class HomeAssistantClient
    @brief Client to interact with Home Assistant API.

    This class handles fetching available domains, entities, and sending commands
    to Home Assistant devices. It also integrates simple functions for non-HA commands.
    """

    # Define the allowed domains (these are your "device types")
    ALLOWED_DOMAINS = ['light', 'climate', 'switch', 'fan', 'media_player', 'thermostat']

    def __init__(self):
        """
        @brief Initialize the client, fetch domain actions and entity map.
        """

        self.class_prefix_message = "[HomeAssistant]"
        # Load environment variables
        load_dotenv()
        
        # Load sensitive configuration from environment variables
        self.base_url = os.getenv('HA_BASE_URL', '')
        self.token = os.getenv('HA_TOKEN', '')
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        # Connection configuration
        self.timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        self.entity_map_cache = None  # Cache for fallback

        # Devices to exclude based on friendly name substrings
        self.exclusion_dict = {
            "exclude_name1": "APC1400",
            "exclude_name2": "Trust1500",
            "exclude_name3": "EATON",
        }
        
        # List of explicitly allowed entities when filtering by entity
        self.allowed_entities = [
            'light.kitchen_light',
            'light.desk_light',
            'light.couch_light',
            'climate.as35pbphra_pre',
            'climate.as25pbphra_pre',
        ]

    def _retry_request(self, method, url, **kwargs):
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

    def initialize_HA(self, allow_internet_searches=True):
                
        # Initialize simple functions handler with home location
        self.simple_functions : SimpleFunctions = SimpleFunctions(
            self.get_home_location(), 
            allow_internet_searches=allow_internet_searches
        )

        # Fetch domain actions from Home Assistant API
        self.domain_to_actions = self.fetch_domain_actions()

        # Fetch entity map, first with exclusions then filtering by allowed entities
        self.entity_map = self.fetch_entity_map(exclusion_dict=self.exclusion_dict)
        self.entity_map = self.fetch_entity_map(filter_mode='entity', allowed_entities=self.allowed_entities)
        
        # Uncomment if you want to update entity map from a file
        # self.entity_map = self.update_entity_map_from_file(self.entity_map)

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Entity map loaded with {len(self.entity_map)} entities") 

    def fetch_domain_actions(self) -> dict:
        """
        @brief Fetch all available domain actions (services) from Home Assistant.

        @return Dictionary mapping domains to a list of their supported actions,
                or an error message in case of failure.
        """
        url = f"{self.base_url}/api/services"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            response = self._retry_request('GET', url, headers=self.headers)
            services = response.json()

            domain_to_actions = {}
            for item in services:
                domain = item['domain']
                actions = list(item['services'].keys())
                domain_to_actions[domain] = actions

            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully fetched {len(domain_to_actions)} domain actions")
            return domain_to_actions

        except requests.exceptions.RequestException as req_err:
            error_msg = f"Failed to fetch domain actions: {req_err}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}
        except (ValueError, KeyError) as parse_err:
            error_msg = f"Error parsing services response: {parse_err}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}

    def fetch_entity_map(
        self,
        exclusion_dict: dict = None,
        filter_mode: str = 'domain',  # 'domain', 'entity', or 'none'
        allowed_entities: list = None  # Only used if filter_mode=='entity'
    ) -> dict:
        """
        @brief Fetch entities from Home Assistant, optionally filtered and excluded.

        @param exclusion_dict Dictionary of friendly name substrings to exclude.
        @param filter_mode Filter mode: 'domain' filters by allowed domains,
                        'entity' filters by allowed_entities list,
                        'none' applies no filtering.
        @param allowed_entities List of entity_ids to allow if filter_mode=='entity'.

        @return Dictionary mapping friendly_name to entity info and actions.
        """
        try:
            url = f"{self.base_url}/api/states"
            response = self._retry_request('GET', url, headers=self.headers)

            entities = response.json()

            exclusion_dict = exclusion_dict or {}
            allowed_entities = allowed_entities or []

            entity_map = {}

            for entity in entities:
                domain, _ = entity['entity_id'].split('.', 1)

                # Filtering logic based on filter_mode
                if filter_mode == 'domain':
                    if domain not in self.ALLOWED_DOMAINS:
                        continue
                elif filter_mode == 'entity':
                    if entity['entity_id'] not in allowed_entities:
                        continue
                elif filter_mode == 'none':
                    pass  # No filtering applied
                else:
                    raise ValueError(f"Invalid filter_mode: {filter_mode}")

                # Get friendly_name if available, fallback to entity_id (lowercase)
                friendly_name = entity['attributes'].get('friendly_name', entity['entity_id']).lower()

                # Exclude entities if their friendly_name contains any excluded substrings
                if any(excluded_name.lower() in friendly_name for excluded_name in exclusion_dict.values()):
                    continue

                # Get supported actions for the domain
                actions = self.domain_to_actions.get(domain, [])

                entity_map[friendly_name] = {
                    'entity_id': entity['entity_id'],
                    'actions': actions,
                }

            # Cache the entity map for fallback
            self.entity_map_cache = entity_map.copy()
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully fetched {len(entity_map)} entities")
            return entity_map

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch entity map: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            
            # Try to use cached entity map as fallback
            if self.entity_map_cache:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Using cached entity map with {len(self.entity_map_cache)} entities")
                return self.entity_map_cache
            
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] No cached entity map available")
            return {}
            
        except (ValueError, KeyError, TypeError) as e:
            error_msg = f"Error parsing entity map response: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            
            # Try to use cached entity map as fallback
            if self.entity_map_cache:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Using cached entity map with {len(self.entity_map_cache)} entities")
                return self.entity_map_cache
            
            return {}

    def send_commands(self, payload: dict, debug: bool = True):
        """
        @brief Send commands to Home Assistant devices or handle simple functions.

        @param payload Dictionary containing 'commands' list.
        @param debug Enable debug prints.

        @return List of results for each command or None.
        """
        results = []

        for command in payload.get('commands', []):
            action = command.get('action', '').replace(" ", "_")
            target = command.get('target', '').lower()
            extra_data = command.get('data', {})

            if debug:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing command: action={action}, target={target}, data={extra_data}")

            # Check if this command matches a simple function (non-HA)
            simple_action = self.simple_functions.find_matching_action(command_json=command)
            
            if simple_action is None:
                # Lookup entity info in the map
                entity_info = self.entity_map.get(target)

                if not entity_info:
                    # Unknown target error
                    results.append({
                        "target": target,
                        "action": action,
                        "error": f"Unknown target: {target}"
                    })
                    continue

                # Check if action supported by the entity's domain
                if action not in entity_info['actions']:
                    results.append({
                        "target": target,
                        "action": action,
                        "error": f"Action '{action}' not supported for target '{target}'"
                    })
                    continue

                domain = entity_info['entity_id'].split('.')[0]

                # Get service info to validate required fields
                service_info = self.get_service_info(domain, action)
                missing_fields = []

                if service_info:
                    required_fields = service_info.get('fields', {}).keys()
                    for field in required_fields:
                        if field == 'entity_id':
                            continue
                        if service_info['fields'][field].get('required', False) and field not in extra_data:
                            missing_fields.append(field)

                if missing_fields:
                    # Missing required data fields for the action
                    results.append({
                        "target": target,
                        "action": action,
                        "error": f"Missing required fields for action '{action}': {missing_fields}"
                    })
                    continue

                # Prepare request URL and payload for the service call
                url = f"{self.base_url}/api/services/{domain}/{action}"
                payload_data = {"entity_id": entity_info['entity_id'], **extra_data}

                try:
                    response = self._retry_request('POST', url, headers=self.headers, json=payload_data)
                    response_data = response.json() if response.content else {}

                    results.append({
                        "target": target,
                        "action": action,
                        "success": True,
                        "status": response.status_code,
                        "response": response_data,
                    })
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command executed: {action} on {target}")

                except requests.exceptions.RequestException as e:
                    # HTTP request failed after retries
                    error_msg = f"Failed to execute command after retries: {e}"
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
                    results.append({
                        "target": target,
                        "action": action,
                        "error": error_msg,
                        "url": url,
                        "payload": payload_data,
                    })

                except ValueError as e:  # JSON decoding error
                    error_msg = f"Failed to parse response JSON: {e}"
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
                    results.append({
                        "target": target,
                        "action": action,
                        "error": error_msg,
                        "status": response.status_code,
                        "response": response.text,
                    })

            else:
                # Call the simple function corresponding to the action
                # Pass any data parameters from the command
                result = self.simple_functions.call_function_by_name(simple_action, **extra_data)
                results.append({
                    "target": target,
                    "action": action,
                    "success": True,
                    "response": result,
                    "type": "simple_function"  # Tag to identify simple function execution
                })
        
        if debug:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] All command results: {results}")
        
        return results if results else None

    def get_service_info(self, domain, action):
        """
        @brief Retrieve service info for a domain and action from Home Assistant.

        @param domain Domain name (e.g., 'light')
        @param action Action name (e.g., 'turn_on')

        @return Service info dict if found, else None.
        """
        try:
            url = f"{self.base_url}/api/services"
            response = self._retry_request('GET', url, headers=self.headers)
            services = response.json()

            for item in services:
                if item['domain'] == domain:
                    return item['services'].get(action)
            return None
            
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to get service info for {domain}.{action}: {e}")
            return None

    def generate_devices_prompt_fragment(self):
        """
        @brief Generate JSON fragment describing devices and their actions.

        @return JSON-formatted string with device names and supported actions.
        """
        devices = {}
        for name, info in self.entity_map.items():
            # Replace underscores with spaces for readability in action names
            actions = [action.replace('_', ' ') for action in info['actions']]
            devices[name] = actions
        return json.dumps({"devices": devices}, indent=2)
    
    def get_home_location(self):
        """
        @brief Retrieve the configured home latitude and longitude from HA config.

        @return Dictionary with latitude and longitude or error message.
        """
        url = f"{self.base_url}/api/config"
        try:
            response = self._retry_request('GET', url, headers=self.headers)
            config = response.json()
            latitude = config.get('latitude')
            longitude = config.get('longitude')

            if latitude is not None and longitude is not None:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Retrieved home location: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            else:
                error_msg = "Latitude or longitude not found in the configuration"
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] {error_msg}")
                return {"error": error_msg}

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch home location: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}
        except (ValueError, KeyError) as e:
            error_msg = f"Error parsing config response: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}
