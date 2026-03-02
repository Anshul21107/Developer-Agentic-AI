from .rag_store import query_documents
from .state import AgentState


async def rag_tool_node(state: AgentState) -> dict:
    query = state.get("user_input", "")
    session_id = state.get("session_id", "")
    docs = query_documents(session_id, query, k=4)
    if not docs:
        context = "No relevant documents were found in the knowledge base."
    else:
        context = "\n\n".join(
            f"Source: {doc.metadata.get('source', 'unknown')}\n{doc.page_content}"
            for doc in docs
        )
    return {"tool_context": context, "agent": "rag_agent"}
