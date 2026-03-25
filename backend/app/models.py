import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from .db import Base

IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _ist_now():
    return datetime.now(IST_TZ)


def _uuid():
    return str(uuid.uuid4())


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=True)
    memory_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_ist_now)
    updated_at = Column(DateTime, default=_ist_now, onupdate=_ist_now)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    documents = relationship(
        "SessionDocument", back_populates="session", cascade="all, delete-orphan"
    )
    emails = relationship(
        "SessionEmail", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    agent = Column(String, nullable=True)
    timestamp = Column(DateTime, default=_ist_now)

    session = relationship("Session", back_populates="messages")


class SessionDocument(Base):
    __tablename__ = "session_documents"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=_ist_now)

    session = relationship("Session", back_populates="documents")


class SessionEmail(Base):
    __tablename__ = "session_emails"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    to_address = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=_ist_now)
    sent_at = Column(DateTime, nullable=True)

    session = relationship("Session", back_populates="emails")


class UserFact(Base):
    """Persistent user facts for personalization (name, location, preferences, etc.)."""
    __tablename__ = "user_facts"

    id = Column(String, primary_key=True, default=_uuid)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_ist_now)
    updated_at = Column(DateTime, default=_ist_now, onupdate=_ist_now)
