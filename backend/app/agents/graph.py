from langgraph.graph import END, StateGraph
from .email_agent import email_tool_node
from .general_agent import general_tool_node
from .news_agent import news_tool_node
from .web_search_agent import web_search_tool_node
from .intent_agent import intent_node
from .rag_agent import rag_tool_node
from .state import AgentState
from .weather_agent import weather_tool_node


def _route_intent(state: AgentState) -> str:
    return state.get("intent", "general")


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("intent_router", intent_node)
    graph.add_node("rag", rag_tool_node)
    graph.add_node("weather", weather_tool_node)
    graph.add_node("email", email_tool_node)
    graph.add_node("news", news_tool_node)
    graph.add_node("web_search", web_search_tool_node)
    graph.add_node("general", general_tool_node)

    graph.set_entry_point("intent_router")
    graph.add_conditional_edges(
        "intent_router",
        _route_intent,
        {
            "rag": "rag",
            "weather": "weather",
            "email": "email",
            "news": "news",
            "web_search": "web_search",
            "general": "general",
        },
    )
    graph.add_edge("rag", END)
    graph.add_edge("weather", END)
    graph.add_edge("email", END)
    graph.add_edge("news", END)
    graph.add_edge("web_search", END)
    graph.add_edge("general", END)

    return graph.compile()


agent_graph = build_graph()
