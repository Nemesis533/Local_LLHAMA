"""
Calendar and Reminder Manager for Local_LLHAMA
Handles appointments, alarms, and reminders using SQLite database.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ..Shared_Logger import LogLevel


class CalendarManager:
    """
    Manages calendar events, reminders, and alarms using SQLite.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize calendar manager with SQLite database.
        
        @param db_path: Path to SQLite database file. If None, uses default location.
        """
        self.class_prefix_message = "[CalendarManager]"
        if db_path is None:
            base_path = Path(__file__).parent.parent
            data_dir = base_path / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "calendar.db"
        
        self.db_path = str(db_path)
        self._init_database()
    
    def _get_connection(self):
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create reminders/events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                event_type TEXT NOT NULL CHECK(event_type IN ('reminder', 'appointment', 'alarm')),
                due_datetime TEXT NOT NULL,
                repeat_pattern TEXT CHECK(repeat_pattern IN ('none', 'daily', 'weekly', 'monthly', 'yearly')),
                is_completed BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                notification_minutes_before INTEGER DEFAULT 0
            )
        ''')
        
        # Migrate existing table if needed (add user_id column)
        cursor.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'user_id' not in columns:
            print(f"{self.class_prefix_message} {LogLevel.INFO} Migrating calendar database: adding user_id column")
            cursor.execute("ALTER TABLE events ADD COLUMN user_id INTEGER")
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_due_datetime ON events(due_datetime)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_is_completed ON events(is_completed)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_id ON events(user_id)
        ''')
        
        conn.commit()
        conn.close()
        print(f"{self.class_prefix_message} {LogLevel.INFO} Calendar database initialized")
    
    # === CREATE Operations ===
    
    def add_reminder(self, title: str, due_datetime: str, description: str = "", 
                     repeat_pattern: str = "none", notification_minutes: int = 0, user_id: int = None) -> Tuple[bool, str, int]:
        """
        Add a new reminder.
        
        @param title: Title of the reminder
        @param due_datetime: When the reminder is due (ISO format or natural language)
        @param description: Optional description
        @param repeat_pattern: 'none', 'daily', 'weekly', 'monthly', 'yearly'
        @param notification_minutes: Minutes before to notify (0 = at time)
        @param user_id: User ID for per-user calendars (None for voice-created generic entries)
        @return: Tuple (success, message, event_id)
        """
        return self._add_event('reminder', title, due_datetime, description, 
                              repeat_pattern, notification_minutes, user_id)
    
    def add_appointment(self, title: str, due_datetime: str, description: str = "",
                       notification_minutes: int = 15, user_id: int = None) -> Tuple[bool, str, int]:
        """
        Add a new appointment (non-repeating event).
        
        @param title: Title of the appointment
        @param due_datetime: When the appointment is scheduled
        @param description: Optional description
        @param notification_minutes: Minutes before to notify (default 15)
        @param user_id: User ID for per-user calendars (None for voice-created generic entries)
        @return: Tuple (success, message, event_id)
        """
        return self._add_event('appointment', title, due_datetime, description,
                              'none', notification_minutes, user_id)
    
    def add_alarm(self, title: str, due_datetime: str, repeat_pattern: str = "none", user_id: int = None) -> Tuple[bool, str, int]:
        """
        Add a new alarm.
        
        @param title: Title/label for the alarm
        @param due_datetime: When the alarm should go off
        @param repeat_pattern: 'none', 'daily', 'weekly'
        @param user_id: User ID for per-user calendars (None for voice-created generic entries)
        @return: Tuple (success, message, event_id)
        """
        return self._add_event('alarm', title, due_datetime, "", repeat_pattern, 0, user_id)
    
    def _add_event(self, event_type: str, title: str, due_datetime: str, 
                   description: str, repeat_pattern: str, notification_minutes: int, user_id: int = None) -> Tuple[bool, str, int]:
        """Internal method to add any type of event."""
        try:
            # Parse datetime
            parsed_datetime = self._parse_datetime(due_datetime)
            if not parsed_datetime:
                return False, f"Could not parse datetime: {due_datetime}", -1
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO events (user_id, title, description, event_type, due_datetime, 
                                   repeat_pattern, notification_minutes_before)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, title, description, event_type, parsed_datetime, repeat_pattern, notification_minutes))
            
            event_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            formatted_time = datetime.fromisoformat(parsed_datetime).strftime("%B %d, %Y at %I:%M %p")
            message = f"{event_type.capitalize()} '{title}' set for {formatted_time}"
            if repeat_pattern != 'none':
                message += f" (repeats {repeat_pattern})"
            
            print(f"{self.class_prefix_message} {LogLevel.INFO} {message}")
            return True, message, event_id
            
        except Exception as e:
            error_msg = f"Failed to add {event_type}: {e}"
            print(f"{self.class_prefix_message} {LogLevel.ERROR} {error_msg}")
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
        
        # Helper to parse time portion
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
                    test_dt = reference_time.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
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
                            test_dt = reference_time.replace(hour=hour, minute=0, second=0, microsecond=0)
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
                time_obj = parse_time_portion(time_part, smart_am_pm=True, reference_time=now)
                if time_obj:
                    dt = dt.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
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
                    dt = dt.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
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
                    dt = dt.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
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
                        return dt.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
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
                    match = re.match(r'(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days)', after_now)
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
    
    def get_upcoming_events(self, event_type: Optional[str] = None, 
                           days: int = 7, include_completed: bool = False, user_id: Optional[int] = None) -> List[Dict]:
        """
        Get upcoming events within specified days.
        
        @param event_type: Filter by type ('reminder', 'appointment', 'alarm') or None for all
        @param days: Number of days to look ahead
        @param include_completed: Include completed events
        @param user_id: Filter by user ID (None = all events including generic voice-created ones)
        @return: List of event dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        future = (datetime.now() + timedelta(days=days)).isoformat()
        
        query = '''
            SELECT * FROM events 
            WHERE due_datetime >= ? AND due_datetime <= ?
            AND is_active = 1
        '''
        params = [now, future]
        
        if not include_completed:
            query += ' AND is_completed = 0'
        
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        
        if user_id is not None:
            query += ' AND user_id = ?'
            params.append(user_id)
        
        query += ' ORDER BY due_datetime ASC'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_event_by_id(self, event_id: int) -> Optional[Dict]:
        """Get a specific event by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM events WHERE id = ?', (event_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def search_events(self, search_term: str, event_type: Optional[str] = None) -> List[Dict]:
        """
        Search events by title or description.
        
        @param search_term: Text to search for
        @param event_type: Optional filter by event type
        @return: List of matching events
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM events 
            WHERE (title LIKE ? OR description LIKE ?)
            AND is_active = 1
        '''
        params = [f'%{search_term}%', f'%{search_term}%']
        
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        
        query += ' ORDER BY due_datetime ASC'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # === UPDATE Operations ===
    
    def complete_event(self, event_id: int) -> Tuple[bool, str]:
        """
        Mark an event as completed.
        
        @param event_id: ID of the event to complete
        @return: Tuple (success, message)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE events 
                SET is_completed = 1, completed_at = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), event_id))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"Event {event_id} not found"
            
            conn.commit()
            conn.close()
            
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
            allowed_fields = ['title', 'description', 'due_datetime', 'repeat_pattern', 
                            'notification_minutes_before', 'is_active']
            
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == 'due_datetime':
                        value = self._parse_datetime(value)
                        if not value:
                            return False, f"Invalid datetime format"
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if not updates:
                return False, "No valid fields to update"
            
            values.append(event_id)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = f"UPDATE events SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, values)
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"Event {event_id} not found"
            
            conn.commit()
            conn.close()
            
            return True, f"Event {event_id} updated successfully"
            
        except Exception as e:
            return False, f"Failed to update event: {e}"
    
    # === DELETE Operations ===
    
    def delete_event(self, event_id: int) -> Tuple[bool, str]:
        """
        Delete an event (soft delete by setting is_active = 0).
        
        @param event_id: ID of the event to delete
        @return: Tuple (success, message)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('UPDATE events SET is_active = 0 WHERE id = ?', (event_id,))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"Event {event_id} not found"
            
            conn.commit()
            conn.close()
            
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
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE events SET is_active = 0 
                WHERE is_completed = 1 AND completed_at < ?
            ''', (cutoff,))
            
            count = cursor.rowcount
            conn.commit()
            conn.close()
            
            return True, f"Deleted {count} old completed event(s)"
            
        except Exception as e:
            return False, f"Failed to delete old events: {e}"
