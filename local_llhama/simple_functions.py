# === System Imports ===
import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from . import simple_functions_helpers as helpers
from .auth.calendar_manager import CalendarManager

# === Custom Imports ===
from .error_handler import ErrorHandler
from .shared_logger import LogLevel

CLASS_PREFIX_MESSAGE = "[SimpleFunctions]"


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
        ollama_host=None,
        ollama_embedding_model=None,
        settings_loader=None,
    ):
        """
        @brief Initialize with home location.
        @param home_location Dictionary with 'latitude' and 'longitude'.
        @param command_schema_path Optional path to command schema file.
        @param allow_internet_searches Whether to allow internet-based searches (Wikipedia, news, etc.)
        @param pg_client PostgreSQL_Client instance for calendar operations.
        @param ollama_host Ollama server host URL (e.g., "192.168.1.1:11434")
        @param ollama_embedding_model Ollama embedding model name (e.g., "embeddinggemma")
        @param settings_loader SettingLoaderClass instance for loading web search config
        """
        load_dotenv()

        self.home_location = home_location
        self.allow_internet_searches = allow_internet_searches
        self.pg_client = pg_client
        self.ollama_host = ollama_host
        self.ollama_embedding_model = ollama_embedding_model or "nomic-embed-text"
        self.similarity_threshold = (
            0.5  # Default threshold for memory search similarity
        )
        self.settings_loader = settings_loader

        # Load web search configuration from settings loader
        self.web_search_config = (
            settings_loader.web_search_config
            if settings_loader
            else self._load_web_search_config()
        )

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

        # Common headers for HTTP requests
        self.headers = {
            "User-Agent": "LLHAMA-Assistant/1.0 (https://github.com/Nemesis533/Local_LLHAMA)"
        }

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
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Failed to load web search config: {e}"
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
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] File not found: {filepath}"
            )
        except json.JSONDecodeError as e:
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Failed to parse JSON - {e}"
            )
        except Exception as e:
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Unexpected error: {e}"
            )

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
                    f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] {function_name} exists but is not callable."
                )
        else:
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] No function named {function_name} found."
            )

    def get_wikipedia_summary(self, topic=None, user_id=None):
        """
        @brief Fetch a short introductory summary from Wikipedia for a given topic.
        Falls back to memory search if Wikipedia doesn't have the article.
        Automatically handles compound queries (e.g., "gastritis and honey") by fetching multiple articles.

        @param topic Topic/article name as a string.
        @param user_id Optional user ID for memory search fallback.
        @return Summary string or error message.
        """
        # Validate inputs
        if not helpers.check_internet_access(self.allow_internet_searches):
            return "Internet searches are currently disabled in system settings."

        error_msg = helpers.validate_input(topic, "topic")
        if error_msg:
            return error_msg

        # Get Wikipedia URLs from config
        wiki_base_url = helpers.get_config_url(self.web_search_config, "wikipedia", "")
        wikimedia_base_url = helpers.get_config_url(
            self.web_search_config, "wikimedia", ""
        )

        # Normalize topic for initial request
        topic_formatted = "_".join(topic.strip().split())

        try:
            # Step 1: Get canonical page title
            summary_url = f"{wiki_base_url}/page/summary/{topic_formatted}"
            timeout = self.web_search_config.get("timeout", 10)
            summary_data = helpers.make_http_request(
                summary_url, self.headers, timeout=timeout
            )

            if not summary_data or not summary_data.get("title"):
                # Try splitting into multiple topics if original query failed
                return self._handle_compound_wikipedia_query(
                    topic, user_id, wiki_base_url, wikimedia_base_url, timeout
                )

            canonical_title = summary_data.get("title").replace(" ", "_")

            # Step 2: Fetch HTML content
            html_url = f"{wikimedia_base_url}/{canonical_title}/html"
            timeout = self.web_search_config.get("timeout", 10)
            html_resp = requests.get(html_url, headers=self.headers, timeout=timeout)
            html_resp.raise_for_status()

            # Parse and extract text
            soup = BeautifulSoup(html_resp.text, "html.parser")

            # Remove unwanted elements
            for element in soup(
                ["script", "style", "nav", "footer", "header", "table", "figure"]
            ):
                element.decompose()

            # Get the first few paragraphs
            paragraphs = soup.find_all("p", limit=3)
            text_parts = [
                p.get_text(separator=" ", strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 20
            ]

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
                # Try splitting into multiple topics
                compound_result = self._handle_compound_wikipedia_query(
                    topic, user_id, wiki_base_url, wikimedia_base_url, timeout
                )
                if compound_result and "not available" not in compound_result.lower():
                    return compound_result
                # Fall back to memory search
                return helpers.wikipedia_fallback_to_memory(
                    topic, user_id, self.pg_client, self.find_in_memory
                )
            ErrorHandler.log_error(
                CLASS_PREFIX_MESSAGE, e, LogLevel.WARNING, "Wikipedia HTTP error"
            )
            return (
                "Wikipedia information not available at the moment, please try later."
            )
        except Exception as e:
            ErrorHandler.log_error(
                CLASS_PREFIX_MESSAGE, e, LogLevel.CRITICAL, "Wikipedia fetch error"
            )
            return (
                "Wikipedia information not available at the moment, please try later."
            )

    def _handle_compound_wikipedia_query(self, topic, user_id, wiki_base_url, wikimedia_base_url, timeout):
        """
        @brief Handle queries with multiple topics (e.g., "gastritis and honey").
        Splits the query and fetches separate articles.

        @param topic Original topic string
        @param user_id Optional user ID for memory fallback
        @param wiki_base_url Wikipedia API base URL
        @param wikimedia_base_url Wikimedia API base URL
        @param timeout Request timeout
        @return Combined summary or error message
        """
        import re
        
        # Split on common conjunctions
        splitters = r'\s+(?:and|or|vs|versus|with|plus)\s+'
        topics = re.split(splitters, topic, flags=re.IGNORECASE)
        
        # Clean and filter topics
        topics = [t.strip() for t in topics if t.strip() and len(t.strip()) > 2]
        
        # Limit to max 3 topics to avoid overwhelming
        topics = topics[:3]
        
        if len(topics) < 2:
            # Not a compound query, return None to use fallback
            return None
        
        print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Compound query detected: {topics}")
        
        summaries = []
        for sub_topic in topics:
            try:
                sub_topic_formatted = "_".join(sub_topic.strip().split())
                summary_url = f"{wiki_base_url}/page/summary/{sub_topic_formatted}"
                
                summary_data = helpers.make_http_request(
                    summary_url, self.headers, timeout=timeout
                )
                
                if summary_data and summary_data.get("title"):
                    canonical_title = summary_data.get("title").replace(" ", "_")
                    html_url = f"{wikimedia_base_url}/{canonical_title}/html"
                    
                    html_resp = requests.get(html_url, headers=self.headers, timeout=timeout)
                    html_resp.raise_for_status()
                    
                    soup = BeautifulSoup(html_resp.text, "html.parser")
                    
                    # Remove unwanted elements
                    for element in soup(["script", "style", "nav", "footer", "header", "table", "figure"]):
                        element.decompose()
                    
                    # Get first 2 paragraphs for each sub-topic
                    paragraphs = soup.find_all("p", limit=2)
                    text_parts = [
                        p.get_text(separator=" ", strip=True)
                        for p in paragraphs
                        if len(p.get_text(strip=True)) > 20
                    ]
                    
                    if text_parts:
                        summary = " ".join(text_parts)
                        # Limit each sub-summary to ~250 chars
                        if len(summary) > 250:
                            summary = summary[:247] + "..."
                        summaries.append(f"{sub_topic.title()}: {summary}")
                        
            except Exception as e:
                print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Failed to fetch '{sub_topic}': {e}")
                continue
        
        if summaries:
            combined = "\n\n".join(summaries)
            print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Combined {len(summaries)} Wikipedia summaries")
            return combined
        
        return None

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
            gdelt_url = helpers.get_config_url(self.web_search_config, "gdelt", "")

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
        weather_url = helpers.get_config_url(
            self.web_search_config, "open-meteo weather", ""
        )

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
        # Normalize repeat pattern - convert common variations to database values
        repeat_normalized = repeat.lower() if repeat else "none"
        if repeat_normalized in ["once", "never", "no", "single"]:
            repeat_normalized = "none"
        elif repeat_normalized not in ["none", "daily", "weekly", "monthly", "yearly"]:
            # Invalid repeat pattern, default to none
            print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Invalid repeat pattern '{repeat}', using 'none'")
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
        geocoding_url = helpers.get_config_url(
            self.web_search_config, "open-meteo geocoding", ""
        )

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
        weather_url = helpers.get_config_url(
            self.web_search_config, "open-meteo weather", ""
        )

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

    def find_in_memory(self, query, user_id, limit=3, role=None, days_back=None):
        """
        Find most similar messages using vector similarity search with pgvector
        and keyword matching.

        @param query: Text query to search for in past conversations
        @param user_id: User ID to filter messages by
        @param limit: Number of similar messages to return (default 3)
        @param role: Optional role filter ('user', 'assistant', or None for both)
        @param days_back: Optional number of days to look back (None = all time)
        @return: Formatted string describing found memories or error message
        """
        if not self.pg_client or not query:
            return "No query provided for memory search."

        if not self.ollama_host:
            return "Ollama host not configured for memory search."

        # Generate embedding from query using Ollama
        try:
            import requests

            ollama_url = (
                self.ollama_host
                if self.ollama_host.startswith("http")
                else f"http://{self.ollama_host}"
            )
            response = requests.post(
                f"{ollama_url}/api/embeddings",
                json={"model": self.ollama_embedding_model, "prompt": query},
                timeout=30,
            )
            response.raise_for_status()
            embedding = response.json().get("embedding")
            if not embedding:
                return "Could not generate embedding for search."
        except Exception as e:
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Error generating embedding: {e}"
            )
            return "Could not generate embedding for search."

        try:
            import re

            # Extract alphanumeric keywords from query, lowercase for matching
            keywords = re.findall(r"\w+", query.lower())
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Parsed keywords: {keywords}"
            )

            # Build keyword search conditions (OR logic: match any keyword)
            keyword_conditions = []
            keyword_params = []
            for keyword in keywords:
                keyword_conditions.append("LOWER(m.content) ILIKE %s")
                keyword_params.append(f"%{keyword}%")
            keyword_where = (
                " OR ".join(keyword_conditions) if keyword_conditions else "1=1"
            )

            # Build role filter condition
            if role:
                role_condition = "AND m.role = %s"
                role_params = [role, role]  # For both vector_search and keyword_search
            else:
                role_condition = ""
                role_params = []

            # Build date filter condition
            if days_back is not None:
                date_condition = "AND m.created_at >= CURRENT_DATE - INTERVAL '%s days'"
                date_params = [days_back, days_back]  # For both searches
            else:
                date_condition = ""
                date_params = []

            # Hybrid search: vector similarity + keyword matching
            sql_query = f"""
            WITH vector_search AS (
                SELECT m.id, m.content, m.role, m.created_at, m.conversation_id,
                    1 - (me.vector <=> %s::vector) AS similarity
                FROM messages m
                JOIN message_embeddings me ON m.id = me.message_id
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.user_id = %s
                {role_condition}
                {date_condition}
                AND (1 - (me.vector <=> %s::vector)) >= %s
            ),
            keyword_search AS (
                SELECT m.id, m.content, m.role, m.created_at, m.conversation_id,
                    0.5 + 0.1 * (
                        {" + ".join([f"(LOWER(m.content) LIKE %s)::int" for _ in keywords])}
                    ) AS similarity
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.user_id = %s
                {role_condition}
                {date_condition}
                AND ({keyword_where})
            ),
            combined AS (
                SELECT id, content, role, created_at, conversation_id, MAX(similarity) as similarity
                FROM (
                    SELECT * FROM vector_search
                    UNION ALL
                    SELECT * FROM keyword_search
                ) all_results
                GROUP BY id, content, role, created_at, conversation_id
            )
            SELECT 
                c.content as user_content,
                c.created_at,
                c.similarity,
                m_next.content as assistant_content,
                c.role as message_role
            FROM combined c
            LEFT JOIN LATERAL (
                SELECT m_next.content
                FROM messages m_next
                WHERE m_next.conversation_id = c.conversation_id
                AND m_next.created_at > c.created_at
                AND m_next.role = 'assistant'
                ORDER BY m_next.created_at ASC
                LIMIT 1
            ) m_next ON TRUE
            ORDER BY c.similarity DESC
            LIMIT %s
            """

            # Build params tuple
            params_tuple = [
                embedding,  # vector_search embedding
                user_id,
                *role_params[:1],  # role for vector_search (if any)
                *date_params[:1],  # days_back for vector_search (if any)
                embedding,  # vector_search threshold comparison
                self.similarity_threshold,
                *keyword_params,  # keyword LIKE params for keyword_search similarity calculation
                user_id,
                *role_params[1:2],  # role for keyword_search (if any)
                *date_params[1:2],  # days_back for keyword_search (if any)
                *keyword_params,  # keyword LIKE params for WHERE clause
                limit,
            ]

            # Debug
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] SQL placeholders: {sql_query.count('%s')}, Params length: {len(params_tuple)}"
            )

            results = self.pg_client.execute_query(sql_query, tuple(params_tuple))

            filtered_results = []
            for row in results or []:
                if len(row) < 3:
                    print(
                        f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Skipping malformed row: {row}"
                    )
                    continue
                filtered_results.append(
                    {
                        "user_message": row[0],
                        "created_at": row[1],
                        "similarity": float(row[2]),
                        "assistant_response": (
                            row[3] if len(row) > 3 and row[3] else None
                        ),
                        "message_role": (
                            row[4] if len(row) > 4 else "user"
                        ),  # Track what role the message was
                    }
                )

            if filtered_results:
                print(
                    f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Found {len(filtered_results)} memories above threshold {self.similarity_threshold:.2f}"
                )
                for idx, result in enumerate(filtered_results, 1):
                    print(
                        f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}]   {idx}. Similarity: {result['similarity']:.4f} (Role: {result.get('message_role', 'unknown')})"
                    )

                # Format results as a natural language string
                response_parts = [
                    f"I found {len(filtered_results)} relevant memory/memories from our past conversations:"
                ]

                for idx, result in enumerate(filtered_results, 1):
                    timestamp = (
                        result["created_at"].strftime("%B %d, %Y")
                        if hasattr(result["created_at"], "strftime")
                        else str(result["created_at"])
                    )
                    similarity_pct = int(result["similarity"] * 100)
                    msg_role = result.get("message_role", "user")

                    response_parts.append(f"\n{idx}. (Similarity: {similarity_pct}%)")

                    # Format differently based on whether it's a user or assistant message
                    if msg_role == "assistant":
                        response_parts.append(
                            f"   I said: \"{result['user_message'][:300]}{'...' if len(result['user_message']) > 300 else ''}\""
                        )
                    else:
                        response_parts.append(
                            f"   You asked: \"{result['user_message']}\""
                        )
                        if result.get("assistant_response"):
                            response_parts.append(
                                f"   I responded: \"{result['assistant_response'][:300]}{'...' if len(result.get('assistant_response', '')) > 300 else ''}\""
                            )

                    response_parts.append(f"   (from {timestamp})")

                return "\n".join(response_parts)

            return f"No memories found with similarity above {self.similarity_threshold:.2f}."

        except Exception as e:
            import traceback

            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Error finding similar messages: {e}"
            )
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.CRITICAL.name}] Traceback:\n{traceback.format_exc()}"
            )
            return "Could not find previous messages for this topic."

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

    def generate_conversational_response(self, query=None, context=None):
        """
        @brief Generate a natural language conversational response.

        This function is called when the user asks for general conversation,
        stories, creative content, or anything that doesn't require device
        control or information lookup.

        The context parameter is populated by the chat handler/command processor
        and can include:
        - conversation_history: Recent messages from the conversation
        - user_preferences: Language, tone, formality settings
        - temporal_context: Time of day, date, timezone
        - function_results: Results from other functions called in same request
        - user_metadata: User ID, name, location, etc.

        @param query The user's conversational query/request.
        @param context Optional dict with additional contextual information
                       to enhance the response (populated by system, not LLM).
        @return Dict with 'type', 'response', and metadata.
        """
        if not query:
            return {
                "type": "simple_function",
                "function_name": "generate_conversational_response",
                "response": "I didn't receive a query to respond to.",
                "error": "Missing query parameter",
            }

        # This will be intercepted by the command processor and sent to
        # the conversation LLM with appropriate context and prompts
        return {
            "type": "simple_function",
            "function_name": "generate_conversational_response",
            "query": query,
            "context": context or {},
            "response": f"Generating response for: {query}",
        }
