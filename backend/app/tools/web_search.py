"""Web search tool — uses DuckDuckGo for live web results."""

from duckduckgo_search import DDGS


async def search_web(query: str, max_results: int = 5) -> dict:
    """Search the web and return structured results."""
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception:
        return {"error": "Web search failed.", "results": []}

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("href", ""),
            "snippet": item.get("body", ""),
        }
        for item in raw
        if item
    ]
    return {"results": results}
