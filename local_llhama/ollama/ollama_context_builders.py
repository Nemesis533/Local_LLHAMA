"""
Ollama Context Builders

This module provides context generation utilities for building LLM prompts
with device information and simple function descriptions.
"""

import json


class ContextBuilder:
    """
    Builds context information for LLM prompts including device information
    and simple function schemas.
    """

    def __init__(self, ha_client, class_prefix_message="[ContextBuilder]"):
        """
        Initialize the context builder.

        @param ha_client HomeAssistantClient instance for device context
        @param class_prefix_message Logging prefix
        """
        self.ha_client = ha_client
        self.class_prefix_message = class_prefix_message

    def generate_simple_functions_context(self):
        """
        Generate description of available simple functions from command schema.

        @return Formatted string describing available simple functions
        """
        if (
            not hasattr(self.ha_client, "simple_functions")
            or not self.ha_client.simple_functions
        ):
            return "No additional simple functions available."

        command_schema = self.ha_client.simple_functions.command_schema
        if not command_schema:
            return "No additional simple functions available."

        functions_desc = ["Available Simple Functions:"]

        for entity_id, entity_info in command_schema.items():
            actions = entity_info.get("actions", [])
            if not actions:
                continue

            description = entity_info.get(
                "description", f'Available actions: {", ".join(actions)}'
            )
            functions_desc.append(f"- {entity_id}: {description}")

            example = entity_info.get("example")
            if example:
                functions_desc.append(f"  Example: {json.dumps(example)}")
            else:
                # Fallback example if not provided
                functions_desc.append(
                    f'  Example: {{"action": "{actions[0]}", "target": "{entity_id}"}}'
                )

            parameters = entity_info.get("parameters", {})
            if parameters:
                optional_params = [
                    name
                    for name, info in parameters.items()
                    if not info.get("required", False)
                ]
                if optional_params:
                    param_desc = ", ".join([f'"{p}"' for p in optional_params])
                    functions_desc.append(f"  Optional parameters: {param_desc}")

        return (
            "\n".join(functions_desc)
            if len(functions_desc) > 1
            else "No additional simple functions available."
        )

    def get_devices_context(self):
        """
        Get device context from Home Assistant.

        @return JSON-formatted string with device information
        """
        return self.ha_client.generate_devices_prompt_fragment()
