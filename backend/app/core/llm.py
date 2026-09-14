"""
VidSage AI — Shared LLM factory.

Single source of truth for the ChatMistralAI instance so the model name,
key and temperature are configured in exactly one place (same model as the
original demo: `mistral-medium-3-5`, temperature=1).

Import notes
  -----------
  ALL langchain imports are intentionally deferred to the functions that need
  them.  langchain_core.prompts transitively imports
  langchain_core.language_models.base which does an unconditional
  `from transformers import GPT2TokenizerFast`, pulling in the full
  transformers + torch stack at module import time.  By keeping this file's
  module-level imports to stdlib-only we allow Uvicorn to bind its port
  instantly and Render to detect the service before any ML work starts.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

# Only stdlib and our own config are safe at module level.
from app.config import settings

# TYPE_CHECKING block: these names are never actually imported at runtime —
# they exist only to satisfy mypy / pyright.
if TYPE_CHECKING:
    from langchain_mistralai import ChatMistralAI
    from langchain_core.runnables import Runnable


@lru_cache
def get_llm() -> "ChatMistralAI":
    """Return a cached ChatMistralAI client (safe to reuse across requests).

    All heavy imports (langchain_mistralai, transformers indirectly) are
    deferred to the first call so that uvicorn startup is instant.
    """
    # Lazy imports: only executed when an LLM feature is first invoked.
    from langchain_mistralai import ChatMistralAI  # noqa: PLC0415

    if not settings.MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY is not configured. Add it to backend/.env"
        )
    return ChatMistralAI(
        model=settings.MISTRAL_MODEL,
        api_key=settings.MISTRAL_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
    )


def build_text_chain(system_prompt: str) -> "Runnable":
    """
    Build the standard  str -> {'text': str} -> prompt -> llm -> str  chain
    used by the summariser and all extractors.
    """
    # Lazy imports: pulling these in here (not at module level) prevents the
    # langchain_core → transformers → torch import chain from running at startup.
    from langchain_core.prompts import ChatPromptTemplate  # noqa: PLC0415
    from langchain_core.output_parsers import StrOutputParser  # noqa: PLC0415
    from langchain_core.runnables import RunnableLambda, RunnablePassthrough  # noqa: PLC0415

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
