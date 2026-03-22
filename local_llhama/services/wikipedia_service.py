"""
@file wikipedia_service.py
@brief Service for fetching Wikipedia article summaries and handling complex queries.

This service handles Wikipedia article retrieval, including:
- Direct article lookups
- OpenSearch title matching
- Compound queries (e.g., "honey and gastritis")
- Fallback to memory search when articles aren't found
"""

import requests
from bs4 import BeautifulSoup

from local_llhama import simple_functions_helpers as helpers
from local_llhama.error_handler import ErrorHandler
from local_llhama.shared_logger import LogLevel

CLASS_PREFIX_MESSAGE = "[WikipediaService]"


class WikipediaService:
    """Service for Wikipedia article retrieval and search."""

    def __init__(
        self,
        web_search_config: dict,
        headers: dict,
        allow_internet_searches: bool,
        pg_client=None,
        find_in_memory_callback=None,
    ):
        """
        Initialize the Wikipedia service.

        @param web_search_config Configuration dict with Wikipedia/Wikimedia URLs and timeouts
        @param headers HTTP headers for requests
        @param allow_internet_searches Whether internet searches are enabled
        @param pg_client PostgreSQL client for memory fallback
        @param find_in_memory_callback Callback function for memory search fallback
        """
        self.web_search_config = web_search_config
        self.headers = headers
        self.allow_internet_searches = allow_internet_searches
        self.pg_client = pg_client
        self.find_in_memory = find_in_memory_callback

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
        timeout = self.web_search_config.get("timeout", 10)

        # Step 1: Try direct lookup
        text = self._fetch_wikipedia_article_text(
            topic_formatted, wiki_base_url, wikimedia_base_url, timeout
        )
        if text:
            return text

        # Step 2: Not found directly — search Wikipedia for the best matching article title
        alt_titles = self._search_wikipedia_title(topic, wiki_base_url, timeout)
        for alt in alt_titles[:3]:
            alt_formatted = "_".join(alt.strip().split())
            text = self._fetch_wikipedia_article_text(
                alt_formatted, wiki_base_url, wikimedia_base_url, timeout
            )
            if text:
                return f"(Wikipedia article: {alt})\n{text}"

        # Step 3: Try compound query (e.g. "honey and gastritis")
        compound = self._handle_compound_wikipedia_query(
            topic, user_id, wiki_base_url, wikimedia_base_url, timeout
        )
        if compound:
            return compound

        # Step 4: Fall back to memory search
        return helpers.wikipedia_fallback_to_memory(
            topic, user_id, self.pg_client, self.find_in_memory
        )

    def _handle_compound_wikipedia_query(
        self, topic, user_id, wiki_base_url, wikimedia_base_url, timeout
    ):
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
        splitters = r"\s+(?:and|or|vs|versus|with|plus)\s+"
        topics = re.split(splitters, topic, flags=re.IGNORECASE)

        # Clean and filter topics
        topics = [t.strip() for t in topics if t.strip() and len(t.strip()) > 2]

        # Limit to max 3 topics to avoid overwhelming
        topics = topics[:3]

        if len(topics) < 2:
            # Not a compound query, return None to use fallback
            return None

        print(
            f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Compound query detected: {topics}"
        )

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

                    html_resp = requests.get(
                        html_url, headers=self.headers, timeout=timeout
                    )
                    html_resp.raise_for_status()

                    soup = BeautifulSoup(html_resp.text, "html.parser")

                    # Remove unwanted elements
                    for element in soup(
                        [
                            "script",
                            "style",
                            "nav",
                            "footer",
                            "header",
                            "table",
                            "figure",
                        ]
                    ):
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
                print(
                    f"{CLASS_PREFIX_MESSAGE} [{LogLevel.WARNING.name}] Failed to fetch '{sub_topic}': {e}"
                )
                continue

        if summaries:
            combined = "\n\n".join(summaries)
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] Combined {len(summaries)} Wikipedia summaries"
            )
            return combined

        return None

    def _search_wikipedia_title(
        self, query: str, wiki_base_url: str, timeout: int
    ) -> list:
        """
        @brief Use Wikipedia's OpenSearch API to find matching article titles for a query.

        Called when a direct page lookup returns 404, to discover the canonical
        article name for the user's intent (e.g. "How airplanes fly" → "Fixed-wing aircraft").

        @param query        The user-supplied search string.
        @param wiki_base_url Wikipedia REST base URL (used to derive the domain).
        @param timeout      Request timeout in seconds.
        @return List of matching article title strings (may be empty).
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(wiki_base_url)
            api_url = f"{parsed.scheme}://{parsed.netloc}/w/api.php"
            resp = requests.get(
                api_url,
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": "5",
                    "namespace": "0",
                    "format": "json",
                    "redirects": "resolve",
                },
                headers=self.headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # opensearch returns [query_str, [titles], [descriptions], [urls]]
            titles = data[1] if len(data) > 1 else []
            print(
                f"{CLASS_PREFIX_MESSAGE} [{LogLevel.INFO.name}] "
                f"Wikipedia OpenSearch for {query!r} → {titles}"
            )
            return titles
        except Exception as e:
            ErrorHandler.log_error(
                CLASS_PREFIX_MESSAGE, e, LogLevel.WARNING, "Wikipedia OpenSearch"
            )
            return []

    def _fetch_wikipedia_article_text(
        self,
        topic_formatted: str,
        wiki_base_url: str,
        wikimedia_base_url: str,
        timeout: int,
        limit_paragraphs: int = 3,
        max_chars: int = 500,
    ):
        """
        @brief Fetch and parse article text from Wikipedia for a given topic slug.

        Resolves the canonical title via the summary endpoint, then fetches the
        full HTML to extract clean paragraph text.

        @param topic_formatted  URL-safe topic string (spaces replaced with underscores).
        @param wiki_base_url    Wikipedia REST base URL.
        @param wikimedia_base_url Wikimedia REST base URL (for HTML endpoint).
        @param timeout          Request timeout in seconds.
        @param limit_paragraphs Max number of paragraphs to return.
        @param max_chars        Hard character limit on returned text.
        @return Extracted text string, or None if the article was not found / empty.
        """
        try:
            summary_data = helpers.make_http_request(
                f"{wiki_base_url}/page/summary/{topic_formatted}",
                self.headers,
                timeout=timeout,
            )
            if not summary_data or not summary_data.get("title"):
                return None

            canonical_title = summary_data["title"].replace(" ", "_")
            html_resp = requests.get(
                f"{wikimedia_base_url}/{canonical_title}/html",
                headers=self.headers,
                timeout=timeout,
            )
            html_resp.raise_for_status()

            soup = BeautifulSoup(html_resp.text, "html.parser")
            for element in soup(
                ["script", "style", "nav", "footer", "header", "table", "figure"]
            ):
                element.decompose()

            paragraphs = soup.find_all("p", limit=limit_paragraphs)
            text_parts = [
                p.get_text(separator=" ", strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 20
            ]
            if not text_parts:
                return None

            text = " ".join(text_parts)
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            return text
        except Exception:
            return None
