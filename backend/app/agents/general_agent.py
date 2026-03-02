from .state import AgentState


async def general_tool_node(state: AgentState) -> dict:
    return {"tool_context": "", "agent": None}
