import os
from pathlib import Path
from typing import Iterable

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

BASE_DIR = Path(__file__).resolve().parents[1]
RAG_DIR = BASE_DIR / "storage" / "rag"
RAG_DIR.mkdir(parents=True, exist_ok=True)

_embeddings: HuggingFaceEmbeddings | None = None
_vectorstore: Chroma | None = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
        os.environ.setdefault("CHROMA_TELEMETRY", "false")
        model_name = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        _embeddings = HuggingFaceEmbeddings(model_name=model_name)
    return _embeddings


def _collection_name(session_id: str) -> str:
    return f"rag_{session_id}"


def _get_vectorstore(session_id: str) -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            collection_name=_collection_name(session_id),
            persist_directory=str(RAG_DIR),
            embedding_function=_get_embeddings(),
        )
    else:
        _vectorstore = Chroma(
            collection_name=_collection_name(session_id),
            persist_directory=str(RAG_DIR),
            embedding_function=_get_embeddings(),
        )
    return _vectorstore


def ingest_texts(session_id: str, texts: Iterable[tuple[str, str]]) -> int:
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
    documents: list[Document] = []
    for text, source in texts:
        if not text.strip():
            continue
        docs = splitter.split_documents(
            [Document(page_content=text, metadata={"source": source})]
        )
        documents.extend(docs)
    if not documents:
        return 0
    vectorstore = _get_vectorstore(session_id)
    vectorstore.add_documents(documents)
    return len(documents)


def query_documents(session_id: str, query: str, k: int = 4) -> list[Document]:
    if not query.strip():
        return []
    vectorstore = _get_vectorstore(session_id)
    return vectorstore.similarity_search(query, k=k)


def has_documents(session_id: str) -> bool:
    try:
        vectorstore = _get_vectorstore(session_id)
        return vectorstore._collection.count() > 0
    except Exception:
        return False
