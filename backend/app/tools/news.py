"""News tool — fetches headlines from NewsAPI."""

import os

import httpx


def _dedupe(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for a in articles:
        key = a.get("url") or a.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


async def fetch_news(query: str | None = None) -> dict:
    """Fetch latest news, optionally filtered by *query*."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY is not configured.", "articles": []}

    params: dict = {"apiKey": api_key, "pageSize": 10, "language": "en"}
    if query:
        endpoint = "https://newsapi.org/v2/everything"
        params["q"] = query
        params["sortBy"] = "publishedAt"
    else:
        endpoint = "https://newsapi.org/v2/top-headlines"
        params["country"] = "in"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(endpoint, params=params)
        resp.raise_for_status()
        data = resp.json()

    articles = _dedupe(data.get("articles") or [])[:6]
    return {
        "articles": [
            {
                "title": a.get("title", "Untitled"),
                "source": (a.get("source") or {}).get("name", "Unknown"),
                "description": a.get("description") or "",
                "url": a.get("url", ""),
            }
            for a in articles
        ]
    }
