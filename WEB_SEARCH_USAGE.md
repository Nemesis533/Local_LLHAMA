# Web Search Function - Usage Guide

## Overview
The `web_search` function allows the LLM to search configured allowed websites and return synthetic summaries of the content. This is integrated into the SimpleFunctions class and can be invoked through the command system.

## Configuration
The allowed websites are configured in `/local_llhama/settings/web_search_config.json`:

```json
{
  "allowed_websites": [
    {
      "name": "Google News",
      "url": "https://news.google.com/home?hl=en-US&gl=US&ceid=US:en",
      "description": "News aggregator from various sources"
    },
    {
      "name": "Wikipedia",
      "url": "https://it.wikipedia.org",
      "description": "Free online encyclopedia"
    }
  ],
  "max_results": 3,
  "timeout": 10
}
```

## How the LLM Can Use It

### Command Format
The LLM should generate commands in this format:

```json
{
  "commands": [
    {
      "target": "web_search",
      "action": "web_search",
      "data": {
        "query": "artificial intelligence news",
        "website": "Wikipedia"
      }
    }
  ]
}
```

### Parameters
- **query** (optional): The search query or topic to look for
- **website** (optional): Specific website name to search (e.g., "Wikipedia", "Google News")

### Example Commands

1. **General web search:**
```json
{
  "target": "web_search",
  "action": "web_search",
  "data": {
    "query": "latest technology trends"
  }
}
```

2. **Search specific website:**
```json
{
  "target": "web_search",
  "action": "web_search",
  "data": {
    "query": "climate change",
    "website": "Wikipedia"
  }
}
```

3. **Search without query (gets homepage content):**
```json
{
  "target": "web_search",
  "action": "web_search"
}
```

## Response Format
The function returns a synthetic summary as a string:

```
Web search results for 'your query':

1. Google News: [Summarized content from Google News...]
2. Wikipedia: [Summarized content from Wikipedia...]
```

## Features
- ✅ Only searches allowed/configured websites
- ✅ Returns synthetic summaries (max 500 chars per site)
- ✅ Cleans HTML and extracts readable text
- ✅ Handles timeouts and errors gracefully
- ✅ Supports filtering to specific websites
- ✅ Integrated with existing command system

## Security
- Only websites explicitly listed in the config file can be searched
- Default timeout of 10 seconds prevents hanging
- User-Agent header included for proper web requests
- HTML parsing removes scripts, styles, and navigation elements

## Adding New Websites
To allow the LLM to search additional websites, add them to `web_search_config.json`:

```json
{
  "name": "Website Name",
  "url": "https://example.com",
  "description": "Description of the website"
}
```

## Testing
Run the test script to verify functionality:
```bash
python test_web_search.py
```
