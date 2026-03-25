"""Central tool registry — maps tool names to implementations.

Designed so that ``execute_tool`` can later be swapped with an MCP client call
without touching the rest of the codebase.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Coroutine

from langchain_core.tools import StructuredTool

from .schemas import (
    CancelEmailInput,
    DraftEmailInput,
    EditEmailInput,
    FetchNewsInput,
    GetWeatherInput,
    QueryRagInput,
    SearchWebInput,
    SendEmailInput,
)
from .weather import get_weather
from .rag import query_rag
from .web_search import search_web
from .news import fetch_news
from .email import draft_email, edit_email, send_email, cancel_email


# ---------------------------------------------------------------------------
# Internal registry  (name → async callable)
# ---------------------------------------------------------------------------

_TOOL_FUNCTIONS: dict[str, Callable[..., Coroutine[Any, Any, dict]]] = {
    "get_weather": get_weather,
    "query_rag": query_rag,
    "search_web": search_web,
    "fetch_news": fetch_news,
    "draft_email": draft_email,
    "edit_email": edit_email,
    "send_email": send_email,
    "cancel_email": cancel_email,
}

# ---------------------------------------------------------------------------
# LangChain StructuredTool wrappers  (used to bind to the LLM)
# ---------------------------------------------------------------------------

_SCHEMA_MAP: dict[str, type] = {
    "get_weather": GetWeatherInput,
    "query_rag": QueryRagInput,
    "search_web": SearchWebInput,
    "fetch_news": FetchNewsInput,
    "draft_email": DraftEmailInput,
    "edit_email": EditEmailInput,
    "send_email": SendEmailInput,
    "cancel_email": CancelEmailInput,
}


def get_tool_definitions(exclude: set[str] | None = None) -> list[StructuredTool]:
    """Return LangChain StructuredTool objects for LLM binding.
    
    Pass *exclude* to hide tools the LLM should not see in this turn.
    """
    exclude = exclude or set()
    tools: list[StructuredTool] = []
    for name, func in _TOOL_FUNCTIONS.items():
        if name in exclude:
            continue
        schema = _SCHEMA_MAP[name]
        tools.append(
            StructuredTool.from_function(
                coroutine=func,
                name=name,
                description=schema.__doc__ or "",
                args_schema=schema,
            )
        )
    return tools


# ---------------------------------------------------------------------------
# Dynamic executor  (MCP-swappable)
# ---------------------------------------------------------------------------


async def execute_tool(name: str, args: dict) -> str:
    """Execute a tool by *name* with *args*.  Returns JSON string.

    To migrate to MCP, replace the body with:
        return await mcp_client.call(name, args)
    """
    func = _TOOL_FUNCTIONS.get(name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = await func(**args)
    except Exception as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str)
