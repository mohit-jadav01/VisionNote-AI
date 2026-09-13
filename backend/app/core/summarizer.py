"""
VidSage AI — Map-reduce transcript summariser + title generator.

Same model (mistral-medium-3-5), same prompts and same map→combine strategy
as the original demo, refactored into clean, reusable, typed functions with
optional progress callbacks for the frontend overlay.
"""

from __future__ import annotations

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.core.llm import build_text_chain

logger = logging.getLogger("vidsage.summarizer")


MAP_PROMPT = """You are a professional AI meeting transcript summarization engine.

The input is a single chunk from a larger meeting transcript. The chunk may start or end in the middle of a discussion.

Your task is to generate a high-quality summary of ONLY the provided transcript chunk.

Requirements:
- Capture the core discussion and essential information.
- Preserve decisions, conclusions, action items, commitments, deadlines, risks, blockers, unresolved questions, and important technical details.
- Preserve names, organizations, project names, numbers, dates, metrics, and technical terminology exactly as mentioned.
- Remove filler words, greetings, repetitions, hesitations, interruptions, off-topic conversation, and speech disfluencies.
- Do not invent, infer, or speculate beyond the transcript.
- Do not rely on context from previous or future transcript chunks.
- If the chunk is incomplete, summarize only the available content naturally without mentioning the missing context.
- Write in clear, concise, professional, and neutral English.
- Keep the summary as short as possible while preserving all important information.
- Return only the summary text without headings, labels, markdown, or additional commentary."""


COMBINE_PROMPT = """
You are a senior AI Meeting Summarization Assistant.

Your task is to combine multiple partial meeting summaries into one final, well-structured, professional meeting summary.

Instructions:

- Merge all summaries into a single coherent document.
- Remove duplicate or repetitive information.
- Preserve every important fact, decision, discussion, and conclusion.
- Maintain the logical order of the meeting whenever possible.
- Do not invent or assume information that is not provided.
- Ignore filler words, greetings, and irrelevant conversation.
- Combine similar ideas into concise bullet points.
- Keep the writing clear, formal, and business-friendly.
- Ensure the summary is easy to read.

Structure the output exactly as follows:

# Meeting Summary

## Key Discussion Points
- Bullet points covering all major topics discussed.

## Decisions Made
- List every confirmed decision.
- If none exist, write "No explicit decisions were made."

## Action Items
For every action item include:
- Task
- Responsible Person (if mentioned)
- Deadline (if mentioned)

Example:
- Prepare final project proposal — Assigned to Rahul — Due Friday

## Risks / Concerns
- Mention blockers, risks, unresolved issues, or concerns.
- If none exist, write "None mentioned."

## Next Steps
- Summarize the agreed future plan.

Guidelines:
- Use professional language.
- Keep sentences concise.
- Avoid repetition.
- Preserve important technical details.
- Do not summarize already summarized information twice.
- Output only the final meeting summary.
"""


TITLE_PROMPT = """
You are an AI Meeting Intelligence Assistant responsible for generating concise, professional, and meaningful meeting titles.

Your objective is to create a title that accurately captures the primary purpose or outcome of the meeting.

Instructions:

- Read the complete meeting transcript carefully.
- Identify the central topic or objective of the meeting.
- Generate ONE clear and professional meeting title.
- Prioritize the main discussion over minor topics.
- Keep the title between 3 and 8 words.
- Use Title Case (capitalize major words).
- Avoid generic titles such as "Meeting Discussion", "Weekly Meeting", or "Conversation".
- Do not include unnecessary punctuation, emojis, quotation marks, dates, participant names, or filler words unless they are essential.
- If the meeting focuses on a project, include the project name when available.
- If the meeting is about planning, design, review, debugging, hiring, finance, research, or strategy, reflect that in the title.
- Make the title suitable for dashboards, calendars, meeting histories, and reports.
- Return ONLY the meeting title.
"""


def split_transcript(transcript: str) -> list[str]:
    """Split a long transcript into LLM-sized chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.SUMMARY_CHUNK_SIZE,
        chunk_overlap=settings.SUMMARY_CHUNK_OVERLAP,
        separators=["\n\n", "\n", "."],
    )
    return splitter.split_text(transcript)


def summarize(transcript: str, on_progress=None) -> str:
    """
    Map-reduce summarisation:
        1. MAP     — summarise each chunk independently.
        2. COMBINE — merge partial summaries into the final structured report.
    """
    map_chain = build_text_chain(MAP_PROMPT)
    chunks = split_transcript(transcript)
    logger.info("Summarising %d chunk(s)", len(chunks))

    partial_summaries: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        partial_summaries.append(map_chain.invoke(chunk))
        if on_progress:
            on_progress(i, len(chunks))

    combined = "\n\n".join(partial_summaries)
    combine_chain = build_text_chain(COMBINE_PROMPT)
    final_summary = combine_chain.invoke(combined)
    logger.info("Summary complete (%d chars).", len(final_summary))
    return final_summary


def generate_title(transcript: str) -> str:
    """Generate a 3-8 word Title-Case meeting/video title from the opening context."""
    title_chain = build_text_chain(TITLE_PROMPT)
    title = title_chain.invoke(transcript[:2000]).strip().strip('"').strip()
    return title or "Untitled Analysis"
