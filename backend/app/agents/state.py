from typing import Literal, TypedDict

Intent = Literal["general", "rag", "weather", "email", "news", "web_search"]


class AgentState(TypedDict, total=False):
    session_id: str
    user_input: str
    intent: Intent
    tool_context: str
    agent: str | None
    memory_summary: str | None
    has_documents: bool
    has_pending_email: bool
