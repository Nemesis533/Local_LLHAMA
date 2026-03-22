"""
@file automation_service.py
@brief Service for automation management and execution.

This service wraps AutomationManager to provide user-friendly automation functionality
including creation, triggering, listing, and deletion with execution logic.
"""

from local_llhama.shared_logger import LogLevel


CLASS_PREFIX_MESSAGE = "[AutomationService]"


class AutomationService:
    """Service for automation management and execution."""

    def __init__(self, automation_manager):
        """
        Initialize the automation service.

        @param automation_manager AutomationManager instance for database operations
        """
        self.automation = automation_manager

    def create_automation(
        self,
        name: str,
        actions: list = None,
        description: str = "",
        user_id: int = None,
        save_previous_commands: bool = True,
        current_request_commands: list = None,
    ) -> str:
        """
        Create a new automation sequence.

        @param name: Unique name for the automation
        @param actions: List of command dictionaries to execute (optional if using save_previous_commands)
        @param description: Optional description
        @param user_id: Optional user ID for per-user automations
        @param save_previous_commands: If True and current_request_commands provided, use those instead of actions
        @param current_request_commands: Commands from current request (injected by command processor)
        @return: Confirmation message
        """
        # If save_previous_commands is True and we have current request commands, use those
        if save_previous_commands and current_request_commands:
            # Filter out the create_automation command itself
            actions = [
                cmd
                for cmd in current_request_commands
                if cmd.get("action") != "create_automation"
            ]
            if not actions:
                return "No commands to save - create_automation was the only command in the request."

        # Fallback to provided actions parameter
        if not actions:
            return "No actions provided. Either specify actions or use save_previous_commands with other commands in the request."

        success, message, automation_id = self.automation.create_automation(
            name, actions, description, user_id
        )
        return message

    def trigger_automation(self, name: str, user_id: int = None, ha_client=None) -> str:
        """
        Trigger (execute) an existing automation by name.

        @param name: Name of the automation to run
        @param user_id: Optional user ID to filter automations
        @param ha_client: HomeAssistantClient instance for executing commands
        @return: Result message
        """
        # Get the automation
        automation = self.automation.get_automation(name, user_id)

        if not automation:
            return f"Automation '{name}' not found."

        if not ha_client:
            return "Cannot execute automation: Home Assistant client not available."

        # Execute all actions in the automation
        actions = automation.get("actions", [])
        if not actions:
            return f"Automation '{name}' has no actions to execute."

        try:
            # Build command payload
            payload = {"commands": actions}

            # Execute through HA client (which handles both HA and simple functions)
            results = ha_client.send_commands(payload, debug=True, user_id=user_id)

            # Update last triggered timestamp
            self.automation.update_last_triggered(automation["id"])

            # Build response
            success_count = sum(
                1 for r in results if isinstance(r, dict) and not r.get("error")
            )
            total_count = len(actions)

            if success_count == total_count:
                return f"Automation '{name}' executed successfully ({total_count} action(s))."
            elif success_count > 0:
                return f"Automation '{name}' partially executed ({success_count}/{total_count} actions succeeded)."
            else:
                return f"Automation '{name}' failed to execute."

        except Exception as e:
            error_msg = f"Error executing automation '{name}': {str(e)}"
            print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.ERROR.name}] {error_msg}")
            return error_msg

    def list_automations(self, user_id: int = None) -> str:
        """
        List all saved automations.

        @param user_id: Optional user ID to filter automations
        @return: Formatted list of automations
        """
        automations = self.automation.list_automations(user_id)

        if not automations:
            return "No automations found."

        result = "Your automations:\n"
        for auto in automations:
            result += f"\n- {auto['name']}"
            if auto.get("description"):
                result += f": {auto['description']}"
            result += f" ({auto['action_count']} action(s))"
            if auto.get("last_triggered"):
                result += f"\n  Last used: {auto['last_triggered']}"

        return result

    def delete_automation(self, name: str, user_id: int = None) -> str:
        """
        Delete an automation by name.

        @param name: Name of the automation to delete
        @param user_id: Optional user ID to filter automations
        @return: Confirmation message
        """
        success, message = self.automation.delete_automation(name, user_id)
        return message
