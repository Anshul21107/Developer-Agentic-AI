"""Agent graph state definition."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State flowing through the planner ↔ tool_executor loop."""

    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    memory_summary: str | None
    has_documents: bool
    has_pending_email: bool
    agent_label: str | None
