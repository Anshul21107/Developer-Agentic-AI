from duckduckgo_search import DDGS
from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState
from ..llm import get_llm

WEB_SEARCH_PROMPT = """Answer the user query using ONLY the web results below.
Be factual and concise. If results are insufficient, say so.
Do not mention training data or knowledge cutoff."""


def _web_search(query: str, max_results: int = 5) -> list[dict]:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("href", ""),
            "snippet": item.get("body", ""),
        }
        for item in results
        if item
    ]


def _format_results(results: list[dict]) -> str:
    lines = []
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        snippet = item.get("snippet") or ""
        lines.append(f"{idx}. {title}\n{snippet}\n{url}".strip())
    return "\n\n".join(lines)


async def web_search_tool_node(state: AgentState) -> dict:
    query = state.get("user_input", "")
    if not query.strip():
        return {"tool_context": "No query provided.", "agent": "web_search_agent"}
    try:
        results = _web_search(query, max_results=5)
    except Exception:
        return {"tool_context": "Web search failed.", "agent": "web_search_agent"}

    if not results:
        return {"tool_context": "No results found.", "agent": "web_search_agent"}

    llm = get_llm(streaming=False)
    payload = _format_results(results)
    prompt = f"User query: {query}\n\nWeb results:\n{payload}"
    response = await llm.ainvoke(
        [SystemMessage(content=WEB_SEARCH_PROMPT), HumanMessage(content=prompt)]
    )
    summary = response.content.strip()
    if not summary or "knowledge cutoff" in summary.lower():
        summary = payload
    return {"tool_context": summary, "agent": "web_search_agent"}
