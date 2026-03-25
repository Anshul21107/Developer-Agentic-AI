"""LangGraph planner ↔ tool_executor loop."""

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from .planner import planner_node
from .state import AgentState
from .tool_executor import tool_executor_node


def _should_continue(state: AgentState) -> str:
    """Route: if the last message has tool_calls → execute, else → finish."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tool_executor"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_executor", tool_executor_node)

    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", _should_continue, {
        "tool_executor": "tool_executor",
        END: END,
    })
    graph.add_edge("tool_executor", "planner")

    return graph.compile()


agent_graph = build_graph()
