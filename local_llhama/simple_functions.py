# === System Imports ===
import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from .utils import memory_search_helpers as mem_helpers
from .utils import simple_functions_helpers as helpers
from .auth.automation_manager import AutomationManager
from .auth.calendar_manager import CalendarManager

# === Service Imports ===
from .services.wikipedia_service import WikipediaService
from .services.weather_service import WeatherService
from .services.news_service import NewsService
from .services.memory_service import MemoryService
from .services.calendar_service import CalendarService
from .services.automation_service import AutomationService

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
            0.7  # Default threshold for memory search similarity
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

        # Initialize managers
        calendar_manager = CalendarManager(pg_client)
        automation_manager = AutomationManager(pg_client)

        # Common headers for HTTP requests
        self.headers = {
            "User-Agent": "LLHAMA-Assistant/1.0 (https://github.com/Nemesis533/Local_LLHAMA)"
        }

        # Initialize service instances
        self.wikipedia_service = WikipediaService(
            web_search_config=self.web_search_config,
            headers=self.headers,
            allow_internet_searches=self.allow_internet_searches,
            pg_client=self.pg_client,
            find_in_memory_callback=None,  # Will be set after MemoryService init
        )

        self.weather_service = WeatherService(
            web_search_config=self.web_search_config, home_location=self.home_location
        )

        self.news_service = NewsService(
            web_search_config=self.web_search_config,
            allow_internet_searches=self.allow_internet_searches,
        )

        self.memory_service = MemoryService(
            pg_client=self.pg_client,
            ollama_host=self.ollama_host,
            ollama_embedding_model=self.ollama_embedding_model,
            similarity_threshold=self.similarity_threshold,
        )

        # Set memory callback for Wikipedia fallback
        self.wikipedia_service.find_in_memory = self.memory_service.find_in_memory

        # Initialize calendar and automation services
        self.calendar_service = CalendarService(calendar_manager)
        self.automation_service = AutomationService(automation_manager)

        # Maintain backward compatibility - keep references for existing code
        self.calendar = calendar_manager
        self.automation = automation_manager

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
        return self.wikipedia_service.get_wikipedia_summary(topic, user_id)

    def get_news_summary(self, query=None):
        """
        Fetch latest global news using GDELT API.

        GDELT monitors news sources worldwide in real-time, providing comprehensive coverage.

        @param query Search term string (topic, person, location, etc.)
        @return Summary of top news articles or error message
        """
        return self.news_service.get_news_summary(query)

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
        return self.weather_service._format_weather_response(
            location, temperature, condition, wind_speed
        )

    def home_weather(self, place=None):
        """
        @brief Fetch weather forecast for home location using Open-Meteo API.

        @param place Optional location parameter (currently unused).
        @return Weather forecast string or error message.
        """
        return self.weather_service.home_weather(place)

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
        return self.calendar_service.add_event(
            event_type, title, when, description, repeat, user_id
        )

    def get_events(self, days: int = 7, event_type: str = None) -> str:
        """
        Get upcoming calendar events. Can filter by event type or get all events.

        @param days: Number of days to look ahead (default 7)
        @param event_type: Optional filter - "reminder", "appointment", "alarm", or None for all
        @return: Formatted list of upcoming events
        """
        return self.calendar_service.get_events(days, event_type)

    def manage_event(self, operation: str, search_term: str) -> str:
        """
        Complete or delete a calendar event by searching for it.

        @param operation: Action to perform - "complete" or "delete"
        @param search_term: Text to search for in event titles/descriptions
        @return: Confirmation message
        """
        return self.calendar_service.manage_event(operation, search_term)

    def get_all_upcoming_events(self, days: int = 7) -> str:
        """
        Get all upcoming events (reminders, appointments, alarms) within specified days.

        @param days: Number of days to look ahead (default 7)
        @return: Formatted list of all upcoming events
        """
        return self.calendar_service.get_all_upcoming_events(days)

    def list_calendar(self, days: int = 7) -> str:
        """
        List all calendar entries including reminders, appointments, and alarms in an organized format.
        Simple function that provides a comprehensive view of the calendar.

        @param days: Number of days to look ahead (default 7)
        @return: Formatted calendar listing grouped by type
        """
        return self.calendar_service.list_calendar(days)

    def get_coordinates(self, place_name):
        """
        @brief Get latitude and longitude coordinates for a given place name.

        @param place_name Name of the place to geocode.
        @return Tuple of (latitude, longitude) or (None, None) if not found.
        """
        return self.weather_service.get_coordinates(place_name)

    def get_weather(self, place=None):
        """
        @brief Fetch current weather for a specified place.

        @param place Place name string.
        @return Weather description string or error message.
        """
        return self.weather_service.get_weather(place)

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
        return self.memory_service.find_in_memory(
            query, user_id, limit, role, days_back
        )

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

    # === AUTOMATION FUNCTIONS ===

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
        return self.automation_service.create_automation(
            name, actions, description, user_id, save_previous_commands, current_request_commands
        )

    def trigger_automation(self, name: str, user_id: int = None, ha_client=None) -> str:
        """
        Trigger (execute) an existing automation by name.

        @param name: Name of the automation to run
        @param user_id: Optional user ID to filter automations
        @param ha_client: HomeAssistantClient instance for executing commands
        @return: Result message
        """
        return self.automation_service.trigger_automation(name, user_id, ha_client)

    def list_automations(self, user_id: int = None) -> str:
        """
        List all saved automations.

        @param user_id: Optional user ID to filter automations
        @return: Formatted list of automations
        """
        return self.automation_service.list_automations(user_id)

    def delete_automation(self, name: str, user_id: int = None) -> str:
        """
        Delete an automation by name.

        @param name: Name of the automation to delete
        @param user_id: Optional user ID to filter automations
        @return: Confirmation message
        """
        return self.automation_service.delete_automation(name, user_id)

    def get_wikipedia_image(self, topic: str = None) -> dict:
        """
        @brief Fetch a list of image candidates for a topic from Wikipedia.

        Hits the Wikimedia media-list endpoint first to gather all article images
        with captions and section context, then falls back to the summary endpoint
        for the cover image.  The candidates list is returned as a sentinel dict so
        that ChatHandler can ask the LLM to pick the most contextually relevant one
        before emitting the result to the frontend.

        @param topic   Topic or subject to look up on Wikipedia.
        @param user_id Optional user ID (unused, kept for consistency).
        @return Sentinel dict with type="wikipedia_image_request", or error string.
        """
        if not helpers.check_internet_access(self.allow_internet_searches):
            return "Internet searches are currently disabled in system settings."

        if not self.web_search_config.get("wikipedia_images_enabled", True):
            return "Wikipedia images are disabled in system settings."

        error_msg = helpers.validate_input(topic, "topic")
        if error_msg:
            return error_msg

        wiki_base_url = helpers.get_config_url(self.web_search_config, "wikipedia", "")
        topic_formatted = "_".join(topic.strip().split())
        timeout = self.web_search_config.get("timeout", 10)

        # Build list of titles to try: direct first, then OpenSearch alternatives
        titles_to_try = [topic_formatted]
        alt_titles = self._search_wikipedia_title(topic, wiki_base_url, timeout)
        titles_to_try += ["_".join(t.strip().split()) for t in alt_titles if t]

        for title_slug in titles_to_try[:5]:
            result = self._fetch_wikipedia_image_candidates(
                title_slug, wiki_base_url, timeout
            )
            if result:
                result["topic"] = topic
                return result

        return f"No image available on Wikipedia for: {topic}"

    def _fetch_wikipedia_image_candidates(
        self, title_slug: str, wiki_base_url: str, timeout: int
    ):
        """
        @brief Fetch image candidates for a single Wikipedia article slug.

        Resolves the canonical title via the summary endpoint, then hits the
        media-list endpoint to collect all usable images with captions and section
        context.  Falls back to the summary cover image if media-list is empty.

        @param title_slug    URL-safe article title (spaces → underscores).
        @param wiki_base_url Wikipedia REST base URL.
        @param timeout       Request timeout in seconds.
        @return Sentinel dict with keys (type, page_title, candidates, fallback_url,
                topic) if at least one image was found, otherwise None.
        """
        try:
            summary_data = helpers.make_http_request(
                f"{wiki_base_url}/page/summary/{title_slug}",
                self.headers,
                timeout=timeout,
            )
        except Exception:
            return None

        if not summary_data:
            return None

        page_title = summary_data.get("title", title_slug.replace("_", " "))
        canonical = page_title.replace(" ", "_")

        # Only use originalimage - thumbnails are unreliable and often 404
        fallback_img = summary_data.get("originalimage")
        fallback_url = fallback_img.get("source") if fallback_img else None

        # Convert thumbnail URLs to original format if needed
        # Thumb: .../commons/thumb/4/4d/File.jpg/500px-File.jpg
        # Original: .../commons/4/4d/File.jpg
        if fallback_url and "/thumb/" in fallback_url:
            # Remove /thumb/ from path and remove sized filename at end
            fallback_url = fallback_url.replace("/thumb/", "/").rsplit("/", 1)[0]

        candidates = []
        try:
            media_data = helpers.make_http_request(
                f"{wiki_base_url}/page/media-list/{canonical}",
                self.headers,
                timeout=timeout,
            )
            # Added filter as otherwise the result could potentially be too messy
            if media_data and media_data.get("items"):
                SKIP_EXTENSIONS = (
                    ".svg",
                    ".gif",
                    ".ogg",
                    ".ogv",
                    ".webm",
                    ".mp3",
                    ".mp4",
                    ".wav",
                )
                MIN_DIM = 400  # Minimum 400px to filter out icons, thumbnails, and low-res images
                seen_filenames = set()
                for item in media_data["items"]:
                    if item.get("type") != "image":
                        continue
                    # Only use the canonical original URL — never srcset thumbnails (avoids 404s)
                    original_src = item.get("original", {}).get("source", "")
                    if not original_src:
                        continue
                    # Skip math equation renders and other non-photo content
                    if (
                        "/math/render/" in original_src
                        or "wikimedia.org/api/" in original_src
                    ):
                        continue
                    if any(
                        original_src.lower().endswith(ext) for ext in SKIP_EXTENSIONS
                    ):
                        continue
                    w = item.get("original", {}).get("width", 9999)
                    h = item.get("original", {}).get("height", 9999)
                    if w < MIN_DIM or h < MIN_DIM:
                        continue
                    # Deduplicate by filename within this fetch
                    fname = original_src.rstrip("/").split("/")[-1].lower()
                    if fname in seen_filenames:
                        continue
                    seen_filenames.add(fname)
                    raw_caption = item.get("caption", {}).get("text", "") or item.get(
                        "title", ""
                    )
                    candidates.append(
                        {
                            "url": original_src,
                            "caption": raw_caption.strip(),
                            "section": item.get("section_title", "").strip(),
                        }
                    )
                print(
                    f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] "
                    f"media-list: {len(candidates)} candidate(s) for {page_title!r}"
                )
        except Exception as e:
            ErrorHandler.log_error(
                CLASS_PREFIX_MESSAGE, e, LogLevel.WARNING, "Wikipedia media-list fetch"
            )

        if not candidates:
            if not fallback_url:
                return None  # article exists but truly has no images
            candidates = [{"url": fallback_url, "caption": page_title, "section": ""}]

        return {
            "type": "wikipedia_image_request",
            "topic": title_slug.replace("_", " "),
            "page_title": page_title,
            "candidates": candidates,
            "fallback_url": fallback_url,
        }

    def generate_image(
        self, prompt: str, title: str = None, user_id: int = None
    ) -> dict:
        """
        @brief Signal that an image generation request has been received.

        This method does NOT perform the heavy generation work directly.
        It returns a sentinel dict that is detected by ChatHandler, which then
        offloads the LLM and runs the diffusion pipeline in a background thread.

        @param prompt   Detailed image description from the LLM.
        @param title    Optional image title (LLM will suggest one if absent).
        @param user_id  ID of the requesting user.
        @return Sentinel dict with type="image_generation_request".
        """
        print(
            f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Image generation request received: "
            f"title={title!r}, user_id={user_id}"
        )
        return {
            "type": "image_generation_request",
            "prompt": prompt or "",
            "title": title or "",
            "user_id": user_id,
        }

    def analyze_image(self, image: str, query: str = None, user_id: int = None) -> dict:
        """
        @brief Signal that an image analysis request has been received.

        This method does NOT perform the heavy inference directly.
        It returns a sentinel dict detected by ChatHandler, which then offloads
        the main LLM, loads LLaVA, runs analysis, streams the answer, unloads
        LLaVA, and reloads the main model.

        @param image    Image source: a URL, a file path, or a base64-encoded string.
        @param query    Question or instruction about the image.
        @param user_id  ID of the requesting user.
        @return Sentinel dict with type="image_analysis_request".
        """
        print(
            f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Image analysis request received: "
            f"query={query!r}, user_id={user_id}"
        )
        return {
            "type": "image_analysis_request",
            "image": image or "",
            "query": query or "Describe what you see in this image.",
            "user_id": user_id,
        }
