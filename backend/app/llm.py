import os
from langchain_groq import ChatGroq

def get_llm(streaming: bool, callbacks=None):
    api_key = os.getenv("GROQ_API_KEY")
    model_name = os.getenv("GROQ_MODEL")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return ChatGroq(
        api_key=api_key,
        model=model_name,
        streaming=streaming,
        callbacks=callbacks or [],
        temperature=0.7,
    )
