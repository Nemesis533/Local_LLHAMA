# === System Imports ===
import requests
import json
import os
import time
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

# === Custom Imports ===
from .Shared_Logger import LogLevel

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

                if debug:
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command Results: {results}")

                return None
            
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
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Simple function results: {results}")
        
        return results

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
        self.filepath = os.path.join(os.path.dirname(__file__), "command_schema.txt")  # Path to the command schema JSON file
        self.home_location = home_location
        self.command_schema = self.load_command_schema_from_file()
        self.local_weather_url = "http://192.168.88.243:8000/weather-forecast"
        self.web_search_config_path = os.path.join(
            os.path.dirname(__file__), 
            "settings", 
            "web_search_config.json"
        )
        self.web_search_config = self.load_web_search_config()
        
        # Load API keys from environment
        self.newsdata_api_key = os.getenv("NEWSDATA_API_KEY", "YOUR_NEWSDATA_API_KEY")

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
                print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] {function_name} exists but is not callable.")
        else:
            print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] No function named {function_name} found.")

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
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] File not found: {self.filepath}")
        except json.JSONDecodeError as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Failed to parse JSON - {e}")
        except Exception as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Unexpected error: {e}")

        return {}

    def load_web_search_config(self) -> dict:
        """
        @brief Load web search configuration from JSON file.

        @return Dictionary with allowed websites config or default config.
        """
        try:
            with open(self.web_search_config_path, 'r', encoding='utf-8') as file:
                config = json.load(file)
            print(f"[SimpleFunctions] [{LogLevel.INFO.name}] Loaded web search config with {len(config.get('allowed_websites', []))} websites")
            return config
        except FileNotFoundError:
            print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] Web search config not found: {self.web_search_config_path}")
            return {"allowed_websites": [], "max_results": 3, "timeout": 10}
        except json.JSONDecodeError as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Failed to parse web search config - {e}")
            return {"allowed_websites": [], "max_results": 3, "timeout": 10}
        except Exception as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Unexpected error loading web search config: {e}")
            return {"allowed_websites": [], "max_results": 3, "timeout": 10}

    def _clean_text(self, text: str) -> str:
        """
        @brief Clean and normalize text from web scraping.

        @param text Raw text string.
        @return Cleaned text string.
        """
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s.,!?;:\-()]', '', text)
        return text.strip()

    def _extract_text_from_html(self, html_content: str, max_length: int = 500) -> str:
        """
        @brief Extract and summarize text content from HTML.

        @param html_content Raw HTML string.
        @param max_length Maximum character length for extracted text.
        @return Cleaned and truncated text summary.
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)
            
            text = self._clean_text(text)
            
            if len(text) > max_length:
                text = text[:max_length] + "..."
            
            return text if text else "No readable content found."
            
        except Exception as e:
            print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] Error extracting text from HTML: {e}")
            return "Error parsing web content."

    def _search_website(self, url: str, query: str = None) -> dict:
        """
        @brief Fetch and parse content from a website.

        @param url Website URL to search.
        @param query Optional search query (for future enhancement).
        @return Dictionary with status and content or error.
        """
        timeout = self.web_search_config.get('timeout', 10)
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            content = self._extract_text_from_html(response.text)
            
            return {
                "success": True,
                "url": url,
                "content": content,
                "status_code": response.status_code
            }
            
        except requests.Timeout:
            return {
                "success": False,
                "url": url,
                "error": "Request timed out"
            }
        except requests.RequestException as e:
            return {
                "success": False,
                "url": url,
                "error": f"Failed to fetch: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": f"Unexpected error: {str(e)}"
            }

    def get_wikipedia_summary(self, topic=None):
        """
        @brief Fetch a short introductory summary from Wikipedia for a given topic.

        @param topic Topic/article name as a string.
        @return Summary string or error message.
        """
        error_message = "Wikipedia information not available at the moment, please try later."

        if not topic:
            return "Please specify a topic."

        # Use Wikimedia Core REST API to get HTML content
        # Format: https://api.wikimedia.org/core/v1/wikipedia/{language}/page/{title}/html
        # Replace spaces with underscores for the URL
        topic_formatted = topic.replace(" ", "_")
        url = f"https://api.wikimedia.org/core/v1/wikipedia/en/page/{topic_formatted}/html"

        try:
            headers = {
                'User-Agent': 'LLHAMA-Assistant/1.0 (https://github.com/Nemesis533/Local_LLHAMA)'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Extract text from HTML response
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'table', 'figure']):
                element.decompose()
            
            # Get the first few paragraphs (introduction)
            paragraphs = soup.find_all('p', limit=3)
            text_parts = []
            
            for p in paragraphs:
                text = p.get_text(separator=' ', strip=True)
                if text and len(text) > 20:  # Skip very short paragraphs
                    text_parts.append(text)
            
            if text_parts:
                summary = ' '.join(text_parts)
                # Limit to reasonable length
                if len(summary) > 500:
                    summary = summary[:497] + "..."
                return summary
            else:
                return f"No summary found for: {topic}"

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return f"No Wikipedia page found for: {topic}"
            return error_message
        except Exception:
            return error_message

    def get_news_summary(self, query=None):
        """
        @brief Fetch a summary of the latest global news related to a query.

        @param query Search term string.
        @return Summary of top news articles or error message.
        """
        error_message = "News data not available at the moment, please try later."

        if not query:
            return "Please specify a news topic."

        url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": self.newsdata_api_key,
            "q": query,
            "language": "en"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            articles = data.get("results", [])
            if not articles:
                return f"No recent news found for: {query}"

            # Build a short summary from the top 3 headlines
            summaries = []
            for article in articles[:3]:
                title = article.get("title", "")
                desc = article.get("description", "")
                summaries.append(f"- {title}\n  {desc}")

            return "\n\n".join(summaries)

        except Exception:
            return error_message

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
