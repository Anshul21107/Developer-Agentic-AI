"""Tool executor node — runs tool calls from the last LLM message."""

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from .state import AgentState
from ..tools.registry import execute_tool


# Map tool names to user-friendly agent labels
_AGENT_LABELS: dict[str, str] = {
    "get_weather": "weather_agent",
    "query_rag": "rag_agent",
    "search_web": "web_search_agent",
    "fetch_news": "news_agent",
    "draft_email": "email_agent",
    "edit_email": "email_agent",
    "send_email": "email_agent",
    "cancel_email": "email_agent",
}


async def tool_executor_node(state: AgentState) -> dict:
    """Execute every tool_call in the last AIMessage in PARALLEL."""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return {}

    session_id = state.get("session_id", "")
    session_tools = {"query_rag", "draft_email", "edit_email", "send_email", "cancel_email"}

    # Prepare args for each call
    calls_with_args = []
    for call in last_msg.tool_calls:
        name = call["name"]
        args = dict(call["args"])
        if name in session_tools:
            args["session_id"] = session_id
        calls_with_args.append((call, name, args))

    # Execute ALL tools in parallel
    results = await asyncio.gather(
        *(execute_tool(name, args) for _, name, args in calls_with_args)
    )

    # Build ToolMessages and labels
    tool_messages: list[ToolMessage] = []
    seen_labels: list[str] = []

    for (call, name, _), result in zip(calls_with_args, results):
        tool_messages.append(
            ToolMessage(content=result, tool_call_id=call["id"])
        )
        if '"error"' not in result:
            label = _AGENT_LABELS.get(name, name)
            if label not in seen_labels:
                seen_labels.append(label)

    return {"messages": tool_messages, "agent_label": ",".join(seen_labels)}
