import ast
import json
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from .rag_store import query_documents
from .state import AgentState
from ..db import SessionLocal
from ..llm import get_llm
from ..models import SessionEmail

EMAIL_DRAFT_SYSTEM_PROMPT = """You draft professional emails.
Return ONLY valid JSON with keys: to, subject, body.
If user didn't specify recipient, use an empty string for "to".
Keep the body concise and clear.
Use \\n for line breaks and \\n\\n for paragraphs in the body."""

EMAIL_EDIT_SYSTEM_PROMPT = """You update an existing email draft.
Return ONLY valid JSON with keys: to, subject, body.
Preserve the original paragraph breaks and use \\n for line breaks."""

EMAIL_REPAIR_SYSTEM_PROMPT = """Fix the content into valid JSON.
Return ONLY valid JSON with keys: to, subject, body."""


def _is_confirm(user_input: str) -> bool:
    lowered = user_input.lower().strip()
    return bool(
        re.search(
            r"\b(send|sent|confirm|approve|go ahead|yes send|send it|send email)\b",
            lowered,
        )
    )


def _is_cancel(user_input: str) -> bool:
    lowered = user_input.lower().strip()
    return bool(re.search(r"\b(cancel|stop|don't send|do not send)\b", lowered))


def _send_email(to_address: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_address = os.getenv("SMTP_FROM") or username
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not host or not username or not password or not from_address:
        raise RuntimeError("SMTP is not configured.")

    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=10) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.send_message(message)


def _first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == "\"":
            in_string = not in_string
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if not cleaned:
        raise json.JSONDecodeError("Empty response", cleaned, 0)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        candidate = _first_json_object(cleaned)
        if candidate:
            candidate = candidate.replace("\r\n", "\\n").replace("\n", "\\n")
            candidate = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(candidate)
                    if isinstance(parsed, (dict, list)):
                        return parsed
                except Exception:
                    pass
        raise


async def _repair_json(llm, content: str) -> dict:
    result = await llm.ainvoke(
        [
            SystemMessage(content=EMAIL_REPAIR_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ]
    )
    return _extract_json(result.content or "{}")


async def _safe_parse_json(llm, content: str) -> dict | None:
    try:
        return _extract_json(content)
    except json.JSONDecodeError:
        try:
            return await _repair_json(llm, content)
        except Exception:
            return None


async def email_tool_node(state: AgentState) -> dict:
    session_id = state.get("session_id")
    user_input = state.get("user_input", "")
    if not session_id:
        return {"tool_context": "No session available for email drafting.", "agent": "email_agent"}

    db: Session = SessionLocal()
    try:
        pending = (
            db.query(SessionEmail)
            .filter(SessionEmail.session_id == session_id, SessionEmail.status == "pending")
            .order_by(SessionEmail.created_at.desc())
            .first()
        )

        if pending:
            if _is_cancel(user_input):
                pending.status = "canceled"
                db.commit()
                return {
                    "tool_context": "Email draft canceled.",
                    "agent": "email_agent",
                }
            if _is_confirm(user_input):
                _send_email(pending.to_address, pending.subject, pending.body)
                pending.status = "sent"
                pending.sent_at = datetime.utcnow()
                db.commit()
                return {
                    "tool_context": "Email sent successfully.",
                    "agent": "email_agent",
                }

            llm = get_llm(streaming=False)
            edit_prompt = (
                "Update this draft using the user's instructions.\n\n"
                f"Draft:\nTo: {pending.to_address}\nSubject: {pending.subject}\n\n{pending.body}\n\n"
                f"User instructions:\n{user_input}"
            )
            result = await llm.ainvoke(
                [
                    SystemMessage(content=EMAIL_EDIT_SYSTEM_PROMPT),
                    HumanMessage(content=edit_prompt),
                ]
            )
            data = await _safe_parse_json(llm, result.content or "{}")
            if data is None:
                return {
                    "tool_context": (
                        "I couldn't parse the updated draft. Please rephrase the "
                        "changes or provide them in plain text."
                    ),
                    "agent": "email_agent",
                }
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                data = {}
            pending.to_address = (data.get("to") or pending.to_address).strip()
            pending.subject = (data.get("subject") or pending.subject).strip()
            pending.body = (data.get("body") or pending.body).strip()
            db.commit()
            return {
                "tool_context": (
                    "Draft updated. Please confirm before sending.\n\n"
                    f"To: {pending.to_address}\nSubject: {pending.subject}\n\n{pending.body}\n\n"
                    "Reply with 'send' to send or 'cancel' to discard."
                ),
                "agent": "email_agent",
            }

        rag_context = ""
        if state.get("has_documents", False):
            docs = query_documents(session_id, user_input, k=3)
            if docs:
                rag_context = "\n\n".join(
                    f"Source: {doc.metadata.get('source', 'unknown')}\n{doc.page_content}"
                    for doc in docs
                )

        llm = get_llm(streaming=False)
        prompt = user_input
        if rag_context:
            prompt = f"{user_input}\n\nUse this context if helpful:\n{rag_context}"

        result = await llm.ainvoke(
            [
                SystemMessage(content=EMAIL_DRAFT_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        data = await _safe_parse_json(llm, result.content or "{}")
        if data is None:
            return {
                "tool_context": (
                    "I couldn't parse the draft. Please retry the request or "
                    "provide the email details explicitly."
                ),
                "agent": "email_agent",
            }
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}
        to_address = (data.get("to") or "").strip()
        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()

        if not subject or not body:
            return {
                "tool_context": "Please provide a subject and message for the email.",
                "agent": "email_agent",
            }

        if not to_address:
            return {
                "tool_context": "Who should I send this email to? Please provide the recipient.",
                "agent": "email_agent",
            }

        draft = SessionEmail(
            session_id=session_id,
            to_address=to_address,
            subject=subject,
            body=body,
            status="pending",
        )
        db.add(draft)
        db.commit()

        return {
            "tool_context": (
                "Draft ready. Please confirm before sending.\n\n"
                f"To: {to_address}\nSubject: {subject}\n\n{body}\n\n"
                "Reply with 'send' to send or 'cancel' to discard."
            ),
            "agent": "email_agent",
        }
    finally:
        db.close()
