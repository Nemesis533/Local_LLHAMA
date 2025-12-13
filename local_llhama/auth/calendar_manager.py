"""
Calendar and Reminder Manager for Local_LLHAMA
Handles appointments, alarms, and reminders using PostgreSQL database.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..postgresql_client import PostgreSQLClient
from ..shared_logger import LogLevel


class CalendarManager:
    """
    Manages calendar events, reminders, and alarms using PostgreSQL.
    """

    def __init__(self, pg_client=None):
        """
        Initialize calendar manager with PostgreSQL database.

        @param pg_client: PostgreSQL_Client instance. If None, creates new one.
        """
        self.class_prefix_message = "[CalendarManager]"
        if pg_client is None:
            self.pg_client = PostgreSQLClient()
        else:
            self.pg_client = pg_client

    # === CREATE Operations ===

    def add_event(
        self,
        event_type: str,
        title: str,
        due_datetime: str,
        description: str = "",
        repeat_pattern: str = "none",
        notification_minutes: int = None,
        user_id: int = None,
    ) -> Tuple[bool, str, int]:
        """
        Add a new calendar event (reminder, appointment, or alarm).

        @param event_type: Type of event - 'reminder', 'appointment', or 'alarm'
        @param title: Title of the event
        @param due_datetime: When the event is due (ISO format or natural language)
        @param description: Optional description
        @param repeat_pattern: 'none', 'daily', 'weekly', 'monthly', 'yearly'
        @param notification_minutes: Minutes before to notify (None = use defaults)
        @param user_id: User ID for per-user calendars (None for voice-created generic entries)
        @return: Tuple (success, message, event_id)
        """
        # Set default notification minutes based on event type if not specified
        if notification_minutes is None:
            defaults = {"reminder": 0, "appointment": 15, "alarm": 0}
            notification_minutes = defaults.get(event_type, 0)

        event = self._add_event(
            event_type,
            title,
            due_datetime,
            description,
            repeat_pattern,
            notification_minutes,
            user_id,
        )

        return event

    def _add_event(
        self,
        event_type: str,
        title: str,
        due_datetime: str,
        description: str,
        repeat_pattern: str,
        notification_minutes: int,
        user_id: int = None,
    ) -> Tuple[bool, str, int]:
        """
        @brief Internal method to add any type of event.
        @param event_type Type of event (reminder, alarm, etc.)
        @param title Event title/label
        @param due_datetime Event datetime string
        @param description Event description
        @param repeat_pattern Repeat pattern ('none', 'daily', 'weekly')
        @param notification_minutes Minutes before to notify
        @param user_id User ID for per-user events
        @return Tuple (success, message, event_id)
        """
        try:
            # Parse datetime
            parsed_datetime = self._parse_datetime(due_datetime)
            if not parsed_datetime:
                return False, f"Could not parse datetime: {due_datetime}", -1

            result = self.pg_client.execute_write_returning_dict(
                """
                INSERT INTO events (user_id, title, description, event_type, due_datetime, 
                                   repeat_pattern, notification_minutes_before)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    title,
                    description,
                    event_type,
                    parsed_datetime,
                    repeat_pattern,
                    notification_minutes,
                ),
            )

            event_id = result["id"] if result else -1

            formatted_time = datetime.fromisoformat(parsed_datetime).strftime(
                "%B %d, %Y at %I:%M %p"
            )
            message = f"{event_type.capitalize()} '{title}' set for {formatted_time}"
            if repeat_pattern != "none":
                message += f" (repeats {repeat_pattern})"

            print(f"{self.class_prefix_message} {LogLevel.INFO} {message}")
            return True, message, event_id

        except Exception as e:
            error_msg = f"Failed to add {event_type}: {e}"
            print(f"{self.class_prefix_message} {LogLevel.CRITICAL} {error_msg}")
            return False, error_msg, -1

    def _parse_datetime(self, datetime_str: str) -> Optional[str]:
        """
        Parse datetime string into ISO format.
        Supports ISO format and some natural language.

        @param datetime_str: Input datetime string
        @return: ISO format datetime string or None
        """
        try:
            # Try ISO format first
            dt = datetime.fromisoformat(datetime_str)
            return dt.isoformat()
        except:
            pass

        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%d/%m/%Y %H:%M",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(datetime_str, fmt)
                return dt.isoformat()
            except:
                continue

        # Simple relative parsing
        datetime_str_lower = datetime_str.lower().strip()
        now = datetime.now()

        # Helper to parse time portion - somewhat verbose due to multiple formats but more efficient than using alternatives
        def parse_time_portion(time_str, smart_am_pm=False, reference_time=None):
            """Parse time from string like '19:00', '7:00 PM', '7pm', '19:00 hours'

            @param time_str: Time string to parse
            @param smart_am_pm: If True and no AM/PM specified, intelligently choose based on reference_time
            @param reference_time: Datetime to compare against for smart AM/PM detection
            @return: time object or None
            """
            time_str = time_str.strip()

            # Remove trailing "hours" if present
            if time_str.endswith(" hours"):
                time_str = time_str[:-6].strip()
            elif time_str.endswith("hours"):
                time_str = time_str[:-5].strip()

            # Check if AM/PM is explicitly specified
            has_am_pm = "am" in time_str.lower() or "pm" in time_str.lower()

            # Try 24-hour format first (19:00)
            try:
                parsed_time = datetime.strptime(time_str, "%H:%M").time()
                # If it's 24-hour format (>12), return as is
                if parsed_time.hour > 12:
                    return parsed_time
                # If it's <= 12 and no smart AM/PM, return as is
                if not smart_am_pm or has_am_pm:
                    return parsed_time
                # Smart AM/PM: if the time has already passed today, assume PM
                if reference_time:
                    test_dt = reference_time.replace(
                        hour=parsed_time.hour,
                        minute=parsed_time.minute,
                        second=0,
                        microsecond=0,
                    )
                    if test_dt <= reference_time and parsed_time.hour < 12:
                        # Already passed, add 12 hours for PM
                        return parsed_time.replace(hour=parsed_time.hour + 12)
                return parsed_time
            except:
                pass

            # Try 12-hour with AM/PM (7:00 PM)
            try:
                return datetime.strptime(time_str, "%I:%M %p").time()
            except:
                pass

            # Try without colon (7pm, 7am)
            try:
                return datetime.strptime(time_str, "%I%p").time()
            except:
                pass

            # Try with space (7 pm, 7 am)
            try:
                return datetime.strptime(time_str, "%I %p").time()
            except:
                pass

            # Try just the hour number (8, 9, etc.) - apply smart AM/PM
            try:
                hour = int(time_str)
                if 0 <= hour <= 23:
                    if hour > 12:
                        # Definitely 24-hour format
                        return datetime.strptime(f"{hour}:00", "%H:%M").time()
                    else:
                        # Could be 12-hour format, apply smart AM/PM if requested
                        parsed_time = datetime.strptime(f"{hour}:00", "%H:%M").time()
                        if smart_am_pm and reference_time and hour < 12:
                            test_dt = reference_time.replace(
                                hour=hour, minute=0, second=0, microsecond=0
                            )
                            if test_dt <= reference_time:
                                # Already passed, assume PM
                                return parsed_time.replace(hour=hour + 12)
                        return parsed_time
            except:
                pass

            return None

        # Handle "today at HH:MM"
        if "today" in datetime_str_lower:
            dt = now
            if "at" in datetime_str_lower:
                time_part = datetime_str_lower.split("at")[-1].strip()
                time_obj = parse_time_portion(
                    time_part, smart_am_pm=True, reference_time=now
                )
                if time_obj:
                    dt = dt.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute,
                        second=0,
                        microsecond=0,
                    )
                else:
                    return None
            else:
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            return dt.isoformat()

        # Handle "tomorrow at HH:MM"
        if "tomorrow" in datetime_str_lower:
            dt = now + timedelta(days=1)
            if "at" in datetime_str_lower:
                time_part = datetime_str_lower.split("at")[-1].strip()
                time_obj = parse_time_portion(time_part)
                if time_obj:
                    dt = dt.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute,
                        second=0,
                        microsecond=0,
                    )
                else:
                    return None
            else:
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            return dt.isoformat()

        # Handle "next week"
        if "next week" in datetime_str_lower:
            dt = now + timedelta(weeks=1)
            if "at" in datetime_str_lower:
                time_part = datetime_str_lower.split("at")[-1].strip()
                time_obj = parse_time_portion(time_part)
                if time_obj:
                    dt = dt.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute,
                        second=0,
                        microsecond=0,
                    )
                else:
                    dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            return dt.isoformat()

        # Handle "in X hours/minutes"
        if "in" in datetime_str_lower:
            parts = datetime_str_lower.split()
            try:
                idx = parts.index("in")
                if idx + 2 < len(parts):
                    amount = int(parts[idx + 1])
                    unit = parts[idx + 2].lower()

                    if "hour" in unit:
                        dt = now + timedelta(hours=amount)
                        return dt.replace(second=0, microsecond=0).isoformat()
                    elif "minute" in unit or "min" in unit:
                        dt = now + timedelta(minutes=amount)
                        return dt.replace(second=0, microsecond=0).isoformat()
                    elif "day" in unit:
                        dt = now + timedelta(days=amount)
                        return dt.replace(
                            hour=9, minute=0, second=0, microsecond=0
                        ).isoformat()
            except (ValueError, IndexError):
                pass

        # Handle "now + X minutes/hours/days" or "now+X minutes/hours/days"
        if "now" in datetime_str_lower and ("+") in datetime_str_lower:
            try:
                # Remove spaces around + for easier parsing
                datetime_str_clean = datetime_str_lower.replace(" ", "")
                # Split on 'now+'
                if "now+" in datetime_str_clean:
                    after_now = datetime_str_clean.split("now+")[1]
                    # Extract number and unit
                    import re

                    match = re.match(
                        r"(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days)",
                        after_now,
                    )
                    if match:
                        amount = int(match.group(1))
                        unit = match.group(2).lower()

                        if "day" in unit:
                            dt = now + timedelta(days=amount)
                            return dt.replace(second=0, microsecond=0).isoformat()
                        elif "hour" in unit or "hr" in unit:
                            dt = now + timedelta(hours=amount)
                            return dt.replace(second=0, microsecond=0).isoformat()
                        elif "minute" in unit or "min" in unit:
                            dt = now + timedelta(minutes=amount)
                            return dt.replace(second=0, microsecond=0).isoformat()
            except (ValueError, IndexError, AttributeError):
                pass

        return None

    # === READ Operations ===

    def get_upcoming_events(
        self,
        event_type: Optional[str] = None,
        days: int = 7,
        include_completed: bool = False,
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get upcoming events within specified days.

        @param event_type: Filter by type ('reminder', 'appointment', 'alarm') or None for all
        @param days: Number of days to look ahead
        @param include_completed: Include completed events
        @param user_id: Filter by user ID (None = all events including generic voice-created ones)
        @return: List of event dictionaries
        """
        now = datetime.now().isoformat()
        future = (datetime.now() + timedelta(days=days)).isoformat()

        query = """
            SELECT * FROM events 
            WHERE due_datetime >= %s AND due_datetime <= %s
            AND is_active = TRUE
        """
        params = [now, future]

        if not include_completed:
            query += " AND is_completed = FALSE"

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type)

        if user_id is not None:
            # Include both user-specific events AND generic voice-created events  where user_id IS NULL
            query += " AND (user_id = %s OR user_id IS NULL)"
            params.append(user_id)

        query += " ORDER BY due_datetime ASC"

        try:
            results = self.pg_client.execute_query_dict(query, tuple(params))
            return results if results else []
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to get upcoming events: {e}"
            )
            return []

    def get_event_by_id(self, event_id: int) -> Optional[Dict]:
        """
        @brief Get a specific event by ID.
        @param event_id Event ID to retrieve
        @return Event dict or None if not found
        """
        try:
            results = self.pg_client.execute_query_dict(
                "SELECT * FROM events WHERE id = %s", (event_id,)
            )
            return results[0] if results and len(results) > 0 else None
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to get event {event_id}: {e}"
            )
            return None

    def search_events(
        self, search_term: str, event_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Search events by title or description.

        @param search_term: Text to search for
        @param event_type: Optional filter by event type
        @return: List of matching events
        """
        query = """
            SELECT * FROM events 
            WHERE (title ILIKE %s OR description ILIKE %s)
            AND is_active = TRUE
        """
        params = [f"%{search_term}%", f"%{search_term}%"]

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type)

        query += " ORDER BY due_datetime ASC"

        try:
            results = self.pg_client.execute_query_dict(query, tuple(params))
            return results if results else []
        except Exception as e:
            print(
                f"{self.class_prefix_message} {LogLevel.CRITICAL} Failed to search events: {e}"
            )
            return []

    # === UPDATE Operations ===

    def complete_event(self, event_id: int) -> Tuple[bool, str]:
        """
        Mark an event as completed.

        @param event_id: ID of the event to complete
        @return: Tuple (success, message)
        """
        try:
            self.pg_client.execute_write(
                """
                UPDATE events 
                SET is_completed = TRUE, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (event_id,),
            )
            return True, f"Event {event_id} marked as completed"
        except Exception as e:
            return False, f"Failed to complete event: {e}"

    def update_event(self, event_id: int, **kwargs) -> Tuple[bool, str]:
        """
        Update an event's properties.

        @param event_id: ID of the event to update
        @param kwargs: Properties to update (title, description, due_datetime, etc.)
        @return: Tuple (success, message)
        """
        try:
            allowed_fields = [
                "title",
                "description",
                "due_datetime",
                "repeat_pattern",
                "notification_minutes_before",
                "is_active",
            ]

            updates = []
            values = []

            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == "due_datetime":
                        value = self._parse_datetime(value)
                        if not value:
                            return False, f"Invalid datetime format"
                    updates.append(f"{key} = %s")
                    values.append(value)

            if not updates:
                return False, "No valid fields to update"

            values.append(event_id)
            query = f"UPDATE events SET {', '.join(updates)} WHERE id = %s"

            self.pg_client.execute_write(query, tuple(values))
            return True, f"Event {event_id} updated successfully"

        except Exception as e:
            return False, f"Failed to update event: {e}"

    # === DELETE Operations ===

    def delete_event(self, event_id: int) -> Tuple[bool, str]:
        """
        Delete an event (soft delete by setting is_active = FALSE).

        @param event_id: ID of the event to delete
        @return: Tuple (success, message)
        """
        try:
            self.pg_client.execute_write(
                "UPDATE events SET is_active = FALSE WHERE id = %s", (event_id,)
            )
            return True, f"Event {event_id} deleted successfully"
        except Exception as e:
            return False, f"Failed to delete event: {e}"

    def delete_completed_events(self, days_old: int = 30) -> Tuple[bool, str]:
        """
        Delete completed events older than specified days.

        @param days_old: Delete events completed more than this many days ago
        @return: Tuple (success, message with count)
        """
        try:
            cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()

            result = self.pg_client.execute_write(
                """
                UPDATE events SET is_active = FALSE 
                WHERE is_completed = TRUE AND completed_at < %s
                RETURNING id
                """,
                (cutoff,),
            )

            count = len(result) if result else 0
            return True, f"Deleted {count} old completed event(s)"
        except Exception as e:
            return False, f"Failed to delete old events: {e}"
