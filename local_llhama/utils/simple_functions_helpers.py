"""
Helper functions for SimpleFunctions class.

Contains utility methods for HTTP requests, input validation, and configuration loading.
"""

import requests

from .error_handler import ErrorHandler
from .shared_logger import LogLevel

CLASS_PREFIX_MESSAGE = "[SimpleFunctions]"


def get_config_url(web_search_config: dict, site_name: str, default_url: str) -> str:
    """Get URL from web search config by site name."""
    for site in web_search_config.get("allowed_websites", []):
        if site.get("name", "").lower() == site_name.lower():
            return site.get("url", default_url)
    return default_url


def make_http_request(
    url: str, headers: dict, params: dict = None, timeout: int = 10
) -> dict:
    """
    Make HTTP GET request with error handling.

    @param url URL to request
    @param headers HTTP headers dict
    @param params Query parameters
    @param timeout Request timeout
    @return JSON response or None on error
    """
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        ErrorHandler.log_error(
            CLASS_PREFIX_MESSAGE, e, LogLevel.WARNING, f"HTTP request to {url}"
        )
        return None


def check_internet_access(allow_internet_searches: bool) -> bool:
    """Check if internet searches are allowed."""
    return allow_internet_searches


def validate_input(value: str, param_name: str) -> str:
    """Validate and return error message if input is invalid."""
    if not value:
        return f"Please specify a {param_name}."
    return None


def wikipedia_fallback_to_memory(
    topic: str, user_id: int, pg_client, find_in_memory_func
) -> str:
    """Fallback to memory search when Wikipedia doesn't have the article."""
    if not (user_id and pg_client):
        return f"No Wikipedia page found for: {topic}"

    print(
        f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Wikipedia page not found, searching memory for: {topic}"
    )
    memory_results = find_in_memory_func(query=topic, user_id=user_id, limit=3)

    # find_in_memory now returns a formatted string
    if isinstance(memory_results, str):
        # If it's an error message or "no memories found", return Wikipedia error
        if (
            "No memories found" in memory_results
            or "not configured" in memory_results
            or "No query provided" in memory_results
            or "Could not" in memory_results
        ):
            return f"No Wikipedia page found for: {topic}"

        # Otherwise, prepend context and return the memory results
        return f"No '{topic}' on Wikipedia, but here's what we discussed before:\n\n{memory_results}"

    # Fallback in case old format is still somehow returned
    return f"No Wikipedia page found for: {topic}"
