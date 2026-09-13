"""
VidSage AI — Shared LLM factory.

Single source of truth for the ChatMistralAI instance so the model name,
key and temperature are configured in exactly one place (same model as the
original demo: `mistral-medium-3-5`, temperature=1).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from app.config import settings


@lru_cache
def get_llm() -> ChatMistralAI:
    """Return a cached ChatMistralAI client (safe to reuse across requests)."""
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY is not configured. Add it to backend/.env"
        )
    return ChatMistralAI(
        model=settings.MISTRAL_MODEL,
        api_key=settings.MISTRAL_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
    )


def build_text_chain(system_prompt: str) -> Runnable:
    """
    Build the standard  str → {'text': str} → prompt → llm → str  chain
    used by the summariser and all extractors.
    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "{text}")]
    )
    return (
        RunnablePassthrough()
        | RunnableLambda(lambda x: {"text": x})
        | prompt
        | get_llm()
        | StrOutputParser()
    )
