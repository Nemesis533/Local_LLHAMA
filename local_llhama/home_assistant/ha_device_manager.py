"""
Home Assistant Device Manager

Handles device discovery, entity mapping, domain actions, and home location
retrieval from Home Assistant.
"""

# === System Imports ===
import requests

# === Custom Imports ===
from ..shared_logger import LogLevel
from ..simple_functions import SimpleFunctions
from .ha_validators import HADataFormatter, HAEntityFilter


class HADeviceManager:
    """
    Manages Home Assistant devices, entities, and domain operations.

    This class handles:
    - Fetching domain actions (services)
    - Building and maintaining entity maps
    - Filtering and excluding entities
    - Retrieving home location
    - Generating device context for LLM prompts
    """

    def __init__(
        self,
        core_client,
        allowed_domains,
        exclusion_dict,
        allowed_entities,
        class_prefix_message,
    ):
        """
        Initialize the device manager.

        @param core_client HAClientCore instance for API access
        @param allowed_domains List of allowed device domains
        @param exclusion_dict Dictionary of friendly name substrings to exclude
        @param allowed_entities List of entity_ids to allow
        @param class_prefix_message Logging prefix
        """
        self.core = core_client
        self.allowed_domains = allowed_domains
        self.exclusion_dict = exclusion_dict
        self.allowed_entities = allowed_entities
        self.class_prefix_message = class_prefix_message

        # Entity map cache for fallback
        self.entity_map_cache = None

        # State
        self.domain_to_actions = {}
        self.entity_map = {}
        self.simple_functions = None

    def initialize(self, allow_internet_searches=True, pg_client=None):
        """
        Initialize the device manager by fetching HA data.

        @param allow_internet_searches Enable internet searches in simple functions
        @param pg_client PostgreSQL client for simple functions
        """
        # Get home location and validate
        home_location = self.get_home_location()
        if "error" in home_location:
            error_msg = f"Failed to get home location: {home_location['error']}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            raise AttributeError(error_msg)

        # Initialize simple functions handler with home location
        self.simple_functions = SimpleFunctions(
            home_location,
            allow_internet_searches=allow_internet_searches,
            pg_client=pg_client,
        )

        # Fetch domain actions from Home Assistant API
        self.domain_to_actions = self.fetch_domain_actions()

        # Fetch entity map, first with exclusions then filtering by allowed entities
        # The exclusion map is there pro prevent commands beign routed to entities we don't want
        # Such as a wrongly interpreted command shutting off all your UPS systems

        self.entity_map = self.fetch_entity_map(exclusion_dict=self.exclusion_dict)
        self.entity_map = self.fetch_entity_map(
            filter_mode="entity", allowed_entities=self.allowed_entities
        )

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Entity map loaded with {len(self.entity_map)} entities"
        )

    def fetch_domain_actions(self) -> dict:
        """
        Fetch all available domain actions (services) from Home Assistant.

        @return Dictionary mapping domains to a list of their supported actions,
                or an error message in case of failure.
        """
        url = f"{self.core.base_url}/api/services"

        try:
            response = self.core.request_handler.retry_request(
                "GET", url, headers=self.core.request_handler.headers
            )
            services = response.json()

            domain_to_actions = {}
            for item in services:
                domain = item["domain"]
                actions = list(item["services"].keys())
                domain_to_actions[domain] = actions

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully fetched {len(domain_to_actions)} domain actions"
            )
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
        filter_mode: str = "domain",
        allowed_entities: list = None,
    ) -> dict:
        """
        Fetch entities from Home Assistant, optionally filtered and excluded.

        @param exclusion_dict Dictionary of friendly name substrings to exclude
        @param filter_mode Filter mode: 'domain', 'entity', or 'none'
        @param allowed_entities List of entity_ids to allow if filter_mode=='entity'
        @return Dictionary mapping friendly_name to entity info and actions
        """
        try:
            url = f"{self.core.base_url}/api/states"
            response = self.core.request_handler.retry_request(
                "GET", url, headers=self.core.request_handler.headers
            )

            entities = response.json()

            exclusion_dict = exclusion_dict or {}
            allowed_entities = allowed_entities or []

            entity_map = {}

            for entity in entities:
                domain, _ = entity["entity_id"].split(".", 1)

                # Filtering logic using utility class
                if not HAEntityFilter.should_include_entity(
                    entity["entity_id"],
                    domain,
                    filter_mode,
                    self.allowed_domains,
                    allowed_entities,
                ):
                    continue

                # Get friendly_name if available, fallback to entity_id (lowercase)
                friendly_name = (
                    entity["attributes"]
                    .get("friendly_name", entity["entity_id"])
                    .lower()
                )

                if HAEntityFilter.should_exclude_entity(friendly_name, exclusion_dict):
                    continue

                # Get supported actions for the domain
                actions = self.domain_to_actions.get(domain, [])

                entity_map[friendly_name] = {
                    "entity_id": entity["entity_id"],
                    "actions": actions,
                }

            self.entity_map_cache = entity_map.copy()
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully fetched {len(entity_map)} entities"
            )
            return entity_map

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch entity map: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")

            # Try to use cached entity map as fallback
            if self.entity_map_cache:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Using cached entity map with {len(self.entity_map_cache)} entities"
                )
                return self.entity_map_cache

            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] No cached entity map available"
            )
            return {}

        except (ValueError, KeyError, TypeError) as e:
            error_msg = f"Error parsing entity map response: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")

            # Try to use cached entity map as fallback
            if self.entity_map_cache:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Using cached entity map with {len(self.entity_map_cache)} entities"
                )
                return self.entity_map_cache

            return {}

    def get_service_info(self, domain, action):
        """
        Retrieve service info for a domain and action from Home Assistant.

        @param domain Domain name (e.g., 'light')
        @param action Action name (e.g., 'turn_on')
        @return Service info dict if found, else None
        """
        try:
            url = f"{self.core.base_url}/api/services"
            response = self.core.request_handler.retry_request(
                "GET", url, headers=self.core.request_handler.headers
            )
            services = response.json()

            for item in services:
                if item["domain"] == domain:
                    return item["services"].get(action)
            return None

        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to get service info for {domain}.{action}: {e}"
            )
            return None

    def generate_devices_prompt_fragment(self):
        """
        Generate JSON fragment describing devices and their actions, necessary to provide the LLM with context.

        @return JSON-formatted string with device names and supported actions
        """
        return HADataFormatter.generate_devices_prompt_fragment(self.entity_map)

    def get_home_location(self):
        """
        Retrieve the configured home latitude and longitude from HA config.

        @return Dictionary with latitude and longitude or error message
        """
        url = f"{self.core.base_url}/api/config"
        try:
            response = self.core.request_handler.retry_request(
                "GET", url, headers=self.core.request_handler.headers
            )
            config = response.json()
            latitude = config.get("latitude")
            longitude = config.get("longitude")

            if latitude is not None and longitude is not None:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Retrieved home location: {latitude}, {longitude}"
                )
                return {"latitude": latitude, "longitude": longitude}
            else:
                error_msg = "Latitude or longitude not found in the configuration"
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] {error_msg}"
                )
                return {"error": error_msg}

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch home location: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}
        except (ValueError, KeyError) as e:
            error_msg = f"Error parsing config response: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return {"error": error_msg}
