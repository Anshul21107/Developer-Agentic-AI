"""Email tools — draft, edit, send, cancel email lifecycle."""

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import SessionEmail


def _smtp_send(to_address: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_address = os.getenv("SMTP_FROM") or username
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not host or not username or not password or not from_address:
        raise RuntimeError("SMTP is not configured.")

    msg = EmailMessage()
    msg["From"] = from_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=10) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.send_message(msg)


def _get_pending(session_id: str, db: Session) -> SessionEmail | None:
    return (
        db.query(SessionEmail)
        .filter(SessionEmail.session_id == session_id, SessionEmail.status == "pending")
        .order_by(SessionEmail.created_at.desc())
        .first()
    )


async def draft_email(session_id: str, to: str, subject: str, body: str) -> dict:
    """Create a new email draft stored in the database."""
    db: Session = SessionLocal()
    try:
        # Cancel any existing pending draft first
        existing = _get_pending(session_id, db)
        if existing:
            existing.status = "canceled"

        draft = SessionEmail(
            session_id=session_id,
            to_address=to,
            subject=subject,
            body=body,
            status="pending",
        )
        db.add(draft)
        db.commit()
        return _draft_response(to, subject, body)
    finally:
        db.close()


def _draft_response(to: str, subject: str, body: str) -> dict:
    return {
        "status": "drafted",
        "to": to,
        "subject": subject,
        "body": body,
        "display": (
            f"📧 **Email Draft**\n\n"
            f"**To:** {to}\n\n"
            f"**Subject:** {subject}\n\n"
            f"**Body:**\n\n{body}\n\n"
            f"---\n\n"
            f"Would you like to **send**, **edit**, or **cancel** this draft?"
        ),
        "message": (
            "Email draft created. Show the 'display' field content exactly "
            "as-is to the user. Do not rephrase it."
        ),
    }


async def edit_email(
    session_id: str,
    to: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict:
    """Edit the pending email draft — update only the fields provided."""
    db: Session = SessionLocal()
    try:
        pending = _get_pending(session_id, db)
        if not pending:
            return {"error": "No pending email draft to edit."}

        if to is not None:
            pending.to_address = to
        if subject is not None:
            pending.subject = subject
        if body is not None:
            pending.body = body
        db.commit()

        return _draft_response(pending.to_address, pending.subject, pending.body)
    finally:
        db.close()


async def send_email(session_id: str) -> dict:
    """Send the pending email draft via SMTP."""
    db: Session = SessionLocal()
    try:
        pending = _get_pending(session_id, db)
        if not pending:
            return {"error": "No pending email draft to send."}

        try:
            _smtp_send(pending.to_address, pending.subject, pending.body)
        except Exception as exc:
            return {"error": f"Failed to send email: {exc}"}

        pending.status = "sent"
        pending.sent_at = datetime.utcnow()
        db.commit()
        return {
            "status": "sent",
            "to": pending.to_address,
            "subject": pending.subject,
            "message": "Email sent successfully.",
        }
    finally:
        db.close()


async def cancel_email(session_id: str) -> dict:
    """Cancel the pending email draft."""
    db: Session = SessionLocal()
    try:
        pending = _get_pending(session_id, db)
        if not pending:
            return {"error": "No pending email draft to cancel."}

        pending.status = "canceled"
        db.commit()
        return {"status": "canceled", "message": "Email draft canceled."}
    finally:
        db.close()
