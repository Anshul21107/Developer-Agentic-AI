import json
import re
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from .agents.graph import agent_graph
from .agents.memory_agent import update_memory_summary
from .agents.rag_store import ingest_texts, has_documents
from .agents.web_search_agent import web_search_tool_node
from .db import Base, SessionLocal, engine, get_db
from .llm import get_llm
from .models import Message, Session as ChatSession, SessionDocument, SessionEmail
from .schemas import ChatRequest, DocumentRead, MessageRead, SessionRead

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


@app.post("/sessions", response_model=SessionRead)
def create_session(db: Session = Depends(get_db)):
    session = ChatSession(title=None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions", response_model=list[SessionRead])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()


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


async def _generate_title(user_message: str) -> str:
    llm = get_llm(streaming=False)
    prompt = (
        "Create a short, 3-6 word title for this chat based on the first message. "
        "Return only the title.\n\n"
        f"Message: {user_message}"
    )
    result = await llm.ainvoke(prompt)
    return result.content.strip().strip('"')


def _to_lc_messages(messages: list[Message]):
    lc_messages = []
    for msg in messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        else:
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages


@app.post("/chat/{session_id}/stream")
async def chat_stream(session_id: str, request: ChatRequest):
    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        user_message = Message(session_id=session_id, role="user", content=request.message)
        db.add(user_message)
        db.commit()

        message_count = (
            db.query(Message).filter(Message.session_id == session_id).count()
        )
        if message_count == 1 and not session.title:
            try:
                session.title = await _generate_title(request.message)
                db.commit()
            except Exception:
                db.rollback()

        history = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        lc_messages = _to_lc_messages(history)

        memory_summary = session.memory_summary
        agent_state = await agent_graph.ainvoke(
            {
                "session_id": session_id,
                "user_input": request.message,
                "memory_summary": memory_summary,
                "has_documents": has_documents(session_id),
                "has_pending_email": _has_pending_email(session_id, db),
            }
        )
        agent_name = agent_state.get("agent")
        tool_context = agent_state.get("tool_context", "")

        if not agent_name:
            gate = await _should_use_web_search(request.message)
            if gate.get("requires_web_search"):
                web_state = await web_search_tool_node({"user_input": request.message})
                agent_name = web_state.get("agent")
                tool_context = web_state.get("tool_context", "")

        system_prompt = _build_system_prompt(
            agent_name=agent_name or "general",
            tool_context=tool_context,
            memory_summary=memory_summary,
        )
        lc_messages.insert(0, SystemMessage(content=system_prompt))

        async def event_generator():
            chunks: list[str] = []
            try:
                if agent_name:
                    yield f"data: {json.dumps({'agent': agent_name})}\n\n"
                if agent_name in {"email_agent", "web_search_agent", "weather_agent", "news_agent"} and tool_context:
                    chunks.append(tool_context)
                    yield f"data: {json.dumps({'token': tool_context})}\n\n"
                else:
                    llm = get_llm(streaming=True)
                    async for chunk in llm.astream(lc_messages):
                        token = getattr(chunk, "content", "") or ""
                        if not token:
                            continue
                        chunks.append(token)
                        payload = json.dumps({"token": token})
                        yield f"data: {payload}\n\n"
            finally:
                assistant_text = "".join(chunks).strip()
                if assistant_text:
                    assistant_message = Message(
                        session_id=session_id,
                        role="assistant",
                        content=assistant_text,
                        agent=agent_name if agent_name else None,
                    )
                    db.add(assistant_message)
                    db.commit()
                    try:
                        session.memory_summary = await update_memory_summary(
                            session.memory_summary, request.message, assistant_text
                        )
                        db.commit()
                    except Exception:
                        db.rollback()
                yield "data: [DONE]\n\n"
                db.close()

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception:
        db.close()
        raise


def _has_pending_email(session_id: str, db: Session) -> bool:
    return (
        db.query(SessionEmail)
        .filter(SessionEmail.session_id == session_id, SessionEmail.status == "pending")
        .count()
        > 0
    )


def _build_system_prompt(
    agent_name: str, tool_context: str, memory_summary: str | None
) -> str:
    prompt_parts = [
        "You are a helpful assistant in an agentic chatbot.",
    ]
    if memory_summary:
        prompt_parts.append(f"Conversation summary:\n{memory_summary}")
    if agent_name == "rag_agent":
        prompt_parts.append(
            "Use the provided context when answering. If the context is missing, "
            "say what you do not know and ask a follow-up question."
        )
    if agent_name == "weather_agent":
        prompt_parts.append(
            "Answer as a weather assistant using the provided weather context."
        )
    if agent_name == "news_agent":
        prompt_parts.append(
            "Answer as a news assistant. Use the summarized bullets provided."
        )
    if agent_name == "web_search_agent":
        prompt_parts.append(
            "Answer as a web search assistant. Use only the provided summary."
        )
    if tool_context:
        prompt_parts.append(f"Context:\n{tool_context}")
    return "\n\n".join(prompt_parts)


async def _should_use_web_search(user_message: str) -> dict:
    llm = get_llm(streaming=False)
    prompt = (
        "Answer the question. If you are not confident or the answer may require "
        "up-to-date information, set requires_web_search=true.\n\n"
        "Return ONLY valid JSON with keys: answer, requires_web_search.\n\n"
        f"Question: {user_message}"
    )
    result = await llm.ainvoke(prompt)
    content = (result.content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"answer": "", "requires_web_search": False}


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
