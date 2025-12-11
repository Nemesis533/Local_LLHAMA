"""
Home Assistant Integration Module

This module provides a clean interface for interacting with Home Assistant.
It handles device management, command execution, and service validation.

Main Components:
- HomeAssistantClient: Main client interface (facade)
- HAClientCore: Connection management and configuration
- HADeviceManager: Device/domain/entity operations
- HACommandExecutor: Command sending and execution logic
- HAServiceValidator: Service validation utilities

Usage:
    from local_llhama.home_assistant import HomeAssistantClient

    # Initialize the client
    ha_client = HomeAssistantClient()
    ha_client.initialize_HA()

    # Send commands
    payload = {"commands": [{"action": "turn_on", "target": "kitchen light"}]}
    results = ha_client.send_commands(payload)
"""

import json
import os

from ..Shared_Logger import LogLevel
from .ha_client_core import HAClientCore, HARequestHandler
from .ha_command_executor import HACommandExecutor
from .ha_device_manager import HADeviceManager
from .ha_validators import HADataFormatter, HAEntityFilter, HAServiceValidator


# Main facade class for backward compatibility
class HomeAssistantClient:
    """
    Facade class that provides a unified interface to the Home Assistant subsystem.

    This class coordinates between the core client, device manager, and command executor
    to provide a simple API for interacting with Home Assistant.
    """

    def __init__(self):
        """Initialize the Home Assistant client facade."""
        self.class_prefix_message = "[HomeAssistant]"

        # Load settings from object_settings.json
        settings = self._load_settings()

        # Get configuration from settings
        self.ALLOWED_DOMAINS = settings.get("ALLOWED_DOMAINS", [])
        exclusion_dict = settings.get("exclusion_dict", {})
        allowed_entities = settings.get("allowed_entities", [])

        # Initialize core components
        self.core = HAClientCore()
        self.device_manager = HADeviceManager(
            self.core,
            self.ALLOWED_DOMAINS,
            exclusion_dict,
            allowed_entities,
            self.class_prefix_message,
        )
        self.command_executor = HACommandExecutor(
            self.core, self.device_manager, self.class_prefix_message
        )

        # Expose commonly used attributes for backward compatibility
        self.base_url = self.core.base_url
        self.token = self.core.token
        self.timeout = self.core.timeout
        self.max_retries = self.core.max_retries
        self.retry_delay = self.core.retry_delay
        self.request_handler = self.core.request_handler
        self.exclusion_dict = self.device_manager.exclusion_dict
        self.allowed_entities = self.device_manager.allowed_entities

    def _load_settings(self):
        """
        Load HomeAssistantClient settings from system_settings.json.

        @return Dictionary with ALLOWED_DOMAINS, exclusion_dict, and allowed_entities
        """
        # Get the base path (go up from home_assistant/ to local_llhama/)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_path = os.path.join(base_path, "settings", "system_settings.json")

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ha_settings = data.get("home_assistant", {})

            # Extract values with defaults
            allowed_domains = ha_settings.get("allowed_domains", {}).get(
                "value",
                ["light", "climate", "switch", "fan", "media_player", "thermostat"],
            )
            exclusion_dict = ha_settings.get("exclusion_dict", {}).get("value", {})
            allowed_entities = ha_settings.get("allowed_entities", {}).get("value", [])

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loaded settings: {len(allowed_domains)} domains, {len(exclusion_dict)} exclusions, {len(allowed_entities)} allowed entities"
            )

            return {
                "ALLOWED_DOMAINS": allowed_domains,
                "exclusion_dict": exclusion_dict,
                "allowed_entities": allowed_entities,
            }

        except FileNotFoundError:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Settings file not found, using defaults"
            )
            return {
                "ALLOWED_DOMAINS": [
                    "light",
                    "climate",
                    "switch",
                    "fan",
                    "media_player",
                    "thermostat",
                ],
                "exclusion_dict": {},
                "allowed_entities": [],
            }
        except (json.JSONDecodeError, KeyError) as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse settings: {e}"
            )
            return {
                "ALLOWED_DOMAINS": [
                    "light",
                    "climate",
                    "switch",
                    "fan",
                    "media_player",
                    "thermostat",
                ],
                "exclusion_dict": {},
                "allowed_entities": [],
            }

    def initialize_HA(self, allow_internet_searches=True, pg_client=None):
        """
        Initialize Home Assistant connection and fetch device information.

        @param allow_internet_searches Enable internet searches in simple functions
        @param pg_client PostgreSQL client for simple functions
        """
        self.device_manager.initialize(allow_internet_searches, pg_client)

        # Expose entity map and domain actions for backward compatibility
        self.entity_map = self.device_manager.entity_map
        self.domain_to_actions = self.device_manager.domain_to_actions
        self.simple_functions = self.device_manager.simple_functions

    def fetch_domain_actions(self):
        """Fetch all available domain actions from Home Assistant."""
        return self.device_manager.fetch_domain_actions()

    def fetch_entity_map(
        self, exclusion_dict=None, filter_mode="domain", allowed_entities=None
    ):
        """Fetch entities from Home Assistant with optional filtering."""
        return self.device_manager.fetch_entity_map(
            exclusion_dict, filter_mode, allowed_entities
        )

    def send_commands(self, payload, debug=True, user_id=None):
        """Send commands to Home Assistant devices or handle simple functions."""
        return self.command_executor.send_commands(payload, debug, user_id)

    def get_service_info(self, domain, action):
        """Retrieve service info for a domain and action."""
        return self.device_manager.get_service_info(domain, action)

    def generate_devices_prompt_fragment(self):
        """Generate JSON fragment describing devices and their actions."""
        return self.device_manager.generate_devices_prompt_fragment()

    def get_home_location(self):
        """Retrieve the configured home latitude and longitude."""
        return self.device_manager.get_home_location()


__all__ = [
    "HomeAssistantClient",
    "HAClientCore",
    "HADeviceManager",
    "HACommandExecutor",
    "HARequestHandler",
    "HAServiceValidator",
    "HADataFormatter",
    "HAEntityFilter",
]
