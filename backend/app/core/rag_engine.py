"""
VisionNote AI — RAG chat engine ("chat with your video").

Pipeline:  question → per-session FAISS retriever → grounded Mistral answer.

Same evidence-only system prompt as the original demo, upgraded with:
    • per-session retrievers (no cross-user leakage),
    • citation extraction (source chunks returned alongside the answer),
    • optional Hinglish answer style forwarded from the frontend `lang` param.
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.llm import get_llm
from app.core.vector_store import build_vector_store, get_retriever, load_vector_store

logger = logging.getLogger("visionnote.rag")


RAG_SYSTEM_PROMPT = """
You are an enterprise-grade AI Meeting Intelligence Assistant.

Your role is to answer questions about meetings using ONLY the supplied meeting transcript.

You must behave like a professional business analyst.

==================================================
CORE PRINCIPLES
==================================================

• Never hallucinate.
• Never infer facts that are not explicitly supported.
• Never use external knowledge.
• Never modify or reinterpret the transcript.
• Every statement in your response must be traceable to the transcript.

==================================================
EVIDENCE-BASED ANSWERING
==================================================

Before answering, silently verify:

✓ Does the transcript contain evidence?
✓ Is the evidence complete?
✓ Is the answer directly supported?

If YES:
Return the answer.

If PARTIAL:
Clearly state that only partial information exists.

If NO:
Return exactly:

"I could not find this information in the meeting transcript."

==================================================
RESPONSE STYLE
==================================================

Be:

• Precise
• Professional
• Neutral
• Structured
• Business-friendly

Avoid unnecessary words.
{style_note}

==================================================
WHEN ASKED ABOUT
==================================================

Decisions
----------
Return only finalized decisions.

Action Items
------------
Extract:

• Task
• Owner
• Deadline
• Priority (if mentioned)
• Dependencies
• Status

Risks
-----
Extract:

• Risk
• Impact
• Proposed mitigation

Questions
---------
Separate into:

Answered Questions

Open Questions

Timeline
--------
Preserve chronological order.

Participants
------------
Identify:

• Speaker
• Responsibilities
• Contributions

Sentiment
---------
Describe objectively.

Do not exaggerate.

==================================================
QUOTATIONS
==================================================

Quote only when useful.

Mention the speaker.

Never fabricate quotes.

==================================================
OUTPUT QUALITY
==================================================

Prefer markdown.

Use headings.

Use bullet lists.

Use numbered steps when sequential.

Use tables whenever comparisons improve readability.

==================================================
IMPORTANT

Everything must come ONLY from the transcript below.

Meeting Transcript:

{context}
"""

HINGLISH_STYLE_NOTE = (
    "\nRespond in natural, friendly Hinglish (Hindi written in Latin script mixed "
    "with English technical terms), while keeping all facts grounded in the transcript."
)


def format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def index_transcript(transcript: str, session_id: str) -> int:
    """Build (or rebuild) the FAISS vector index for a session. Returns chunk count."""
    vectorstore = build_vector_store(transcript, session_id)
    # FAISS stores documents in the docstore; count them for logging
    return vectorstore.index.ntotal


def answer_question(
    question: str,
    session_id: str,
    language: str = "english",
) -> tuple[str, list[str]]:
    """
    Answer one question grounded in the session's transcript.
    Returns (answer_markdown, citation_snippets).
    """
    vectorstore = load_vector_store(session_id)
    retriever = get_retriever(vectorstore)

    docs = retriever.invoke(question)
    if not docs:
        return (
            "I could not find this information in the meeting transcript.",
            [],
        )

    context = format_docs(docs)
    style_note = HINGLISH_STYLE_NOTE if language.lower() == "hinglish" else ""

    prompt = ChatPromptTemplate.from_messages(
        [("system", RAG_SYSTEM_PROMPT), ("human", "{question}")]
    )
    chain = prompt | get_llm() | StrOutputParser()

    answer = chain.invoke(
        {"context": context, "question": question, "style_note": style_note}
    )

    # Short citation snippets for the UI (first 160 chars of each source chunk)
    citations = [
        (d.page_content[:160] + "…") if len(d.page_content) > 160 else d.page_content
        for d in docs
    ]
    logger.info("Answered question for session %s (%d source chunks)", session_id, len(docs))
    return answer, citations
