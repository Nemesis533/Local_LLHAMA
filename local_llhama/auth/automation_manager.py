"""
Automation Manager for Local_LLHAMA
Handles creation, storage, and execution of user-defined automation sequences.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..postgresql_client import PostgreSQLClient
from ..shared_logger import LogLevel


class AutomationManager:
    """
    Manages user-defined automations - reusable sequences of actions.
    Automations can include any combination of:
    - Home Assistant device commands (turn on lights, adjust climate, etc.)
    - Calendar events (set reminders, appointments, alarms)
    - Information queries (weather, news, wikipedia)
    - Any other simple function
    """

    def __init__(self, pg_client=None):
        """
        Initialize automation manager with PostgreSQL database.

        @param pg_client: PostgreSQL_Client instance. If None, creates new one.
        """
        self.class_prefix_message = "[AutomationManager]"
        if pg_client is None:
            self.pg_client = PostgreSQLClient()
        else:
            self.pg_client = pg_client

    # === CREATE Operations ===

    def create_automation(
        self,
        name: str,
        actions: List[Dict],
        description: str = "",
        user_id: int = None,
    ) -> Tuple[bool, str, int]:
        """
        Create a new automation sequence.

        @param name: Unique name for the automation (e.g., "morning_routine", "movie_mode")
        @param actions: List of command dictionaries [{action, target, data}, ...]
        @param description: Optional description of what this automation does
        @param user_id: User ID for per-user automations (None for voice-created global automations)
        @return: Tuple (success, message, automation_id)
        """
        # Validate actions format
        if not actions or not isinstance(actions, list):
            return False, "Actions must be a non-empty list of command objects", -1

        for action in actions:
            if not isinstance(action, dict) or "action" not in action:
                return (
                    False,
                    "Each action must be a dictionary with at least an 'action' field",
                    -1,
                )

        # Convert actions to JSON
        actions_json = json.dumps(actions)

        try:
            # Check if automation with this name already exists for this user
            existing = self.pg_client.execute_read(
                """
                SELECT id FROM automations
                WHERE name = %s AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                """,
                (name, user_id, user_id),
            )

            if existing:
                return (
                    False,
                    f"Automation named '{name}' already exists. Delete it first or use a different name.",
                    -1,
                )

            result = self.pg_client.execute_write_returning_dict(
                """
                INSERT INTO automations (user_id, name, description, actions, is_active)
                VALUES (%s, %s, %s, %s::jsonb, true)
                RETURNING id
                """,
                (user_id, name, description, actions_json),
            )

            if result and "id" in result:
                automation_id = result["id"]
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Created automation '{name}' with {len(actions)} action(s)"
                )
                return (
                    True,
                    f"Automation '{name}' created successfully with {len(actions)} action(s).",
                    automation_id,
                )
            else:
                return False, "Failed to create automation", -1

        except Exception as e:
            error_msg = f"Error creating automation: {str(e)}"
            print(f"{self.class_prefix_message} [{LogLevel.ERROR.name}] {error_msg}")
            return False, error_msg, -1

    # === READ Operations ===

    def get_automation(self, name: str, user_id: int = None) -> Optional[Dict]:
        """
        Retrieve an automation by name.

        @param name: Name of the automation
        @param user_id: User ID to filter by (None for voice-created global automations)
        @return: Automation dictionary or None if not found
        """
        try:
            result = self.pg_client.execute_read(
                """
                SELECT id, user_id, name, description, actions, is_active,
                       created_at, last_triggered
                FROM automations
                WHERE name = %s AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                  AND is_active = true
                """,
                (name, user_id, user_id),
            )

            if result:
                automation = result[0]
                # Parse JSON actions back to list
                automation["actions"] = json.loads(automation["actions"])
                return automation
            return None

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Error retrieving automation: {e}"
            )
            return None

    def list_automations(self, user_id: int = None) -> List[Dict]:
        """
        List all active automations.

        @param user_id: User ID to filter by (None for all global automations)
        @return: List of automation dictionaries
        """
        try:
            results = self.pg_client.execute_read(
                """
                SELECT id, name, description, actions, created_at, last_triggered
                FROM automations
                WHERE (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                  AND is_active = true
                ORDER BY created_at DESC
                """,
                (user_id, user_id),
            )

            automations = []
            for row in results:
                automation = dict(row)
                # Parse actions to get count
                actions = json.loads(automation["actions"])
                automation["action_count"] = len(actions)
                # Don't include full actions in list view
                del automation["actions"]
                automations.append(automation)

            return automations

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Error listing automations: {e}"
            )
            return []

    # === UPDATE Operations ===

    def update_last_triggered(self, automation_id: int) -> bool:
        """
        Update the last_triggered timestamp for an automation.

        @param automation_id: ID of the automation
        @return: True if successful, False otherwise
        """
        try:
            self.pg_client.execute_write(
                """
                UPDATE automations
                SET last_triggered = %s
                WHERE id = %s
                """,
                (datetime.now().isoformat(), automation_id),
            )
            return True

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.ERROR.name}] Error updating automation: {e}"
            )
            return False

    # === DELETE Operations ===

    def delete_automation(self, name: str, user_id: int = None) -> Tuple[bool, str]:
        """
        Delete an automation by name (soft delete - sets is_active to false).

        @param name: Name of the automation to delete
        @param user_id: User ID to filter by
        @return: Tuple (success, message)
        """
        try:
            # Check if it exists
            automation = self.get_automation(name, user_id)
            if not automation:
                return False, f"Automation '{name}' not found."

            # Soft delete
            self.pg_client.execute_write(
                """
                UPDATE automations
                SET is_active = false
                WHERE name = %s AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                """,
                (name, user_id, user_id),
            )

            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Deleted automation '{name}'"
            )
            return True, f"Automation '{name}' deleted successfully."

        except Exception as e:
            error_msg = f"Error deleting automation: {str(e)}"
            print(f"{self.class_prefix_message} [{LogLevel.ERROR.name}] {error_msg}")
            return False, error_msg
