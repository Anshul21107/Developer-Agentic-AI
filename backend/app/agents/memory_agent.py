from langchain_core.messages import HumanMessage, SystemMessage

from ..llm import get_llm

MEMORY_SYSTEM_PROMPT = """You are a memory summarizer for a chatbot.
Update the running summary with the latest user and assistant turn.
Keep it concise, factual, and under 120 words."""


async def update_memory_summary(
    previous_summary: str | None, user_message: str, assistant_message: str
) -> str:
    llm = get_llm(streaming=False)
    summary = previous_summary or "No prior summary."
    update_prompt = (
        f"Existing summary:\n{summary}\n\n"
        f"New user message:\n{user_message}\n\n"
        f"Assistant response:\n{assistant_message}\n\n"
        "Return the updated summary only."
    )
    result = await llm.ainvoke(
        [
            SystemMessage(content=MEMORY_SYSTEM_PROMPT),
            HumanMessage(content=update_prompt),
        ]
    )
    return (result.content or "").strip()