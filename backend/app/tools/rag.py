"""RAG tool — queries session-specific ChromaDB for document context."""

from ..agents.rag_store import query_documents


async def query_rag(session_id: str, query: str, k: int = 4) -> dict:
    """Retrieve the top-*k* document chunks matching *query*."""
    docs = query_documents(session_id, query, k=k)
    if not docs:
        return {"results": [], "message": "No relevant documents found."}
    return {
        "results": [
            {
                "source": doc.metadata.get("source", "unknown"),
                "content": doc.page_content,
            }
            for doc in docs
        ]
    }
