"""Planner node — calls the LLM with tool schemas bound."""

from langchain_core.messages import SystemMessage

from .state import AgentState
from .memory_extractor import get_all_facts
from ..llm import get_llm
from ..tools.registry import get_tool_definitions

SYSTEM_PROMPT_BASE = (
    "You are a helpful assistant with access to tools.\n"
    "Only call tools that are directly relevant to the user's question.\n"
    "Do NOT call tools the user did not ask about (e.g. don't call weather "
    "for a price question, don't draft emails unless asked).\n"
    "When no tool is needed, respond directly from your knowledge."
)


def _build_system_prompt(state: AgentState) -> str:
    parts = [SYSTEM_PROMPT_BASE]

    # Inject personalization facts
    facts = get_all_facts()
    if facts:
        lines = [f"- {f['key']}: {f['value']}" for f in facts]
        parts.append(
            "You know the following about the user. Use these facts to "
            "personalize responses: greet by name, resolve ambiguities "
            "(e.g. 'the city' or 'my city' means their location, 'weather' "
            "without a city means their location). Do NOT proactively call "
            "tools just because facts exist — only when the user asks:\n"
            + "\n".join(lines)
        )

    summary = state.get("memory_summary")
    if summary:
        parts.append(f"Conversation summary so far:\n{summary}")
    if state.get("has_documents"):
        parts.append(
            "The user has uploaded documents in this session. "
            "Use query_rag only if the user's question is about those documents."
        )
    if state.get("has_pending_email"):
        parts.append(
            "There is a pending email draft in this session. "
            "The user may want to edit, send, or cancel it."
        )
    return "\n\n".join(parts)


async def planner_node(state: AgentState) -> dict:
    """Call the LLM with tool schemas; return its response message."""
    system_prompt = _build_system_prompt(state)
    messages = list(state.get("messages", []))

    # Inject system prompt at the front if not already there
    if not messages or not isinstance(messages[0], SystemMessage):
        messages.insert(0, SystemMessage(content=system_prompt))
    else:
        messages[0] = SystemMessage(content=system_prompt)

    # Gate tool visibility based on current state
    exclude: set[str] = set()
    if not state.get("has_documents"):
        exclude.add("query_rag")
    if not state.get("has_pending_email"):
        exclude.update({"send_email", "edit_email", "cancel_email"})

    llm = get_llm(streaming=False)
    tools = get_tool_definitions(exclude=exclude)
    llm_with_tools = llm.bind_tools(tools)

    try:
        response = await llm_with_tools.ainvoke(messages)
    except Exception:
        # Groq sometimes rejects malformed tool calls — retry without tools
        response = await llm.ainvoke(messages)

    return {"messages": [response]}
