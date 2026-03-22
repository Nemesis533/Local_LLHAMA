"""
@file calendar_service.py
@brief Service for calendar operations with formatting and presentation logic.

This service wraps CalendarManager to provide user-friendly calendar functionality
including reminders, appointments, and alarms with rich formatting.
"""

from datetime import datetime

from local_llhama.shared_logger import LogLevel


CLASS_PREFIX_MESSAGE = "[CalendarService]"


class CalendarService:
    """Service for calendar operations with presentation logic."""

    def __init__(self, calendar_manager):
        """
        Initialize the calendar service.

        @param calendar_manager CalendarManager instance for database operations
        """
        self.calendar = calendar_manager

    def _format_event_datetime(self, event: dict, format_long: bool = True) -> str:
        """
        @brief Format event datetime consistently.

        @param event Event dictionary with due_datetime field
        @param format_long If True, use long format ("%B %d at %I:%M %p"), else short ("%b %d at %I:%M %p")
        @return Formatted datetime string
        """
        dt = datetime.fromisoformat(event["due_datetime"])
        format_string = "%B %d at %I:%M %p" if format_long else "%b %d at %I:%M %p"
        return dt.strftime(format_string)

    def add_event(
        self,
        event_type: str,
        title: str,
        when: str,
        description: str = "",
        repeat: str = "none",
        user_id: int = None,
    ) -> str:
        """
        Add a calendar event - reminder, appointment, or alarm.

        @param event_type: Type of event - "reminder", "appointment", or "alarm"
        @param title: Event title or what to remember
        @param when: When the event occurs (e.g., "2025-12-25 09:00", "tomorrow at 15:00")
        @param description: Optional additional details
        @param repeat: Repeat pattern - "none", "daily", "weekly", "monthly", "yearly"
        @param user_id: Optional user ID for web chat users
        @return: Confirmation message
        """
        # Normalize repeat pattern - convert common variations to database values
        repeat_normalized = repeat.lower() if repeat else "none"
        if repeat_normalized in ["once", "never", "no", "single"]:
            repeat_normalized = "none"
        elif repeat_normalized not in ["none", "daily", "weekly", "monthly", "yearly"]:
            # Invalid repeat pattern, default to none
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Invalid repeat pattern '{repeat}', using 'none'"
            )
            repeat_normalized = "none"

        success, message, _ = self.calendar.add_event(
            event_type, title, when, description, repeat_normalized, user_id=user_id
        )
        return message

    def get_events(self, days: int = 7, event_type: str = None) -> str:
        """
        Get upcoming calendar events. Can filter by event type or get all events.

        @param days: Number of days to look ahead (default 7)
        @param event_type: Optional filter - "reminder", "appointment", "alarm", or None for all
        @return: Formatted list of upcoming events
        """
        events = self.calendar.get_upcoming_events(event_type=event_type, days=days)

        if not events:
            type_label = f"{event_type}s" if event_type else "events"
            return f"No {type_label} scheduled for the next {days} days."

        # Group by type if showing all
        if event_type is None:
            by_type = {"reminder": [], "appointment": [], "alarm": []}
            for event in events:
                by_type[event["event_type"]].append(event)

            result = f"Upcoming events (next {days} days):\n"
            for evt_type in ["reminder", "appointment", "alarm"]:
                if by_type[evt_type]:
                    result += f"\n{evt_type.capitalize()}s:\n"
                    for event in by_type[evt_type]:
                        formatted = self._format_event_datetime(event, format_long=True)
                        result += f"- {event['title']} - {formatted}"
                        if event["repeat_pattern"] != "none":
                            result += f" (repeats {event['repeat_pattern']})"
                        if event.get("description"):
                            result += f"\n  Details: {event['description']}"
                        result += "\n"
            return result

        # Single type view
        type_label = f"{event_type}s"
        result = f"Upcoming {type_label} (next {days} days):\n"
        for event in events:
            formatted = self._format_event_datetime(event, format_long=True)
            result += f"\n- {event['title']} - {formatted}"
            if event["repeat_pattern"] != "none":
                result += f" (repeats {event['repeat_pattern']})"
            if event.get("description"):
                result += f"\n  Details: {event['description']}"

        return result

    def manage_event(self, operation: str, search_term: str) -> str:
        """
        Complete or delete a calendar event by searching for it.

        @param operation: Action to perform - "complete" or "delete"
        @param search_term: Text to search for in event titles/descriptions
        @return: Confirmation message
        """
        # For complete, only search reminders
        event_type = "reminder" if operation == "complete" else None
        events = self.calendar.search_events(search_term, event_type=event_type)

        if not events:
            return f"No event found matching '{search_term}'."

        if len(events) > 1:
            result = f"Multiple events found for '{search_term}':\n"
            for event in events:
                formatted = self._format_event_datetime(event, format_long=True)
                result += f"\n- ID {event['id']}: {event['title']} ({event['event_type']}) - {formatted}"
            result += "\n\nPlease be more specific or use the ID."
            return result

        event = events[0]

        if operation == "complete":
            success, message = self.calendar.complete_event(event["id"])
            return f"Marked '{event['title']}' as completed."
        elif operation == "delete":
            success, message = self.calendar.delete_event(event["id"])
            return f"Deleted {event['event_type']} '{event['title']}'."
        else:
            return f"Unknown operation '{operation}'. Use 'complete' or 'delete'."

    def get_all_upcoming_events(self, days: int = 7) -> str:
        """
        Get all upcoming events (reminders, appointments, alarms) within specified days.

        @param days: Number of days to look ahead (default 7)
        @return: Formatted list of all upcoming events
        """
        events = self.calendar.get_upcoming_events(days=days)

        if not events:
            return f"No events scheduled for the next {days} days."

        result = f"Upcoming events (next {days} days):\n"
        for event in events:
            formatted = self._format_event_datetime(event, format_long=True)
            result += (
                f"\n- [{event['event_type'].upper()}] {event['title']} - {formatted}"
            )
            if event["repeat_pattern"] != "none":
                result += f" (repeats {event['repeat_pattern']})"

        return result

    def list_calendar(self, days: int = 7) -> str:
        """
        List all calendar entries including reminders, appointments, and alarms in an organized format.
        Simple function that provides a comprehensive view of the calendar.

        @param days: Number of days to look ahead (default 7)
        @return: Formatted calendar listing grouped by type
        """
        all_events = self.calendar.get_upcoming_events(
            days=days, include_completed=False
        )

        if not all_events:
            return f"Calendar is empty for the next {days} days."

        # Group events by type
        reminders = [e for e in all_events if e["event_type"] == "reminder"]
        appointments = [e for e in all_events if e["event_type"] == "appointment"]
        alarms = [e for e in all_events if e["event_type"] == "alarm"]

        result = f"CALENDAR (next {days} days):\n"

        # Show reminders
        if reminders:
            result += f"\nREMINDERS ({len(reminders)}):\n"
            for event in reminders:
                formatted = self._format_event_datetime(event, format_long=False)
                result += f"  - {event['title']} - {formatted}"
                if event["repeat_pattern"] != "none":
                    result += f" [repeats {event['repeat_pattern']}]"
                if event.get("description"):
                    result += f"\n    Details: {event['description']}"
                result += "\n"

        # Show alarms
        if alarms:
            result += f"\nALARMS ({len(alarms)}):\n"
            for event in alarms:
                formatted = self._format_event_datetime(event, format_long=False)
                result += f"  - {event['title']} - {formatted}"
                if event["repeat_pattern"] != "none":
                    result += f" [repeats {event['repeat_pattern']}]"
                result += "\n"

        # Show appointments
        if appointments:
            result += f"\nAPPOINTMENTS ({len(appointments)}):\n"
            for event in appointments:
                formatted = self._format_event_datetime(event, format_long=False)
                result += f"  - {event['title']} - {formatted}"
                if event.get("description"):
                    result += f"\n    Details: {event['description']}"
                result += "\n"

        result += f"\nTotal: {len(all_events)} event(s)"
        return result
