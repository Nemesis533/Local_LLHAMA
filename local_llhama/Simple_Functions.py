# === System Imports ===
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# === Custom Imports ===
from .Shared_Logger import LogLevel
from .auth.calendar_manager import CalendarManager


class SimpleFunctions:
    """
    @class SimpleFunctions
    @brief Implements additional non-Home Assistant commands and utilities.

    Handles tasks like weather info, news lookups, Wikipedia queries, and other logic outside HA.
    """

    def __init__(self, home_location, command_schema_path=None, allow_internet_searches=True, pg_client=None):
        """
        @brief Initialize with home location.
        @param home_location Dictionary with 'latitude' and 'longitude'.
        @param command_schema_path Optional path to command schema file.
        @param allow_internet_searches Whether to allow internet-based searches (Wikipedia, news, etc.)
        @param pg_client PostgreSQL_Client instance for calendar operations.
        """
        load_dotenv()
        
        self.home_location = home_location
        self.local_weather_url = "http://192.168.88.243:8000/weather-forecast"
        self.allow_internet_searches = allow_internet_searches
        
        # Load API keys from environment
        self.newsdata_api_key = os.getenv("NEWSDATA_API_KEY", "YOUR_NEWSDATA_API_KEY")
        
        # Load command schema for action matching
        if command_schema_path is None:
            command_schema_path = os.path.join(os.path.dirname(__file__), "command_schema.txt")
        self.command_schema = self._load_command_schema(command_schema_path)
        
        # Initialize calendar manager with PostgreSQL client
        self.calendar = CalendarManager(pg_client)

    def _load_command_schema(self, filepath: str) -> dict:
        """
        @brief Load command schema from a JSON file.

        @param filepath Path to the command schema file.
        @return Dictionary of the command schema or empty dict on error.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                command_schema = json.load(file)
            return command_schema
        except FileNotFoundError:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] File not found: {filepath}")
        except json.JSONDecodeError as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Failed to parse JSON - {e}")
        except Exception as e:
            print(f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Unexpected error: {e}")

        return {}

    def call_function_by_name(self, function_name: str, *args, **kwargs):
        """
        @brief Call a method by name if it exists and is callable.

        @param function_name Name of the method to call.
        @return Result of the method or None if not found.
        """
        if hasattr(self, function_name):
            method = getattr(self, function_name)
            if callable(method):
                return method(*args, **kwargs)
            else:
                print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] {function_name} exists but is not callable.")
        else:
            print(f"[SimpleFunctions] [{LogLevel.WARNING.name}] No function named {function_name} found.")

    def get_wikipedia_summary(self, topic=None):
        """
        @brief Fetch a short introductory summary from Wikipedia for a given topic.

        @param topic Topic/article name as a string.
        @return Summary string or error message.
        """
        if not self.allow_internet_searches:
            return "Internet searches are currently disabled in system settings."
        
        error_message = "Wikipedia information not available at the moment, please try later."

        if not topic:
            return "Please specify a topic."

        headers = {
            'User-Agent': 'LLHAMA-Assistant/1.0 (https://github.com/Nemesis533/Local_LLHAMA)'
        }

        # Normalize topic for initial request
        topic_formatted = "_".join(topic.strip().split())

        try:
            # Step 1: Get canonical page title from summary endpoint
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic_formatted}"
            summary_resp = requests.get(summary_url, headers=headers, timeout=10)
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()
            canonical_title = summary_data.get("title").replace(" ", "_")

            if not canonical_title:
                return f"No Wikipedia page found for: {topic}"

            # Step 2: Fetch HTML using canonical title
            html_url = f"https://api.wikimedia.org/core/v1/wikipedia/en/page/{canonical_title}/html"
            html_resp = requests.get(html_url, headers=headers, timeout=10)
            html_resp.raise_for_status()

            html_content = html_resp.text
            soup = BeautifulSoup(html_content, 'html.parser')

            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'table', 'figure']):
                element.decompose()

            # Get the first few paragraphs (introduction)
            paragraphs = soup.find_all('p', limit=3)
            text_parts = []

            for p in paragraphs:
                text = p.get_text(separator=' ', strip=True)
                if text and len(text) > 20:  # Skip very short paragraphs
                    text_parts.append(text)

            if text_parts:
                summary_text = ' '.join(text_parts)
                # Limit to reasonable length
                if len(summary_text) > 500:
                    summary_text = summary_text[:497] + "..."
                return summary_text
            else:
                return f"No summary found for: {topic}"

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return f"No Wikipedia page found for: {topic}"
            return error_message
        except Exception:
            return error_message

    def get_news_summary(self, query=None):
        """
        @brief Fetch a summary of the latest global news related to a query.

        @param query Search term string.
        @return Summary of top news articles or error message.
        """
        if not self.allow_internet_searches:
            return "Internet searches are currently disabled in system settings."
        
        error_message = "News data not available at the moment, please try later."

        if not query:
            return "Please specify a news topic."

        url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": self.newsdata_api_key,
            "q": query,
            "language": "en"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            articles = data.get("results", [])
            if not articles:
                return f"No recent news found for: {query}"

            # Build a short summary from the top 3 headlines
            summaries = []
            for article in articles[:3]:
                title = article.get("title", "")
                desc = article.get("description", "")
                summaries.append(f"- {title}\n  {desc}")

            return "\n\n".join(summaries)

        except Exception:
            return error_message

    def _format_weather_response(self, location: str, temperature: float, condition: str = None, wind_speed: float = None) -> str:
        """
        @brief Format a consistent weather response message.

        @param location Location name or description.
        @param temperature Temperature value.
        @param condition Optional weather condition description.
        @param wind_speed Optional wind speed value.
        @return Formatted weather string.
        """
        response = f"The weather in {location} is"
        
        if condition:
            response += f" {condition} with a temperature of {round(temperature, 2)} degrees"
        else:
            response += f" {round(temperature, 2)} degrees"
        
        if wind_speed is not None:
            response += f" and wind speed {round(wind_speed, 2)} kmh"
        
        return response + "."

    def home_weather(self, place=None):
        """
        @brief Fetch weather forecast from a local weather server.

        @param place Optional location parameter (currently unused).
        @return Weather forecast string or error message.
        """
        error_message = "Weather data not available at the moment, please try later."

        try:
            response = requests.get(self.local_weather_url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            return f"Error fetching weather forecast: {e}"

        forecast = data.get("forecast", [])
        if not forecast:
            return "Weather data not available."

        today = forecast[0]
        if today:
            return self._format_weather_response(
                location="home",
                temperature=float(today['temp']),
                condition=today.get('condition')
            )
        return error_message
    
    # === CALENDAR/REMINDER FUNCTIONS ===
    
    def add_reminder(self, title: str, when: str, description: str = "", repeat: str = "none") -> str:
        """
        Add a reminder for a specific date and time.
        
        @param title: What to be reminded about
        @param when: When to be reminded (e.g., "2025-12-25 09:00", "tomorrow at 15:00")
        @param description: Optional additional details
        @param repeat: Repeat pattern - "none", "daily", "weekly", "monthly", "yearly"
        @return: Confirmation message
        """
        success, message, _ = self.calendar.add_reminder(title, when, description, repeat)
        return message
    
    def add_appointment(self, title: str, when: str, description: str = "") -> str:
        """
        Schedule an appointment.
        
        @param title: Appointment title/purpose
        @param when: When the appointment is scheduled (e.g., "2025-12-25 14:00")
        @param description: Optional appointment details
        @return: Confirmation message
        """
        success, message, _ = self.calendar.add_appointment(title, when, description)
        return message
    
    def add_alarm(self, title: str, when: str, repeat: str = "none") -> str:
        """
        Set an alarm.
        
        @param title: Alarm label/purpose
        @param when: When the alarm should go off (e.g., "2025-12-25 07:00", "tomorrow at 6:30")
        @param repeat: Repeat pattern - "none", "daily", "weekly"
        @return: Confirmation message
        """
        success, message, _ = self.calendar.add_alarm(title, when, repeat)
        return message
    
    def get_upcoming_reminders(self, days: int = 7) -> str:
        """
        Get upcoming reminders within specified days.
        
        @param days: Number of days to look ahead (default 7)
        @return: Formatted list of upcoming reminders
        """
        events = self.calendar.get_upcoming_events(event_type='reminder', days=days)
        
        if not events:
            return f"No reminders scheduled for the next {days} days."
        
        result = f"Upcoming reminders (next {days} days):\n"
        for event in events:
            dt = datetime.fromisoformat(event['due_datetime'])
            formatted = dt.strftime("%B %d at %I:%M %p")
            result += f"\n- {event['title']} - {formatted}"
            if event['repeat_pattern'] != 'none':
                result += f" (repeats {event['repeat_pattern']})"
        
        return result
    
    def get_upcoming_appointments(self, days: int = 7) -> str:
        """
        Get upcoming appointments within specified days.
        
        @param days: Number of days to look ahead (default 7)
        @return: Formatted list of upcoming appointments
        """
        events = self.calendar.get_upcoming_events(event_type='appointment', days=days)
        
        if not events:
            return f"No appointments scheduled for the next {days} days."
        
        result = f"Upcoming appointments (next {days} days):\n"
        for event in events:
            dt = datetime.fromisoformat(event['due_datetime'])
            formatted = dt.strftime("%B %d at %I:%M %p")
            result += f"\n- {event['title']} - {formatted}"
            if event['description']:
                result += f"\n  Details: {event['description']}"
        
        return result
    
    def get_alarms(self) -> str:
        """
        Get all active alarms.
        
        @return: Formatted list of alarms
        """
        events = self.calendar.get_upcoming_events(event_type='alarm', days=365)
        
        if not events:
            return "No alarms currently set."
        
        result = "Active alarms:\n"
        for event in events:
            dt = datetime.fromisoformat(event['due_datetime'])
            formatted = dt.strftime("%B %d at %I:%M %p")
            result += f"\n- {event['title']} - {formatted}"
            if event['repeat_pattern'] != 'none':
                result += f" (repeats {event['repeat_pattern']})"
        
        return result
    
    def complete_reminder(self, search_term: str) -> str:
        """
        Mark a reminder as completed by searching for it.
        
        @param search_term: Text to search for in reminder titles
        @return: Confirmation message
        """
        events = self.calendar.search_events(search_term, event_type='reminder')
        
        if not events:
            return f"No reminder found matching '{search_term}'."
        
        if len(events) > 1:
            result = f"Multiple reminders found for '{search_term}':\n"
            for event in events:
                dt = datetime.fromisoformat(event['due_datetime'])
                formatted = dt.strftime("%B %d at %I:%M %p")
                result += f"\n- ID {event['id']}: {event['title']} - {formatted}"
            result += "\n\nPlease be more specific or use the ID."
            return result
        
        event = events[0]
        success, message = self.calendar.complete_event(event['id'])
        return f"Marked '{event['title']}' as completed."
    
    def delete_reminder(self, search_term: str) -> str:
        """
        Delete a reminder, appointment, or alarm by searching for it.
        
        @param search_term: Text to search for in event titles
        @return: Confirmation message
        """
        events = self.calendar.search_events(search_term)
        
        if not events:
            return f"No event found matching '{search_term}'."
        
        if len(events) > 1:
            result = f"Multiple events found for '{search_term}':\n"
            for event in events:
                dt = datetime.fromisoformat(event['due_datetime'])
                formatted = dt.strftime("%B %d at %I:%M %p")
                result += f"\n- ID {event['id']}: {event['title']} ({event['event_type']}) - {formatted}"
            result += "\n\nPlease be more specific or use the ID."
            return result
        
        event = events[0]
        success, message = self.calendar.delete_event(event['id'])
        return f"Deleted {event['event_type']} '{event['title']}'."
    
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
            dt = datetime.fromisoformat(event['due_datetime'])
            formatted = dt.strftime("%B %d at %I:%M %p")
            result += f"\n- [{event['event_type'].upper()}] {event['title']} - {formatted}"
            if event['repeat_pattern'] != 'none':
                result += f" (repeats {event['repeat_pattern']})"
        
        return result
    
    def list_calendar(self, days: int = 7) -> str:
        """
        List all calendar entries including reminders, appointments, and alarms in an organized format.
        Simple function that provides a comprehensive view of the calendar.
        
        @param days: Number of days to look ahead (default 7)
        @return: Formatted calendar listing grouped by type
        """
        all_events = self.calendar.get_upcoming_events(days=days, include_completed=False)
        
        if not all_events:
            return f"Calendar is empty for the next {days} days."
        
        # Group events by type
        reminders = [e for e in all_events if e['event_type'] == 'reminder']
        appointments = [e for e in all_events if e['event_type'] == 'appointment']
        alarms = [e for e in all_events if e['event_type'] == 'alarm']
        
        result = f"CALENDAR (next {days} days):\n"
        
        # Show reminders
        if reminders:
            result += f"\nREMINDERS ({len(reminders)}):\n"
            for event in reminders:
                dt = datetime.fromisoformat(event['due_datetime'])
                formatted = dt.strftime("%b %d at %I:%M %p")
                result += f"  - {event['title']} - {formatted}"
                if event['repeat_pattern'] != 'none':
                    result += f" [repeats {event['repeat_pattern']}]"
                if event.get('description'):
                    result += f"\n    Details: {event['description']}"
                result += "\n"
        
        # Show alarms
        if alarms:
            result += f"\nALARMS ({len(alarms)}):\n"
            for event in alarms:
                dt = datetime.fromisoformat(event['due_datetime'])
                formatted = dt.strftime("%b %d at %I:%M %p")
                result += f"  - {event['title']} - {formatted}"
                if event['repeat_pattern'] != 'none':
                    result += f" [repeats {event['repeat_pattern']}]"
                result += "\n"
        
        # Show appointments
        if appointments:
            result += f"\nAPPOINTMENTS ({len(appointments)}):\n"
            for event in appointments:
                dt = datetime.fromisoformat(event['due_datetime'])
                formatted = dt.strftime("%b %d at %I:%M %p")
                result += f"  - {event['title']} - {formatted}"
                if event.get('description'):
                    result += f"\n    Details: {event['description']}"
                result += "\n"
        
        result += f"\nTotal: {len(all_events)} event(s)"
        return result

    def get_coordinates(self, place_name):
        """
        @brief Get latitude and longitude coordinates for a given place name.

        @param place_name Name of the place to geocode.
        @return Tuple of (latitude, longitude) or (None, None) if not found.
        """
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            'name': place_name,
            'count': 1,
            'format': 'json'
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results")
            if results:
                return results[0]['latitude'], results[0]['longitude']
        return None, None
        
    def get_weather(self, place=None):
        """
        @brief Fetch current weather for a specified place.

        @param place Place name string.
        @return Weather description string or error message.
        """
        error_message = "Weather data not available at the moment, please try later."

        if not place:
            return "Please specify a location."

        lat, lon = self.get_coordinates(place)

        if lat is None or lon is None:
            return f"Could not find location: {place}"

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'current_weather': True
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json().get("current_weather", {})
            
            if data:
                return self._format_weather_response(
                    location=place,
                    temperature=data['temperature'],
                    wind_speed=data.get('windspeed')
                )
            return f"Weather data not available for {place}."
        except requests.RequestException:
            return error_message
    
    def find_matching_action(self, command_json: dict | list) -> str | None:
        """
        @brief Find a matching simple function action for the given command.

        @param command_json Single command dict or list of commands.
        @return Action name string if matched, else None.
        """
        command_json = self._replace_target_with_entity_id(command_json)

        if isinstance(command_json, dict):
            command_json = [command_json]

        for item in command_json:
            entity = item.get("entity_id")
            action = item.get("action")

            if not entity:
                continue

            valid_actions = self.command_schema.get(entity, {}).get("actions", [])
            if action in valid_actions:
                return action

        return None
    
    def _replace_target_with_entity_id(self, command):
        """
        @brief Recursively replace 'target' keys with 'entity_id' in command JSON.

        @param command Dict or list representing the command(s).
        @return Modified command with 'entity_id' keys.
        """
        if isinstance(command, dict):
            new_obj = {}
            for k, v in command.items():
                new_key = "entity_id" if k == "target" else k
                new_obj[new_key] = self._replace_target_with_entity_id(v)
            return new_obj
        elif isinstance(command, list):
            return [self._replace_target_with_entity_id(item) for item in command]
        else:
            return command
