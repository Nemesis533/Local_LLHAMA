# Calendar, Appointment, Alarm & Reminder System

## Overview

The Local_LLHAMA system now includes a comprehensive calendar management system that allows the LLM to create and manage reminders, appointments, and alarms through natural conversation.

## Features

- **Reminders**: Set one-time or recurring reminders with optional descriptions
- **Appointments**: Schedule appointments with notification lead times
- **Alarms**: Set one-time or recurring alarms
- **Natural Language**: Parse common datetime formats and relative times
- **Search & Manage**: Find, complete, update, and delete events
- **SQLite Backend**: No external dependencies, persistent storage

## Architecture

### Database Structure

**Location**: `local_llhama/data/calendar.db`

**Table**: `events`
- `id` - Unique event identifier
- `title` - Event name/description
- `description` - Optional detailed description
- `event_type` - 'reminder', 'appointment', or 'alarm'
- `due_datetime` - ISO format datetime when event occurs
- `repeat_pattern` - 'none', 'daily', 'weekly', 'monthly', 'yearly'
- `is_completed` - Boolean completion status
- `is_active` - Boolean soft-delete flag
- `created_at` - Creation timestamp
- `completed_at` - Completion timestamp
- `notification_minutes_before` - Minutes before event to notify

### Components

1. **CalendarManager** (`local_llhama/auth/calendar_manager.py`)
   - Low-level SQLite operations
   - CRUD operations for events
   - Datetime parsing and validation

2. **SimpleFunctions Integration** (`local_llhama/Simple_Functions.py`)
   - High-level functions callable by LLM
   - Natural language interface
   - Formatted responses for voice output

## Available Functions

### For LLM to Call

#### 1. `add_reminder(title, when, description="", repeat="none")`
Create a new reminder.

**Parameters:**
- `title` (str): What to be reminded about
- `when` (str): When to remind - supports ISO format or natural language
- `description` (str, optional): Additional details
- `repeat` (str, optional): "none", "daily", "weekly", "monthly", "yearly"

**Examples:**
```python
add_reminder("Take medication", "2025-12-25 09:00", "Vitamin D supplement", "daily")
add_reminder("Team meeting", "tomorrow at 14:00", "Discuss Q4 results")
```

**Voice Commands:**
- "Remind me to take medication tomorrow at 9am"
- "Set a daily reminder to take my vitamins at 9am"
- "Create a reminder for the team meeting tomorrow at 2pm"

---

#### 2. `add_appointment(title, when, description="")`
Schedule an appointment (non-repeating, 15-minute notification).

**Parameters:**
- `title` (str): Appointment title
- `when` (str): When scheduled
- `description` (str, optional): Appointment details

**Examples:**
```python
add_appointment("Doctor checkup", "2025-12-25 14:30", "Annual physical with Dr. Smith")
add_appointment("Client meeting", "next week at 10:00")
```

**Voice Commands:**
- "Schedule a doctor appointment for December 25th at 2:30pm"
- "Add appointment for client meeting next week at 10am"

---

#### 3. `add_alarm(title, when, repeat="none")`
Set an alarm.

**Parameters:**
- `title` (str): Alarm label
- `when` (str): When alarm goes off
- `repeat` (str, optional): "none", "daily", "weekly"

**Examples:**
```python
add_alarm("Wake up", "2025-12-25 07:00", "daily")
add_alarm("Morning workout", "tomorrow at 06:30")
```

**Voice Commands:**
- "Set a daily alarm for 7am"
- "Create an alarm for tomorrow at 6:30am for my workout"

---

#### 4. `get_upcoming_reminders(days=7)`
List upcoming reminders.

**Parameters:**
- `days` (int, optional): Days to look ahead (default 7)

**Returns:** Formatted string of reminders

**Voice Commands:**
- "What are my upcoming reminders?"
- "Show me reminders for the next 7 days"
- "List my reminders"

---

#### 5. `get_upcoming_appointments(days=7)`
List upcoming appointments.

**Parameters:**
- `days` (int, optional): Days to look ahead (default 7)

**Returns:** Formatted string of appointments

**Voice Commands:**
- "What appointments do I have this week?"
- "Show my schedule for the next 7 days"
- "List my appointments"

---

#### 6. `get_alarms()`
List all active alarms.

**Returns:** Formatted string of alarms

**Voice Commands:**
- "What alarms do I have set?"
- "Show me my alarms"
- "List all alarms"

---

#### 7. `get_all_upcoming_events(days=7)`
Get all events (reminders, appointments, alarms).

**Parameters:**
- `days` (int, optional): Days to look ahead (default 7)

**Returns:** Formatted string of all events

**Voice Commands:**
- "What's on my calendar?"
- "Show me all my upcoming events"
- "What do I have scheduled this week?"

---

#### 8. `complete_reminder(search_term)`
Mark a reminder as completed.

**Parameters:**
- `search_term` (str): Text to search for in reminder titles

**Returns:** Confirmation message

**Voice Commands:**
- "Mark the medication reminder as done"
- "Complete my team meeting reminder"
- "I finished the groceries reminder"

---

#### 9. `delete_reminder(search_term)`
Delete any event (reminder, appointment, or alarm).

**Parameters:**
- `search_term` (str): Text to search for in event titles

**Returns:** Confirmation message

**Voice Commands:**
- "Delete my morning workout alarm"
- "Cancel the doctor appointment"
- "Remove the team meeting reminder"

---

## Datetime Format Support

The system accepts multiple datetime formats:

### ISO Format (Recommended)
- `"2025-12-25 14:30:00"`
- `"2025-12-25 14:30"`
- `"2025-12-25T14:30:00"`

### Common Formats
- `"12/25/2025 14:30"`
- `"25/12/2025 14:30"`

### Natural Language (Basic)
- `"tomorrow at 14:00"`
- `"tomorrow at 2:30pm"`
- `"next week"`

**Note**: More complex natural language parsing can be added as needed.

## Usage Examples

### User: "Remind me to call mom tomorrow at 3pm"
LLM calls:
```python
add_reminder("Call mom", "tomorrow at 15:00")
```
Response: "Reminder 'Call mom' set for December 24, 2025 at 03:00 PM"

---

### User: "What's on my schedule today?"
LLM calls:
```python
get_all_upcoming_events(days=1)
```
Response: Lists all events for today

---

### User: "Set a daily alarm for 6:30am"
LLM calls:
```python
add_alarm("Morning alarm", "tomorrow at 06:30", "daily")
```
Response: "Alarm 'Morning alarm' set for December 24, 2025 at 06:30 AM (repeats daily)"

---

### User: "I finished my workout"
LLM calls:
```python
complete_reminder("workout")
```
Response: "Marked 'Morning workout' as completed."

---

## Testing

Run the test script:
```bash
python test_calendar.py
```

This tests:
- Adding reminders, appointments, alarms
- Retrieving upcoming events
- Searching events
- Completing and updating events
- Deleting events
- SimpleFunctions integration

## Integration with LLM

The LLM can access these functions through the `SimpleFunctions` class instance that's available in the Home Assistant Interface. The functions are designed to:

1. Accept natural language inputs
2. Return human-readable responses suitable for voice output
3. Handle errors gracefully
4. Provide clear confirmation messages

## Database Management

### Backup
```bash
cp local_llhama/data/calendar.db local_llhama/data/calendar.db.backup
```

### Clear All Events
Delete the database file and restart the system:
```bash
rm local_llhama/data/calendar.db
```

### View Events Directly
```bash
sqlite3 local_llhama/data/calendar.db "SELECT * FROM events WHERE is_active=1 ORDER BY due_datetime;"
```

## Future Enhancements

Potential additions:
- Email/SMS notifications at event time
- Google Calendar sync
- More sophisticated natural language parsing
- Recurring event exceptions
- Event categories/tags
- Location-based reminders
- Snooze functionality
- Voice notifications through TTS

## Security Notes

- Database stored locally in `data/` directory
- No external API dependencies
- All data remains on the local system
- Soft deletes preserve history
- No authentication required (uses system's existing auth)
