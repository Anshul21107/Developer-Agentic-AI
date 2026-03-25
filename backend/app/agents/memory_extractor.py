"""Extract and store personal facts from conversations for personalization."""

import json
import logging

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..llm import get_llm
from ..models import UserFact

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = (
    "Extract personal facts about the user from this conversation.\n\n"
    "RULES:\n"
    "- Only extract CONCRETE facts the user explicitly stated about themselves\n"
    "- Do NOT extract questions, requests, or topics they asked about\n"
    "- Keys must be: name, location, email, job_title, company, or preference_*\n"
    "- Values must be the actual fact (a name, place, etc.), never 'yes'/'no'\n\n"
    "EXAMPLES:\n"
    'User: "My name is Anshul and I live in New Delhi"\n'
    'Output: [{{"key": "name", "value": "Anshul"}}, {{"key": "location", "value": "New Delhi"}}]\n\n'
    'User: "What is the weather in Mumbai?"\n'
    "Output: []\n\n"
    'User: "I work as a software engineer at Google"\n'
    'Output: [{{"key": "job_title", "value": "Software Engineer"}}, {{"key": "company", "value": "Google"}}]\n\n'
    'User: "Send email to john@test.com"\n'
    "Output: []\n\n"
    "NOW EXTRACT FROM:\n"
    "User: {user_msg}\n"
    "Assistant: {assistant_msg}\n\n"
    "Return ONLY a JSON array (or [] if no personal facts):"
)


async def extract_and_store_facts(user_msg: str, assistant_msg: str) -> None:
    """Extract personal facts from a message exchange and upsert into DB."""
    try:
        llm = get_llm(streaming=False)
        prompt = EXTRACT_PROMPT.format(user_msg=user_msg, assistant_msg=assistant_msg)
        response = await llm.ainvoke(prompt)
        content = response.content.strip()

        # Parse JSON from the response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        facts = json.loads(content)
        if not isinstance(facts, list) or not facts:
            return

        # Allowed keys to prevent garbage
        allowed_prefixes = {"name", "location", "email", "job", "company", "preference"}

        db: Session = SessionLocal()
        try:
            for fact in facts:
                key = fact.get("key", "").strip().lower().replace(" ", "_")
                value = fact.get("value", "").strip()

                # Skip invalid facts
                if not key or not value or len(value) < 2:
                    continue
                if value.lower() in {"yes", "no", "true", "false", "none", "null"}:
                    continue
                if not any(key.startswith(p) for p in allowed_prefixes):
                    continue

                # Upsert
                existing = db.query(UserFact).filter(UserFact.key == key).first()
                if existing:
                    existing.value = value
                else:
                    db.add(UserFact(key=key, value=value))
            db.commit()
        finally:
            db.close()

    except Exception as exc:
        logger.debug(f"Fact extraction skipped: {exc}")


def get_all_facts() -> list[dict]:
    """Load all stored user facts from DB."""
    db: Session = SessionLocal()
    try:
        facts = db.query(UserFact).order_by(UserFact.key).all()
        return [{"key": f.key, "value": f.value} for f in facts]
    finally:
        db.close()
