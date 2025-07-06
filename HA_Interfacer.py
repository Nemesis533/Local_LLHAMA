import requests
import json

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
        self.base_url = ""
        self.token = ""  
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

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

    def initialize_HA(self):
                
        # Initialize simple functions handler with home location
        self.simple_functions : SimpleFunctions = SimpleFunctions(self.get_home_location())

        # Fetch domain actions from Home Assistant API
        self.domain_to_actions = self.fetch_domain_actions()

        # Fetch entity map, first with exclusions then filtering by allowed entities
        self.entity_map = self.fetch_entity_map(exclusion_dict=self.exclusion_dict)
        self.entity_map = self.fetch_entity_map(filter_mode='entity', allowed_entities=self.allowed_entities)
        
        # Uncomment if you want to update entity map from a file
        # self.entity_map = self.update_entity_map_from_file(self.entity_map)

        print(self.entity_map) 

    def fetch_domain_actions(self) -> dict:
        """
        @brief Fetch all available domain actions (services) from Home Assistant.

        @return Dictionary mapping domains to a list of their supported actions.
        """
        url = f"{self.base_url}/api/services"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        services = response.json()

        domain_to_actions = {}
        for item in services:
            domain = item['domain']
            actions = list(item['services'].keys())
            domain_to_actions[domain] = actions

        return domain_to_actions

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
        url = f"{self.base_url}/api/states"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

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

        return entity_map

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
                print(f"Processing command: action={action}, target={target}, data={extra_data}")

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
                    response = requests.post(url, headers=self.headers, json=payload_data)
                    response.raise_for_status()  # Raise for HTTP errors
                    response_data = response.json() if response.content else {}

                    results.append({
                        "target": target,
                        "action": action,
                        "success": True,
                        "status": response.status_code,
                        "response": response_data,
                    })

                except requests.exceptions.RequestException as e:
                    # HTTP request failed
                    results.append({
                        "target": target,
                        "action": action,
                        "error": f"HTTP request failed: {e}",
                        "url": url,
                        "payload": payload_data,
                    })

                except ValueError as e:  # JSON decoding error
                    results.append({
                        "target": target,
                        "action": action,
                        "error": f"Failed to parse response JSON: {e}",
                        "status": response.status_code,
                        "raw_response": response.text,
                    })

                if debug:
                    print("Command Results:", results)

                return None
            
            else:
                # Call the simple function corresponding to the action
                results = self.simple_functions.call_function_by_name(simple_action)
                return results

    def get_service_info(self, domain, action):
        """
        @brief Retrieve service info for a domain and action from Home Assistant.

        @param domain Domain name (e.g., 'light')
        @param action Action name (e.g., 'turn_on')

        @return Service info dict if found, else None.
        """
        url = f"{self.base_url}/api/services"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        services = response.json()

        for item in services:
            if item['domain'] == domain:
                return item['services'].get(action)
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
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            config = response.json()
            latitude = config.get('latitude')
            longitude = config.get('longitude')

            if latitude is not None and longitude is not None:
                return {"latitude": latitude, "longitude": longitude}
            else:
                return {"error": "Latitude or longitude not found in the configuration"}

        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch home location: {e}"}


class SimpleFunctions:
    """
    @class SimpleFunctions
    @brief Implements additional non-Home Assistant commands and utilities.

    Handles tasks like weather info, converting command schemas, and other logic outside HA.
    """

    def __init__(self, home_location, db_config=None):
        """
        @brief Initialize with home location and optional DB config.
        @param home_location Dictionary with 'latitude' and 'longitude'.
        @param db_config Optional database configuration.
        """
        self.db_config = db_config
        self.filepath = "command_schema.txt"  # Path to the command schema JSON file
        self.home_location = home_location
        self.command_schema = self.load_command_schema_from_file()
        self.local_weather_url = "http://192.168.88.243:8000/weather-forecast"

    def call_function_by_name(self, function_name: str, *args, **kwargs):
        """
        @brief Call a method by name if it exists and is callable.

        @param function_name Name of the method to call.
        @return Result of the method or None if not found.
        """
        if hasattr(self, function_name):
            method = getattr(self, function_name)
            if callable(method):
                return method(*args, **kwargs)
            else:
                print(f"{function_name} exists but is not callable.")
        else:
            print(f"No function named {function_name} found.")

    def load_command_schema_from_file(self) -> dict:
        """
        @brief Load command schema from a JSON file.

        @return Dictionary of the command schema or empty dict on error.
        """
        try:
            with open(self.filepath, 'r', encoding='utf-8') as file:
                command_schema = json.load(file)
            return command_schema
        except FileNotFoundError:
            print(f"Error: File not found: {self.filepath}")
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON - {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        return {}

    def convert_command_schema_to_entities(self, schema):
        """
        @brief Convert command schema to virtual entities format.

        @param schema Command schema dictionary.
        @return Dictionary mapping virtual entity domains to actions.
        """
        virtual_entities = {}

        for domain, domain_info in schema.items():
            actions = list(domain_info.get('actions', {}).keys())
            virtual_entities[domain] = {
                'entity_id': f'virtual.{domain}',  # Not a real HA entity
                'actions': actions
            }

        return virtual_entities

    def home_weather(self, place=None):
        """
        @brief Fetch weather forecast from a local weather server.

        @param place Optional location parameter (currently unused).
        @return Weather forecast string or error message.
        """
        error_message = "Weather data not available at the moment, please try later."

        try:
            response = requests.get(self.local_weather_url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            return f"Error fetching weather forecast: {e}"

        forecast = data.get("forecast", [])
        if not forecast:
            return "Weather data not available."

        today = forecast[0]
        if today:
            return f"The weather at the location is {today['condition']} with a temperature of {round(float(today['temp']),2)} degrees."
        return error_message

    def get_coordinates(self, place_name):
        """
        @brief Get latitude and longitude coordinates for a given place name.

        @param place_name Name of the place to geocode.
        @return Tuple of (latitude, longitude) or (None, None) if not found.
        """
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            'name': place_name,
            'count': 1,
            'format': 'json'
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results")
            if results:
                return results[0]['latitude'], results[0]['longitude']
        return None, None
        
    def get_weather(self, place=None):
        """
        @brief Fetch current weather for a specified place.

        @param place Place name string.
        @return Weather description string or error message.
        """
        error_message = "Weather data not available at the moment, please try later."

        lat, lon = self.get_coordinates(place)

        if lat is None or lon is None:
            return f"Could not find location: {place}"

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'current_weather': True
        }
        response = requests.get(url, params=params)
        data = response.json().get("current_weather", {})
        if data:
            return f"The weather in {place} is {data['temperature']}°C with wind speed {data['windspeed']} km/h."
        return f"Weather data not available for {place}."
    
    def find_matching_action(self, command_json: dict | list) -> str | None:
        """
        @brief Find a matching simple function action for the given command.

        @param command_json Single command dict or list of commands.
        @return Action name string if matched, else None.
        """
        command_json = self.replace_target_with_entity_id(command_json)

        if isinstance(command_json, dict):
            command_json = [command_json]

        for item in command_json:
            entity = item.get("entity_id")
            action = item.get("action")

            if not entity:
                continue

            valid_actions = self.command_schema.get(entity, {}).get("actions", [])
            if action in valid_actions:
                return action

        return None
    
    def replace_target_with_entity_id(self, command):
        """
        @brief Recursively replace 'target' keys with 'entity_id' in command JSON.

        @param command Dict or list representing the command(s).
        @return Modified command with 'entity_id' keys.
        """
        if isinstance(command, dict):
            new_obj = {}
            for k, v in command.items():
                new_key = "entity_id" if k == "target" else k
                new_obj[new_key] = self.replace_target_with_entity_id(v)
            return new_obj
        elif isinstance(command, list):
            return [self.replace_target_with_entity_id(item) for item in command]
        else:
            return command
