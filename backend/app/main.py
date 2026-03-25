import warnings
warnings.filterwarnings("ignore", message=".*deprecated.*")

import json
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from .agents.graph import agent_graph
from .agents.memory_agent import update_memory_summary
from .agents.memory_extractor import extract_and_store_facts
from .agents.rag_store import ingest_texts, has_documents
from .db import Base, SessionLocal, engine, get_db
from .llm import get_llm
from .models import Message, Session as ChatSession, SessionDocument, SessionEmail, UserFact
from .schemas import ChatRequest, DocumentRead, MessageRead, SessionRead
from .websocket_manager import manager

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _ensure_column("messages", "agent", "VARCHAR")
    _ensure_column("sessions", "memory_summary", "TEXT")
    _ensure_column("sessions", "updated_at", "DATETIME")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS session_emails (
                    id VARCHAR PRIMARY KEY,
                    session_id VARCHAR NOT NULL,
                    to_address VARCHAR NOT NULL,
                    subject VARCHAR NOT NULL,
                    body TEXT NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at DATETIME,
                    sent_at DATETIME,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
        )


def _ensure_column(table: str, column: str, column_type: str) -> None:
    with engine.begin() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        columns = {row[1] for row in result}
        if column not in columns:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


# ---------------------------------------------------------------------------
# Session CRUD  (unchanged)
# ---------------------------------------------------------------------------


@app.post("/sessions", response_model=SessionRead)
def create_session(db: Session = Depends(get_db)):
    session = ChatSession(title=None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions", response_model=list[SessionRead])
def list_sessions(db: Session = Depends(get_db)):
    from sqlalchemy import func
    return (
        db.query(ChatSession)
        .order_by(func.coalesce(ChatSession.updated_at, ChatSession.created_at).desc())
        .all()
    )


@app.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
def get_messages(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
        .all()
    )


@app.get("/sessions/{session_id}/documents", response_model=list[DocumentRead])
def list_documents(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return (
        db.query(SessionDocument)
        .filter(SessionDocument.session_id == session_id)
        .order_by(SessionDocument.uploaded_at.asc())
        .all()
    )


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _generate_title(user_message: str) -> str:
    llm = get_llm(streaming=False)
    prompt = (
        "Create a short, 3-6 word title for this chat based on the first message. "
        "Return only the title.\n\n"
        f"Message: {user_message}"
    )
    result = await llm.ainvoke(prompt)
    return result.content.strip().strip('"')


def _has_pending_email(session_id: str, db: Session) -> bool:
    return (
        db.query(SessionEmail)
        .filter(SessionEmail.session_id == session_id, SessionEmail.status == "pending")
        .count()
        > 0
    )


# ---------------------------------------------------------------------------
# WebSocket chat endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            await websocket.close(code=4004, reason="Session not found")
            return

        await manager.connect(session_id, websocket)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if payload.get("type") != "user_message":
                    continue

                user_content = (payload.get("content") or "").strip()
                if not user_content:
                    continue

                # Store user message and bump session to top
                from .models import _ist_now
                user_msg = Message(session_id=session_id, role="user", content=user_content)
                db.add(user_msg)
                session.updated_at = _ist_now()
                db.commit()

                # Auto-generate title on first message
                message_count = db.query(Message).filter(Message.session_id == session_id).count()
                if message_count == 1 and not session.title:
                    try:
                        session.title = await _generate_title(user_content)
                        db.commit()
                    except Exception:
                        db.rollback()

                # Build conversation history as LangChain messages (last 20 for speed)
                history = (
                    db.query(Message)
                    .filter(Message.session_id == session_id)
                    .order_by(Message.timestamp.desc())
                    .limit(20)
                    .all()
                )
                history.reverse()
                lc_messages = []
                for msg in history:
                    if msg.role == "user":
                        lc_messages.append(HumanMessage(content=msg.content))
                    else:
                        lc_messages.append(AIMessage(content=msg.content))

                # Refresh session to get latest memory
                db.refresh(session)
                memory_summary = session.memory_summary

                # Run planner loop (tools execute in parallel inside)
                agent_state = await agent_graph.ainvoke(
                    {
                        "messages": lc_messages,
                        "session_id": session_id,
                        "memory_summary": memory_summary,
                        "has_documents": has_documents(session_id),
                        "has_pending_email": _has_pending_email(session_id, db),
                    }
                )

                # Extract final AI response
                final_messages = agent_state.get("messages", [])
                last_ai = None
                for m in reversed(final_messages):
                    if isinstance(m, AIMessage) and m.content:
                        last_ai = m
                        break

                assistant_text = last_ai.content.strip() if last_ai else ""
                agent_label = agent_state.get("agent_label") or "general"

                # Stream the response word-by-word
                if assistant_text:
                    await manager.send_json(session_id, {"type": "assistant_start"})

                    words = assistant_text.split(" ")
                    for i, word in enumerate(words):
                        token = word if i == 0 else " " + word
                        await manager.send_json(
                            session_id, {"type": "assistant_token", "content": token}
                        )

                    await manager.send_json(
                        session_id, {"type": "assistant_end", "agent": agent_label}
                    )

                    # Store assistant message
                    assistant_msg = Message(
                        session_id=session_id,
                        role="assistant",
                        content=assistant_text,
                        agent=agent_label,
                    )
                    db.add(assistant_msg)
                    db.commit()

                    # Update memory summary
                    try:
                        session.memory_summary = await update_memory_summary(
                            session.memory_summary, user_content, assistant_text
                        )
                        db.commit()
                    except Exception:
                        db.rollback()

                    # Extract personal facts in background (non-blocking)
                    import asyncio

                    def _log_bg_error(task):
                        if task.exception():
                            logging.getLogger(__name__).debug(
                                f"Fact extraction error: {task.exception()}"
                            )

                    bg = asyncio.create_task(
                        extract_and_store_facts(user_content, assistant_text)
                    )
                    bg.add_done_callback(_log_bg_error)

        except WebSocketDisconnect:
            manager.disconnect(session_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RAG upload  (unchanged)
# ---------------------------------------------------------------------------


def _extract_text_from_upload(filename: str, data: bytes) -> str | None:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return data.decode("utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            return None
        try:
            reader = PdfReader(BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return None
    return None


@app.post("/rag/upload")
async def upload_rag(
    session_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    texts: list[tuple[str, str]] = []
    skipped: list[str] = []
    saved: list[str] = []
    for upload in files:
        data = await upload.read()
        content = _extract_text_from_upload(upload.filename, data)
        if not content:
            skipped.append(upload.filename)
            continue
        texts.append((content, upload.filename))
        saved.append(upload.filename)
    if not texts:
        return {"status": "no_files", "skipped": skipped, "chunks": 0}
    chunks = ingest_texts(session_id, texts)
    for filename in saved:
        db.add(SessionDocument(session_id=session_id, filename=filename))
    db.commit()
    return {"status": "ok", "skipped": skipped, "chunks": chunks}


# ---------------------------------------------------------------------------
# User personalization facts
# ---------------------------------------------------------------------------


@app.get("/user/facts")
def get_user_facts(db: Session = Depends(get_db)):
    """Return all stored user facts."""
    facts = db.query(UserFact).order_by(UserFact.key).all()
    return [{"key": f.key, "value": f.value, "updated_at": str(f.updated_at)} for f in facts]


@app.delete("/user/facts/{key}")
def delete_user_fact(key: str, db: Session = Depends(get_db)):
    """Delete a specific user fact by key."""
    fact = db.query(UserFact).filter(UserFact.key == key).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    db.delete(fact)
    db.commit()
    return {"status": "deleted", "key": key}
