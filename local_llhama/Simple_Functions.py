# === System Imports ===
import requests
import json
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# === Custom Imports ===
from .Shared_Logger import LogLevel


class SimpleFunctions:
    """
    @class SimpleFunctions
    @brief Implements additional non-Home Assistant commands and utilities.

    Handles tasks like weather info, news lookups, Wikipedia queries, and other logic outside HA.
    """

    def __init__(self, home_location, command_schema_path=None):
        """
        @brief Initialize with home location.
        @param home_location Dictionary with 'latitude' and 'longitude'.
        @param command_schema_path Optional path to command schema file.
        """
        load_dotenv()
        
        self.home_location = home_location
        self.local_weather_url = "http://192.168.88.243:8000/weather-forecast"
        
        # Load API keys from environment
        self.newsdata_api_key = os.getenv("NEWSDATA_API_KEY", "YOUR_NEWSDATA_API_KEY")
        
        # Load command schema for action matching
        if command_schema_path is None:
            command_schema_path = os.path.join(os.path.dirname(__file__), "command_schema.txt")
        self.command_schema = self._load_command_schema(command_schema_path)

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
            return f"The weather at the location is {today['condition']} with a temperature of {round(float(today['temp']),2)} degrees."
        return error_message

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

        lat, lon = self.get_coordinates(place)

        if lat is None or lon is None:
            return f"Could not find location: {place}"

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'current_weather': True
        }
        response = requests.get(url, params=params)
        data = response.json().get("current_weather", {})
        if data:
            return f"The weather in {place} is {data['temperature']}°C with wind speed {data['windspeed']} km/h."
        return f"Weather data not available for {place}."
    
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
