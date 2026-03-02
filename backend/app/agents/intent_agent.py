from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState, Intent
from ..llm import get_llm

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a multi-agent chatbot.
Choose one intent from: general, rag, weather, email, news, web_search.
- general: open-ended chat, brainstorming, explanations.
- rag: questions about stored project/company/product knowledge.
- weather: requests for weather or forecast for a location.
- email: requests to draft or send an email.
- news: requests for latest/breaking news or headlines.
- web_search: requests to search the web, verify facts, or research.
Return ONLY the intent label."""


async def intent_node(state: AgentState) -> dict:
    user_input = state.get("user_input", "")
    llm = get_llm(streaming=False)
    availability = "yes" if state.get("has_documents", False) else "no"
    pending = "yes" if state.get("has_pending_email", False) else "no"
    result = await llm.ainvoke(
        [
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"User message: {user_input}\nDocuments available: {availability}\nPending email: {pending}"
                )
            ),
        ]
    )
    intent = (result.content or "").strip().lower()
    if intent in {"general", "rag", "weather", "email", "news", "web_search"}:
        if intent == "web_search" and _heuristic_general_override(user_input) and not _heuristic_web_search_intent(user_input):
            return {"intent": "general"}
        return {"intent": intent}
    if _heuristic_news_intent(user_input):
        return {"intent": "news"}
    if _heuristic_email_intent(user_input, state.get("has_pending_email", False)):
        return {"intent": "email"}
    if _heuristic_rag_intent(user_input, state.get("has_documents", False)):
        return {"intent": "rag"}
    if _heuristic_web_search_intent(user_input):
        return {"intent": "web_search"}
    if _heuristic_general_override(user_input):
        return {"intent": "general"}
    return {"intent": "general"}


def _heuristic_rag_intent(user_input: str, has_documents: bool) -> bool:
    if not has_documents:
        return False
    keywords = [
        "document",
        "doc",
        "file",
        "pdf",
        "uploaded",
        "upload",
        "notes",
        "in the doc",
        "from the doc",
        "from the document",
    ]
    lowered = user_input.lower()
    return any(keyword in lowered for keyword in keywords)


def _heuristic_email_intent(user_input: str, has_pending_email: bool) -> bool:
    lowered = user_input.lower()
    if has_pending_email and any(
        phrase in lowered for phrase in ["send it", "send email", "yes send", "confirm", "approve", "go ahead"]
    ):
        return True
    if has_pending_email:
        return True
    keywords = ["email", "mail", "draft", "compose", "send to", "write to"]
    return any(keyword in lowered for keyword in keywords)


def _heuristic_news_intent(user_input: str) -> bool:
    lowered = user_input.lower()
    keywords = ["news", "headline", "headlines", "breaking"]
    if any(keyword in lowered for keyword in keywords):
        return True
    return "latest news" in lowered or "news about" in lowered


def _heuristic_web_search_intent(user_input: str) -> bool:
    lowered = user_input.lower()
    keywords = [
        "search",
        "web",
        "google",
        "duckduckgo",
        "find",
        "look up",
        "research",
        "fact check",
        "factcheck",
        "verify",
        "source",
        "sources",
    ]
    if any(keyword in lowered for keyword in keywords):
        return True
    # if "latest" in lowered or "released" in lowered or "release date" in lowered:
    #     return True
    return False


def _heuristic_general_override(user_input: str) -> bool:
    lowered = user_input.lower().strip()
    if "news" in lowered:
        return False
    if lowered.startswith("what is") or lowered.startswith("who is") or lowered.startswith("explain"):
        return True
    return False
