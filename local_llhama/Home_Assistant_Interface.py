# === System Imports ===
import requests
import json
import os
from dotenv import load_dotenv

# === Custom Imports ===
from .Shared_Logger import LogLevel
from .Simple_Functions import SimpleFunctions
from .HA_Utils import HARequestHandler, HAEntityFilter, HADataFormatter, HAServiceValidator

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
        
        # Connection configuration
        self.timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        self.entity_map_cache = None  # Cache for fallback
        
        # Initialize request handler
        self.request_handler = HARequestHandler(
            self.base_url, 
            self.token, 
            self.timeout, 
            self.max_retries, 
            self.retry_delay
        )

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

    def initialize_HA(self, allow_internet_searches=True, pg_client=None):
        
        # Get home location and validate
        home_location = self.get_home_location()
        if "error" in home_location:
            error_msg = f"Failed to get home location: {home_location['error']}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            raise AttributeError(error_msg)
        
        # Initialize simple functions handler with home location
        self.simple_functions : SimpleFunctions = SimpleFunctions(
            home_location, 
            allow_internet_searches=allow_internet_searches,
            pg_client=pg_client
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

        try:
            response = self.request_handler.retry_request('GET', url, headers=self.request_handler.headers)
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
            response = self.request_handler.retry_request('GET', url, headers=self.request_handler.headers)

            entities = response.json()

            exclusion_dict = exclusion_dict or {}
            allowed_entities = allowed_entities or []

            entity_map = {}

            for entity in entities:
                domain, _ = entity['entity_id'].split('.', 1)

                # Filtering logic using utility class
                if not HAEntityFilter.should_include_entity(
                    entity['entity_id'], domain, filter_mode, 
                    self.ALLOWED_DOMAINS, allowed_entities
                ):
                    continue

                # Get friendly_name if available, fallback to entity_id (lowercase)
                friendly_name = entity['attributes'].get('friendly_name', entity['entity_id']).lower()

                # Exclude entities using utility class
                if HAEntityFilter.should_exclude_entity(friendly_name, exclusion_dict):
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
                    results.append(HADataFormatter.format_command_result(
                        target, action, error=f"Unknown target: {target}"
                    ))
                    continue

                # Validate action using utility class
                is_valid, error_msg = HAServiceValidator.validate_action_for_entity(action, entity_info)
                if not is_valid:
                    results.append(HADataFormatter.format_command_result(
                        target, action, error=error_msg
                    ))
                    continue

                domain = entity_info['entity_id'].split('.')[0]

                # Get service info to validate required fields
                service_info = self.get_service_info(domain, action)
                
                # Validate required fields using utility class
                is_valid, missing_fields = HAServiceValidator.validate_required_fields(service_info, extra_data)
                if not is_valid:
                    results.append(HADataFormatter.format_command_result(
                        target, action, 
                        error=f"Missing required fields for action '{action}': {missing_fields}"
                    ))
                    continue

                # Prepare request URL and payload for the service call
                url = f"{self.base_url}/api/services/{domain}/{action}"
                payload_data = {"entity_id": entity_info['entity_id'], **extra_data}

                try:
                    response = self.request_handler.retry_request('POST', url, headers=self.request_handler.headers, json=payload_data)
                    response_data = response.json() if response.content else {}

                    results.append(HADataFormatter.format_command_result(
                        target, action, success=True,
                        status=response.status_code,
                        response=response_data
                    ))
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command executed: {action} on {target}")

                except requests.exceptions.RequestException as e:
                    # HTTP request failed after retries
                    error_msg = f"Failed to execute command after retries: {e}"
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
                    results.append(HADataFormatter.format_command_result(
                        target, action, error=error_msg,
                        url=url, payload=payload_data
                    ))

                except ValueError as e:  # JSON decoding error
                    error_msg = f"Failed to parse response JSON: {e}"
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
                    results.append(HADataFormatter.format_command_result(
                        target, action, error=error_msg,
                        status=response.status_code,
                        response=response.text
                    ))

            else:
                # Call the simple function corresponding to the action
                # Pass any data parameters from the command
                result = self.simple_functions.call_function_by_name(simple_action, **extra_data)
                results.append(HADataFormatter.format_command_result(
                    target, action, success=True,
                    response=result,
                    type="simple_function"
                ))
        
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
            response = self.request_handler.retry_request('GET', url, headers=self.request_handler.headers)
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
        return HADataFormatter.generate_devices_prompt_fragment(self.entity_map)
    
    def get_home_location(self):
        """
        @brief Retrieve the configured home latitude and longitude from HA config.

        @return Dictionary with latitude and longitude or error message.
        """
        url = f"{self.base_url}/api/config"
        try:
            response = self.request_handler.retry_request('GET', url, headers=self.request_handler.headers)
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
