"""
VisionNote AI — Pydantic request/response models.

These mirror the frontend contract documented in js/analyze.js:
    POST /api/summarize   { type, src, lang }        → summary JSON
    POST /api/chat        { question, session_id }   → { answer, citations[] }
plus the async job endpoints used by the processing overlay.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────── Enums ───────────────────────────

class SourceType(str, Enum):
    youtube = "youtube"
    file = "file"


class Language(str, Enum):
    english = "english"
    hinglish = "hinglish"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ExtractKind(str, Enum):
    action_items = "action_items"
    decisions = "decisions"
    questions = "questions"


# ─────────────────────────── Requests ───────────────────────────

class AnalyzeRequest(BaseModel):
    """Kick off the full pipeline for a YouTube URL or a previously uploaded file."""
    type: SourceType = Field(..., description="Source kind: 'youtube' or 'file'")
    src: str = Field(..., min_length=3, description="YouTube URL or upload_id returned by /api/upload")
    lang: Language = Field(Language.english, description="Spoken language routing (english→Whisper, hinglish→Sarvam)")

    @field_validator("src")
    @classmethod
    def strip_src(cls, v: str) -> str:
        return v.strip()


class SummarizeRequest(AnalyzeRequest):
    """Synchronous alias kept for frontend contract compatibility (POST /api/summarize)."""


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=8)

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        return v


# ─────────────────────────── Responses ───────────────────────────

class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int


class AnalyzeAccepted(BaseModel):
    session_id: str
    status: JobStatus
    message: str


class ProgressStep(BaseModel):
    """One entry of the processing overlay shown by the frontend."""
    label: str
    percent: int


class StatusResponse(BaseModel):
    session_id: str
    status: JobStatus
    step: Optional[ProgressStep] = None
    error: Optional[str] = None
    result_ready: bool = False


class SummaryResponse(BaseModel):
    session_id: str
    title: str
    summary_markdown: str
    language: Language
    transcript_chars: int
    source: dict[str, Any]


class ExtractResponse(BaseModel):
    session_id: str
    kind: ExtractKind
    content: str


class ChatResponse(BaseModel):
    session_id: str
    question: str
    answer: str
    citations: list[str] = []


class TranscriptResponse(BaseModel):
    session_id: str
    transcript: str
    chars: int


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    warnings: list[str] = []


class ErrorResponse(BaseModel):
    detail: str
