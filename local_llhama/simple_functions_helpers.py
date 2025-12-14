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


def make_http_request(url: str, headers: dict, params: dict = None, timeout: int = 10) -> dict:
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
        ErrorHandler.log_error(CLASS_PREFIX_MESSAGE, e, LogLevel.WARNING, f"HTTP request to {url}")
        return None


def check_internet_access(allow_internet_searches: bool) -> bool:
    """Check if internet searches are allowed."""
    return allow_internet_searches


def validate_input(value: str, param_name: str) -> str:
    """Validate and return error message if input is invalid."""
    if not value:
        return f"Please specify a {param_name}."
    return None


def wikipedia_fallback_to_memory(topic: str, user_id: int, pg_client, find_in_memory_func) -> str:
    """Fallback to memory search when Wikipedia doesn't have the article."""
    if not (user_id and pg_client):
        return f"No Wikipedia page found for: {topic}"
    
    print(f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Wikipedia page not found, searching memory for: {topic}")
    memory_results = find_in_memory_func(query=topic, user_id=user_id, limit=3)
    
    if isinstance(memory_results, list) and memory_results:
        # Filter results that contain the topic word
        topic_lower = topic.lower()
        relevant_results = [
            r for r in memory_results 
            if topic_lower in r['user_message'].lower() or 
               (r.get('assistant_response') and topic_lower in r['assistant_response'].lower())
        ]
        
        # Use filtered results if any contain the topic, otherwise use all
        final_results = relevant_results if relevant_results else memory_results
        
        response = f"No '{topic}' on Wikipedia, but here's what we discussed before:\n\n"
        for idx, result in enumerate(final_results, 1):
            response += f"{idx}. User asked: \\\"{result['user_message']}\\\" (relevance: {result['similarity']:.0%})\n"
            if result.get('assistant_response'):
                assistant_text = result['assistant_response']
                if len(assistant_text) > 200:
                    assistant_text = assistant_text[:197] + "..."
                response += f"   Assistant said: {assistant_text}\n\n"
        return response
    elif isinstance(memory_results, dict) and memory_results.get("error"):
        return f"No Wikipedia page found for: {topic}. {memory_results.get('message', '')}"
    
    return f"No Wikipedia page found for: {topic}"
