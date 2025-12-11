"""
Home Assistant Validation Utilities

Provides filtering, validation, and data formatting for Home Assistant entities
and service calls.
"""

# === System Imports ===
import json


class HAEntityFilter:
    """
    Provides filtering and exclusion logic for Home Assistant entities.

    Handles entity filtering based on domains, explicit entity lists, and
    exclusion patterns based on friendly names.
    """

    @staticmethod
    def should_exclude_entity(friendly_name: str, exclusion_dict: dict) -> bool:
        """
        Check if an entity should be excluded based on its friendly name.

        @param friendly_name The entity's friendly name
        @param exclusion_dict Dictionary of exclusion patterns
        @return True if entity should be excluded, False otherwise
        """
        if not exclusion_dict:
            return False
        return any(
            excluded_name.lower() in friendly_name.lower()
            for excluded_name in exclusion_dict.values()
        )

    @staticmethod
    def should_include_entity(
        entity_id: str,
        domain: str,
        filter_mode: str,
        allowed_domains: list,
        allowed_entities: list,
    ) -> bool:
        """
        Check if an entity should be included based on filter mode.

        @param entity_id The entity's ID
        @param domain The entity's domain
        @param filter_mode Filter mode: 'domain', 'entity', or 'none'
        @param allowed_domains List of allowed domains
        @param allowed_entities List of allowed entity IDs
        @return True if entity should be included, False otherwise
        """
        if filter_mode == "domain":
            return domain in allowed_domains
        elif filter_mode == "entity":
            return entity_id in allowed_entities
        elif filter_mode == "none":
            return True
        else:
            raise ValueError(f"Invalid filter_mode: {filter_mode}")


class HADataFormatter:
    """
    Formats Home Assistant data for display and processing.

    Provides utility methods to format entity maps, service information,
    and generate prompt fragments for LLM interactions.
    """

    @staticmethod
    def generate_devices_prompt_fragment(entity_map: dict) -> str:
        """
        Generate JSON fragment describing devices and their actions.

        @param entity_map Dictionary mapping entity names to their information
        @return JSON-formatted string with device names and supported actions
        """
        devices = {}
        for name, info in entity_map.items():
            # Replace underscores with spaces for readability in action names
            actions = [action.replace("_", " ") for action in info["actions"]]
            devices[name] = actions
        return json.dumps({"devices": devices}, indent=2)

    @staticmethod
    def format_command_result(
        target: str, action: str, success: bool = None, error: str = None, **kwargs
    ) -> dict:
        """
        Format a command execution result consistently.

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
    Validates Home Assistant service calls and parameters.

    Checks if actions are supported by entities and validates required
    parameters for service calls.
    """

    @staticmethod
    def validate_action_for_entity(action: str, entity_info: dict) -> tuple:
        """
        Validate if an action is supported for an entity.

        @param action The action to validate
        @param entity_info Entity information dictionary
        @return Tuple of (is_valid, error_message)
        """
        if action not in entity_info.get("actions", []):
            return False, f"Action '{action}' not supported for this entity"
        return True, None

    @staticmethod
    def validate_required_fields(service_info: dict, extra_data: dict) -> tuple:
        """
        Validate that all required fields are present for a service call.

        @param service_info Service information from Home Assistant
        @param extra_data Data provided for the service call
        @return Tuple of (is_valid, list_of_missing_fields)
        """
        if not service_info:
            return True, []

        missing_fields = []
        required_fields = service_info.get("fields", {}).keys()

        for field in required_fields:
            if field == "entity_id":
                continue
            if (
                service_info["fields"][field].get("required", False)
                and field not in extra_data
            ):
                missing_fields.append(field)

        return len(missing_fields) == 0, missing_fields
