import os
from datetime import datetime, timezone

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState
from ..llm import get_llm

NEWS_SUMMARY_PROMPT = """You rephrase ONLY the provided news articles.
Do not add or invent information.
Return 4-6 bullet points, each starting with a hyphen and include the source name in parentheses.
If no articles are provided, respond exactly: No news found for this topic."""


def _dedupe_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    deduped: list[dict] = []
    for article in articles:
        key = article.get("url") or article.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


def _format_articles(articles: list[dict]) -> str:
    lines = []
    for idx, article in enumerate(articles, start=1):
        title = article.get("title", "Untitled")
        source = (article.get("source") or {}).get("name", "Unknown")
        snippet = article.get("description") or article.get("content") or ""
        url = article.get("url", "")
        lines.append(f"{idx}. {title} ({source})\n{snippet}\n{url}".strip())
    return "\n".join(lines)


async def _fetch_news(query: str | None) -> list[dict]:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return []
    params = {"apiKey": api_key, "pageSize": 10, "language": "en"}
    if query:
        endpoint = "https://newsapi.org/v2/everything"
        params["q"] = query
        params["sortBy"] = "publishedAt"
    else:
        endpoint = "https://newsapi.org/v2/top-headlines"
        params["country"] = "in"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(endpoint, params=params)
        res.raise_for_status()
        data = res.json()
        return data.get("articles") or []


def _extract_query(user_input: str) -> str | None:
    lowered = user_input.lower()
    for prefix in ["news about", "headlines about", "latest on", "updates on"]:
        if prefix in lowered:
            return user_input.lower().split(prefix, 1)[-1].strip()
    return None


async def news_tool_node(state: AgentState) -> dict:
    user_input = state.get("user_input", "")
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {
            "tool_context": "NEWS_API_KEY is not configured. Add it to the backend .env file.",
            "agent": "news_agent",
        }

    query = _extract_query(user_input)
    try:
        articles = await _fetch_news(query)
    except Exception:
        return {
            "tool_context": "Unable to fetch news right now.",
            "agent": "news_agent",
        }

    articles = _dedupe_articles(articles)[:6]
    if not articles:
        return {"tool_context": "No news articles were found.", "agent": "news_agent"}

    llm = get_llm(streaming=False)
    payload = _format_articles(articles)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    prompt = f"Time: {now}\n\nUser query: {user_input}\n\nArticles:\n{payload}"
    summary = await llm.ainvoke(
        [SystemMessage(content=NEWS_SUMMARY_PROMPT), HumanMessage(content=prompt)]
    )
    content = summary.content.strip()
    if not content or "knowledge cutoff" in content.lower():
        content = payload
    return {"tool_context": content, "agent": "news_agent"}
