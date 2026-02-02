"""
Home Assistant Command Executor

Handles sending commands to Home Assistant devices and executing simple functions.
Includes validation and error handling for command execution.
"""

# === System Imports ===
import requests

# === Custom Imports ===
from ..shared_logger import LogLevel
from .ha_validators import HADataFormatter, HAServiceValidator


class HACommandExecutor:
    """
    Executes commands to Home Assistant devices and simple functions.
    Simple functions are non-Home Assistant commands handled internally to simplify LLM prompts.

    This class handles:
    - Command validation and execution
    - Simple function routing
    - Service parameter validation
    - Command result formatting
    """

    def __init__(self, core_client, device_manager, class_prefix_message):
        """
        Initialize the command executor.

        @param core_client HAClientCore instance for API access
        @param device_manager HADeviceManager instance for device info
        @param class_prefix_message Logging prefix
        """
        self.core = core_client
        self.device_manager = device_manager
        self.class_prefix_message = class_prefix_message

    def send_commands(self, payload: dict, debug: bool = True, user_id: int = None):
        """
        Send commands to Home Assistant devices or handle simple functions.

        @param payload Dictionary containing 'commands' list
        @param debug Enable debug prints
        @param user_id Optional user ID for calendar/user-specific operations
        @return List of results for each command or None
        """
        results = []
        all_commands = payload.get("commands", [])

        for command in all_commands:
            action = command.get("action", "").replace(" ", "_")
            target = command.get("target", "").lower()
            extra_data = command.get("data", {})

            if debug:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing command: action={action}, target={target}, data={extra_data}"
                )

            # Check if this command matches a simple function (non-HA); this allows adding simple functions easily
            # And from the LLM's perspective, they are just commands that is can call
            simple_action = self.device_manager.simple_functions.find_matching_action(
                command_json=command
            )

            if simple_action is None:
                # Handle Home Assistant command
                result = self._execute_ha_command(action, target, extra_data, debug)
                results.append(result)
            else:
                # Handle simple function
                # Get display name for UI
                display_name = self.device_manager.simple_functions.get_display_name(
                    simple_action
                )
                result = self._execute_simple_function(
                    simple_action,
                    target,
                    action,
                    extra_data,
                    user_id,
                    display_name,
                    all_commands,
                )
                results.append(result)

        if debug:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] All command results: {results}"
            )

        return results if results else None

    def _execute_ha_command(
        self, action: str, target: str, extra_data: dict, debug: bool
    ) -> dict:
        """
        Execute a Home Assistant command.

        @param action The action to perform
        @param target The target entity
        @param extra_data Additional data for the command
        @param debug Enable debug prints
        @return Command result dictionary
        """
        # Lookup entity info in the map
        entity_info = self.device_manager.entity_map.get(target)

        if not entity_info:
            # Unknown target error
            return HADataFormatter.format_command_result(
                target, action, error=f"Unknown target: {target}"
            )

        # Validate action using utility class
        is_valid, error_msg = HAServiceValidator.validate_action_for_entity(
            action, entity_info
        )
        if not is_valid:
            return HADataFormatter.format_command_result(
                target, action, error=error_msg
            )

        domain = entity_info["entity_id"].split(".")[0]

        # Get service info to validate required fields
        service_info = self.device_manager.get_service_info(domain, action)

        # Validate required fields using utility class
        is_valid, missing_fields = HAServiceValidator.validate_required_fields(
            service_info, extra_data
        )
        if not is_valid:
            return HADataFormatter.format_command_result(
                target,
                action,
                error=f"Missing required fields for action '{action}': {missing_fields}",
            )

        # Prepare request URL and payload for the service call
        url = f"{self.core.base_url}/api/services/{domain}/{action}"
        payload_data = {"entity_id": entity_info["entity_id"], **extra_data}

        try:
            response = self.core.request_handler.retry_request(
                "POST",
                url,
                headers=self.core.request_handler.headers,
                json=payload_data,
            )
            response_data = response.json() if response.content else {}

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Command executed: {action} on {target}"
            )

            return HADataFormatter.format_command_result(
                target,
                action,
                success=True,
                status=response.status_code,
                response=response_data,
            )

        except requests.exceptions.RequestException as e:
            # HTTP request failed after retries
            error_msg = f"Failed to execute command after retries: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return HADataFormatter.format_command_result(
                target,
                action,
                error=error_msg,
                url=url,
                payload=payload_data,
            )

        except ValueError as e:  # JSON decoding error
            error_msg = f"Failed to parse response JSON: {e}"
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
            return HADataFormatter.format_command_result(
                target,
                action,
                error=error_msg,
                status=response.status_code,
                response=response.text,
            )

    def _execute_simple_function(
        self,
        simple_action: str,
        target: str,
        action: str,
        extra_data: dict,
        user_id: int = None,
        display_name: str = None,
        all_commands: list = None,
    ) -> dict:
        """
        Execute a simple function (non-Home Assistant command).

        @param simple_action The simple function name
        @param target The target entity
        @param action The action name
        @param extra_data Additional data for the function
        @param user_id Optional user ID for calendar/user-specific operations
        @param display_name Optional display name for UI
        @param all_commands All commands in the current request (for create_automation)
        @return Command result dictionary
        """
        # Inject user_id for calendar functions
        if simple_action == "add_event" and user_id is not None:
            extra_data["user_id"] = user_id

        # Inject user_id for memory search functions
        if simple_action == "find_in_memory" and user_id is not None:
            extra_data["user_id"] = user_id

        # Inject user_id for Wikipedia to enable memory fallback
        if simple_action == "get_wikipedia_summary" and user_id is not None:
            extra_data["user_id"] = user_id

        # Inject user_id and ha_client for automation functions
        if simple_action in [
            "create_automation",
            "trigger_automation",
            "list_automations",
            "delete_automation",
        ]:
            if user_id is not None:
                extra_data["user_id"] = user_id
            # For create_automation, inject all commands from current request
            if simple_action == "create_automation" and all_commands:
                extra_data["current_request_commands"] = all_commands
            # For trigger_automation, pass the HA client so it can execute the stored actions
            if simple_action == "trigger_automation":
                extra_data["ha_client"] = self.device_manager.ha_client

        # Call the simple function corresponding to the action - this too simplifies LLM prompts
        result = self.device_manager.simple_functions.call_function_by_name(
            simple_action, **extra_data
        )

        return HADataFormatter.format_command_result(
            target,
            action,
            success=True,
            response=result,
            type="simple_function",
            display_name=display_name,
        )
