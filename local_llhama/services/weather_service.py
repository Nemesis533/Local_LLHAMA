"""
@file weather_service.py
@brief Service for fetching weather data using Open-Meteo API.

This service handles weather data retrieval for both specific locations
and the configured home location.
"""

import requests

from local_llhama import simple_functions_helpers as helpers


CLASS_PREFIX_MESSAGE = "[WeatherService]"


class WeatherService:
    """Service for weather data retrieval using Open-Meteo API."""

    def __init__(self, web_search_config: dict, home_location: dict = None):
        """
        Initialize the weather service.

        @param web_search_config Configuration dict with Open-Meteo URLs and timeouts
        @param home_location Optional dict with latitude/longitude for home location
        """
        self.web_search_config = web_search_config
        self.home_location = home_location

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
