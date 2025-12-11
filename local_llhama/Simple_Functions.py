# === System Imports ===
import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from .auth.calendar_manager import CalendarManager

# === Custom Imports ===
from .Shared_Logger import LogLevel


class SimpleFunctions:
    """
    @class SimpleFunctions
    @brief Implements additional non-Home Assistant commands and utilities.

    Handles tasks like weather info, news lookups, Wikipedia queries, and other logic outside HA.
    """

    def __init__(
        self,
        home_location,
        command_schema_path=None,
        allow_internet_searches=True,
        pg_client=None,
    ):
        """
        @brief Initialize with home location.
        @param home_location Dictionary with 'latitude' and 'longitude'.
        @param command_schema_path Optional path to command schema file.
        @param allow_internet_searches Whether to allow internet-based searches (Wikipedia, news, etc.)
        @param pg_client PostgreSQL_Client instance for calendar operations.
        """
        load_dotenv()

        self.home_location = home_location
        self.allow_internet_searches = allow_internet_searches

        # Load web search configuration
        self.web_search_config = self._load_web_search_config()

        # Load API keys from config or environment
        api_tokens = self.web_search_config.get("api_tokens", {})
        self.newsdata_api_key = api_tokens.get("newsdata") or os.getenv(
            "NEWSDATA_API_KEY", "YOUR_NEWSDATA_API_KEY"
        )

        # Load command schema for action matching
        if command_schema_path is None:
            command_schema_path = os.path.join(
                os.path.dirname(__file__), "command_schema.txt"
            )
        self.command_schema = self._load_command_schema(command_schema_path)

        # Initialize calendar manager with PostgreSQL client
        self.calendar = CalendarManager(pg_client)

    def _load_web_search_config(self) -> dict:
        """
        @brief Load web search configuration from JSON file.

        @return Dictionary of web search config or default values on error.
        """
        config_path = os.path.join(
            os.path.dirname(__file__), "settings", "web_search_config.json"
        )
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as e:
            print(
                f"[SimpleFunctions] [{LogLevel.WARNING.name}] Failed to load web search config: {e}"
            )
            # Return default configuration
            return {
                "allowed_websites": [],
                "max_results": 3,
                "timeout": 10,
                "api_tokens": {},
            }

    def _load_command_schema(self, filepath: str) -> dict:
        """
        @brief Load command schema from a JSON file.

        @param filepath Path to the command schema file.
        @return Dictionary of the command schema or empty dict on error.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                command_schema = json.load(file)
            return command_schema
        except FileNotFoundError:
            print(
                f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] File not found: {filepath}"
            )
        except json.JSONDecodeError as e:
            print(
                f"[SimpleFunctions] [{LogLevel.CRITICAL.name}] Failed to parse JSON - {e}"
            )
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
                print(
                    f"[SimpleFunctions] [{LogLevel.WARNING.name}] {function_name} exists but is not callable."
                )
        else:
            print(
                f"[SimpleFunctions] [{LogLevel.WARNING.name}] No function named {function_name} found."
            )

    def get_wikipedia_summary(self, topic=None):
        """
        @brief Fetch a short introductory summary from Wikipedia for a given topic.

        @param topic Topic/article name as a string.
        @return Summary string or error message.
        """
        if not self.allow_internet_searches:
            return "Internet searches are currently disabled in system settings."

        error_message = (
            "Wikipedia information not available at the moment, please try later."
        )

        if not topic:
            return "Please specify a topic."

        headers = {
            "User-Agent": "LLHAMA-Assistant/1.0 (https://github.com/Nemesis533/Local_LLHAMA)"
        }

        # Get Wikipedia URLs from config
        wiki_base_url = "https://en.wikipedia.org/api/rest_v1"  # default
        wikimedia_base_url = (
            "https://api.wikimedia.org/core/v1/wikipedia/en/page"  # default
        )

        for site in self.web_search_config.get("allowed_websites", []):
            site_name = site.get("name", "").lower()
            if site_name == "wikipedia":
                wiki_base_url = site.get("url", wiki_base_url)
            elif site_name == "wikimedia":
                wikimedia_base_url = site.get("url", wikimedia_base_url)

        timeout = self.web_search_config.get("timeout", 10)

        # Normalize topic for initial request
        topic_formatted = "_".join(topic.strip().split())

        try:
            # Step 1: Get canonical page title from summary endpoint
            summary_url = f"{wiki_base_url}/page/summary/{topic_formatted}"
            summary_resp = requests.get(summary_url, headers=headers, timeout=timeout)
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()
            canonical_title = summary_data.get("title").replace(" ", "_")

            if not canonical_title:
                return f"No Wikipedia page found for: {topic}"

            # Step 2: Fetch HTML using canonical title
            # Use Wikimedia API for HTML content
            html_url = f"{wikimedia_base_url}/{canonical_title}/html"
            html_resp = requests.get(html_url, headers=headers, timeout=timeout)
            html_resp.raise_for_status()

            html_content = html_resp.text
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove unwanted elements
            for element in soup(
                ["script", "style", "nav", "footer", "header", "table", "figure"]
            ):
                element.decompose()

            # Get the first few paragraphs (introduction)
            paragraphs = soup.find_all("p", limit=3)
            text_parts = []

            for p in paragraphs:
                text = p.get_text(separator=" ", strip=True)
                if text and len(text) > 20:  # Skip very short paragraphs
                    text_parts.append(text)

            if text_parts:
                summary_text = " ".join(text_parts)
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
        Fetch latest global news using GDELT API.

        GDELT monitors news sources worldwide in real-time, providing comprehensive coverage.

        @param query Search term string (topic, person, location, etc.)
        @return Summary of top news articles or error message
        """
        if not self.allow_internet_searches:
            return "Internet searches are currently disabled in system settings."

        if not query:
            return "Please specify a news topic."

        try:
            timeout = self.web_search_config.get("timeout", 15)
            max_results = self.web_search_config.get("max_results", 5)

            # Get GDELT URL from config
            gdelt_url = "https://api.gdeltproject.org/api/v2/doc/doc"  # default
            for site in self.web_search_config.get("allowed_websites", []):
                if "gdelt" in site.get("name", "").lower():
                    gdelt_url = site.get("url", gdelt_url)
                    break

            params = {
                "query": query,
                "mode": "artlist",  # Article list mode
                "maxrecords": str(
                    max_results * 2
                ),  # Get extras in case some are duplicates
                "format": "json",
                "sort": "datedesc",  # Most recent first
            }

            response = requests.get(gdelt_url, params=params, timeout=timeout)
            response.raise_for_status()

            data = response.json()
            articles = data.get("articles", [])

            if not articles:
                return f"No recent news found for: {query}"

            # Filter and format top articles
            summaries = []
            seen_titles = set()

            for article in articles:
                if len(summaries) >= max_results:
                    break

                title = article.get("title", "").strip()
                url = article.get("url", "")
                source = article.get("domain", "")

                # Skip duplicates
                if title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                # Format: Title (Source)
                summary = f"• {title}"
                if source:
                    summary += f" ({source})"

                summaries.append(summary)

            if not summaries:
                return f"No recent news found for: {query}"

            return f"Latest news about '{query}':\n\n" + "\n\n".join(summaries)

        except requests.exceptions.RequestException as e:
            return f"Error fetching news: Unable to connect to news service. {str(e)}"
        except Exception as e:
            return f"Error processing news data: {str(e)}"

    def _format_weather_response(
        self,
        location: str,
        temperature: float,
        condition: str = None,
        wind_speed: float = None,
    ) -> str:
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
            response += (
                f" {condition} with a temperature of {round(temperature, 2)} degrees"
            )
        else:
            response += f" {round(temperature, 2)} degrees"

        if wind_speed is not None:
            response += f" and wind speed {round(wind_speed, 2)} kmh"

        return response + "."

    def home_weather(self, place=None):
        """
        @brief Fetch weather forecast for home location using Open-Meteo API.

        @param place Optional location parameter (currently unused).
        @return Weather forecast string or error message.
        """
        error_message = "Weather data not available at the moment, please try later."

        if not self.home_location:
            return "Home location not configured."

        lat = self.home_location.get("latitude")
        lon = self.home_location.get("longitude")

        if lat is None or lon is None:
            return "Home coordinates not available."

        # Get Open-Meteo weather URL from config
        weather_url = "https://api.open-meteo.com/v1/forecast"  # default
        for site in self.web_search_config.get("allowed_websites", []):
            if site.get("name", "").lower() == "open-meteo weather":
                weather_url = site.get("url", weather_url)
                break

        timeout = self.web_search_config.get("timeout", 10)
        params = {"latitude": lat, "longitude": lon, "current_weather": True}

        try:
            response = requests.get(weather_url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json().get("current_weather", {})

            if data:
                return self._format_weather_response(
                    location="home",
                    temperature=data["temperature"],
                    wind_speed=data.get("windspeed"),
                )
            return "Weather data not available."
        except requests.RequestException:
            return error_message

    # === CALENDAR/REMINDER FUNCTIONS ===

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
        success, message, _ = self.calendar.add_event(
            event_type, title, when, description, repeat, user_id=user_id
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
                        dt = datetime.fromisoformat(event["due_datetime"])
                        formatted = dt.strftime("%B %d at %I:%M %p")
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
            dt = datetime.fromisoformat(event["due_datetime"])
            formatted = dt.strftime("%B %d at %I:%M %p")
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
                dt = datetime.fromisoformat(event["due_datetime"])
                formatted = dt.strftime("%B %d at %I:%M %p")
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
            dt = datetime.fromisoformat(event["due_datetime"])
            formatted = dt.strftime("%B %d at %I:%M %p")
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
                dt = datetime.fromisoformat(event["due_datetime"])
                formatted = dt.strftime("%b %d at %I:%M %p")
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
                dt = datetime.fromisoformat(event["due_datetime"])
                formatted = dt.strftime("%b %d at %I:%M %p")
                result += f"  - {event['title']} - {formatted}"
                if event["repeat_pattern"] != "none":
                    result += f" [repeats {event['repeat_pattern']}]"
                result += "\n"

        # Show appointments
        if appointments:
            result += f"\nAPPOINTMENTS ({len(appointments)}):\n"
            for event in appointments:
                dt = datetime.fromisoformat(event["due_datetime"])
                formatted = dt.strftime("%b %d at %I:%M %p")
                result += f"  - {event['title']} - {formatted}"
                if event.get("description"):
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
        # Get Open-Meteo geocoding URL from config
        geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"  # default
        for site in self.web_search_config.get("allowed_websites", []):
            if site.get("name", "").lower() == "open-meteo geocoding":
                geocoding_url = site.get("url", geocoding_url)
                break

        url = geocoding_url
        timeout = self.web_search_config.get("timeout", 10)
        params = {"name": place_name, "count": 1, "format": "json"}
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results")
            if results:
                return results[0]["latitude"], results[0]["longitude"]
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

        # Get Open-Meteo weather URL from config
        weather_url = "https://api.open-meteo.com/v1/forecast"  # default
        for site in self.web_search_config.get("allowed_websites", []):
            if site.get("name", "").lower() == "open-meteo weather":
                weather_url = site.get("url", weather_url)
                break

        timeout = self.web_search_config.get("timeout", 10)
        params = {"latitude": lat, "longitude": lon, "current_weather": True}

        try:
            response = requests.get(weather_url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json().get("current_weather", {})

            if data:
                return self._format_weather_response(
                    location=place,
                    temperature=data["temperature"],
                    wind_speed=data.get("windspeed"),
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

    def get_display_name(self, action_name: str) -> str | None:
        """
        @brief Get the display name for a simple function action.

        @param action_name The action name to look up
        @return Display name string if found, else None
        """
        # Find the entity that has this action
        for entity_id, entity_info in self.command_schema.items():
            if action_name in entity_info.get("actions", []):
                return entity_info.get("display_name")
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
