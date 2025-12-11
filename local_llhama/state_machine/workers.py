"""
State Machine Worker Threads

This module contains the worker thread implementations that run in the background
to handle asynchronous tasks like sound playback, command processing, and
calendar checking.
"""

# === System Imports ===
import time
from datetime import datetime, timedelta
from queue import Empty

# === Custom Imports ===
from ..Audio_Output import SoundActions
from ..ollama import OllamaClient
from ..Shared_Logger import LogLevel
from .core_state import State


class WorkerThreads:
    """
    Manages worker thread implementations for the state machine.

    Worker threads run in the background and handle:
    - Sound playback
    - Command processing
    - Calendar reminder checking
    """

    def __init__(self, state_machine_instance):
        """
        Initialize worker threads manager.

        @param state_machine_instance Reference to the parent StateMachineInstance
        """
        self.sm = state_machine_instance
        self.class_prefix_message = state_machine_instance.class_prefix_message

    def sound_player_worker(self):
        """
        Background thread that plays queued sound actions asynchronously.
        """
        while not self.sm.thread_manager.is_stopping():
            try:
                sound_action = self.sm.queue_manager.sound_action_queue.get(timeout=1)
                if sound_action is None:
                    continue
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Playing sound: {sound_action}"
                )
                self.sm.audio_manager.sound_player.play(sound_action)
            except Empty:
                continue
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Sound player worker error: {type(e).__name__}: {e}"
                )
                time.sleep(0.5)

    def command_worker(self):
        """
        Thread worker that processes transcriptions - delegates to state handlers.
        """
        current_state = self.sm.state_manager.get_state()
        if current_state == State.PARSING_VOICE:
            self.sm.state_handlers._command_worker()

    def calendar_checker_worker(self):
        """
        Background thread that checks for due reminders/alarms and plays notification sound.
        """
        # Track which events have already triggered to avoid repeated notifications
        triggered_events = set()

        while not self.sm.thread_manager.is_stopping():
            try:
                # Check if ha_client has simple_functions with calendar
                if not hasattr(self.sm.ha_client, "simple_functions") or not hasattr(
                    self.sm.ha_client.simple_functions, "calendar"
                ):
                    time.sleep(60)  # Wait a minute before checking again
                    continue

                calendar_manager = self.sm.ha_client.simple_functions.calendar
                now = datetime.now()

                # Get events that might be due now
                # Check window: 60 seconds in the past to 30 seconds in the future
                lookback_time = (now - timedelta(seconds=60)).isoformat()
                lookahead_time = (now + timedelta(seconds=30)).isoformat()

                query = """
                    SELECT * FROM events 
                    WHERE due_datetime >= %s AND due_datetime <= %s
                    AND is_active = TRUE
                    AND is_completed = FALSE
                    AND event_type IN ('reminder', 'alarm')
                    ORDER BY due_datetime ASC
                """

                try:
                    results = calendar_manager.pg_client.execute_query_dict(
                        query, (lookback_time, lookahead_time)
                    )
                    upcoming_events = results if results else []
                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to query calendar events: {repr(e)}"
                    )
                    time.sleep(30)
                    continue

                for event in upcoming_events:
                    event_id = event["id"]
                    event_type = event["event_type"]

                    # Only process reminders and alarms
                    if event_type not in ["reminder", "alarm"]:
                        continue

                    # Skip if already triggered
                    if event_id in triggered_events:
                        continue

                    # Parse event due time
                    try:
                        due_time = datetime.fromisoformat(event["due_datetime"])
                    except:
                        continue

                    # Check if event is due NOW
                    grace_period = timedelta(seconds=90)
                    time_until_due = (due_time - now).total_seconds()

                    # Debug log to help troubleshoot
                    if (
                        event_type in ["reminder", "alarm"]
                        and time_until_due > -300
                        and time_until_due < 300
                    ):
                        is_within_grace = now >= due_time and now <= (
                            due_time + grace_period
                        )
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Checking {event_type} '{event['title']}': due at {due_time.strftime('%H:%M:%S')}, now is {now.strftime('%H:%M:%S')}, time_until_due={time_until_due:.1f}s, already_triggered={event_id in triggered_events}, will_trigger={is_within_grace and event_id not in triggered_events}"
                        )

                    # Only trigger if the due time has passed (or is now) but not too long ago
                    if now >= due_time and now <= (due_time + grace_period):
                        # Play reminder sound
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] {event_type.capitalize()} TRIGGERED: {event['title']} (due at {due_time.strftime('%H:%M:%S')}, triggered at {now.strftime('%H:%M:%S')})"
                        )
                        self.sm.play_sound(SoundActions.reminder)
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Sound queued for playback"
                        )

                        # Mark as triggered
                        triggered_events.add(event_id)

                        # Send chat notification if event has user_id
                        self._send_calendar_notification(event, event_type, due_time)

                        # If it's a one-time event, mark as completed
                        if event.get("repeat_pattern") == "none":
                            calendar_manager.complete_event(event_id)

                        # Send reminder notification to web server
                        self._send_reminder_to_web(event, event_type)

                # Clean up old triggered events (older than 5 minutes)
                self._cleanup_triggered_events(triggered_events, calendar_manager, now)

                # Check every 30 seconds
                time.sleep(30)

            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Calendar checker error: {type(e).__name__}: {e}"
                )
                time.sleep(60)  # Wait longer on error

    def _send_calendar_notification(self, event, event_type, due_time):
        """
        Send calendar notification to user via chat.

        @param event Event dictionary
        @param event_type Type of event (reminder/alarm)
        @param due_time Event due time
        """
        user_id = event.get("user_id")
        if user_id and isinstance(self.sm.command_llm, OllamaClient):
            try:
                event_description = event.get("description", "")
                llm_input = f"""Calendar Event Reminder:
- Type: {event_type}
- Title: {event['title']}
- Time: {due_time.strftime('%I:%M %p')}
{f"- Description: {event_description}" if event_description else ''}

Create a friendly reminder message for this calendar event."""

                # Get natural language response from LLM
                nl_output = self.sm.command_llm.send_message(
                    llm_input, message_type="response", from_chat=True
                )

                if nl_output and nl_output.get("nl_response"):
                    notification_message = (
                        f"[Chat Handler] [LLM Reply]: {nl_output.get('nl_response')}"
                    )
                    self.sm.message_handler.send_to_web_server(
                        notification_message, client_id=str(user_id)
                    )
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Sent calendar notification to user {user_id}"
                    )
            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send chat notification: {type(e).__name__}: {e}"
                )

    def _send_reminder_to_web(self, event, event_type):
        """
        Send reminder notification to web server.

        @param event Event dictionary
        @param event_type Type of event
        """
        try:
            reminder_message = {
                "type": "reminder",
                "title": event["title"],
                "description": event.get("description", ""),
                "event_type": event_type,
                "due_time": event["due_datetime"],
            }
            self.sm.message_handler.send_to_web_server(reminder_message)
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to send reminder notification: {e}"
            )

    def _cleanup_triggered_events(self, triggered_events, calendar_manager, now):
        """
        Clean up old triggered events from the tracking set.

        @param triggered_events Set of triggered event IDs
        @param calendar_manager Calendar manager instance
        @param now Current datetime
        """
        cleanup_time = now - timedelta(minutes=5)
        events_to_remove = set()

        for event_id in triggered_events:
            event = calendar_manager.get_event_by_id(event_id)
            if event:
                try:
                    due_time = datetime.fromisoformat(event["due_datetime"])
                    if due_time < cleanup_time:
                        events_to_remove.add(event_id)
                except:
                    events_to_remove.add(event_id)
            else:
                events_to_remove.add(event_id)

        triggered_events -= events_to_remove
