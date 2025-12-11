"""
Home Assistant Client Core Module

Handles connection management, configuration, and low-level HTTP communication
with the Home Assistant API.
"""

# === System Imports ===
import os
import time

import requests
from dotenv import load_dotenv

# === Custom Imports ===
from ..Shared_Logger import LogLevel


class HARequestHandler:
    """
    Handles HTTP requests to Home Assistant with retry logic and error handling.

    Provides robust HTTP request handling with exponential backoff retry logic,
    timeout management, and comprehensive error handling for communication with
    Home Assistant API.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """
        Initialize the request handler with configuration.

        @param base_url Base URL for Home Assistant API
        @param token Authentication token
        @param timeout Request timeout in seconds
        @param max_retries Maximum number of retry attempts
        @param retry_delay Initial delay between retries in seconds
        """
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.class_prefix_message = "[HomeAssistant]"

    def retry_request(self, method: str, url: str, **kwargs):
        """
        Execute HTTP request with retry logic and exponential backoff.

        @param method HTTP method ('GET' or 'POST')
        @param url The URL to request
        @param kwargs Additional arguments for requests (json, headers, etc.)
        @return Response object if successful
        @raises requests.exceptions.RequestException after all retries fail
        """
        kwargs.setdefault("timeout", self.timeout)

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, **kwargs)
                elif method.upper() == "POST":
                    response = requests.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout as e:
                last_exception = e
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Timeout on attempt {attempt + 1}/{self.max_retries}: {url}"
                )

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Connection error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )

            except requests.exceptions.HTTPError as e:
                # Don't retry 4xx errors (client errors like auth failure)
                if 400 <= e.response.status_code < 500:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Client error {e.response.status_code}: {e}"
                    )
                    raise
                last_exception = e
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] HTTP error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )

            except requests.exceptions.RequestException as e:
                last_exception = e
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Request error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )

            # Exponential backoff before retry
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2**attempt)
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Retrying in {delay} seconds..."
                )
                time.sleep(delay)

        # All retries failed
        error_msg = f"Failed to connect to Home Assistant at {self.base_url} after {self.max_retries} attempts"
        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] {error_msg}")
        if last_exception:
            raise requests.exceptions.RequestException(error_msg) from last_exception
        raise requests.exceptions.RequestException(error_msg)


class HAClientCore:
    """
    Core Home Assistant client managing connection configuration.

    This class handles the basic connection setup, environment variable loading,
    and provides the request handler for making API calls to Home Assistant.
    """

    def __init__(self):
        """Initialize the core client with configuration from environment."""
        # Load environment variables
        load_dotenv()

        # Load sensitive configuration from environment variables
        self.base_url = os.getenv("HA_BASE_URL", "")
        self.token = os.getenv("HA_TOKEN", "")

        # Connection configuration
        self.timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 2  # seconds

        # Initialize request handler
        self.request_handler = HARequestHandler(
            self.base_url, self.token, self.timeout, self.max_retries, self.retry_delay
        )

    def validate_connection(self) -> bool:
        """
        Validate that the Home Assistant connection is properly configured.

        @return True if connection parameters are valid, False otherwise
        """
        if not self.base_url or not self.token:
            return False
        return True
