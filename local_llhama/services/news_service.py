"""
@file news_service.py
@brief Service for fetching news articles using GDELT API.

This service handles news article retrieval from GDELT, which monitors
news sources worldwide in real-time.
"""

import requests

from local_llhama import simple_functions_helpers as helpers


CLASS_PREFIX_MESSAGE = "[NewsService]"


class NewsService:
    """Service for news article retrieval using GDELT API."""

    def __init__(self, web_search_config: dict, allow_internet_searches: bool):
        """
        Initialize the news service.

        @param web_search_config Configuration dict with GDELT URL and settings
        @param allow_internet_searches Whether internet searches are enabled
        """
        self.web_search_config = web_search_config
        self.allow_internet_searches = allow_internet_searches

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
