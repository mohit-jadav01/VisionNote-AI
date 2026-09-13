"""
VisionNote AI — In-memory session store.

Each analysis run gets a Session that tracks:
    • pipeline status + current progress step (drives the frontend overlay),
    • the full transcript,
    • the generated title & summary,
    • cached extractor results (action items / decisions / questions).

Thread-safe: the pipeline runs in a worker thread while API requests read
state concurrently. Sessions expire after SESSION_TTL_MINUTES.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings


@dataclass
class Session:
    id: str
    source_type: str                     # 'youtube' | 'file'
    source: str                          # URL or original filename
    language: str = "english"

    status: str = "queued"               # queued | processing | completed | failed
    step_label: str = "Queued…"
    step_percent: int = 0
    error: Optional[str] = None

    transcript: str = ""
    title: str = ""
    summary: str = ""
    extracts: dict[str, str] = field(default_factory=dict)

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ── mutation helpers ────────────────────────────────────────────────
    def set_step(self, label: str, percent: int) -> None:
        with self.lock:
            self.status = "processing"
            self.step_label = label
            self.step_percent = max(0, min(100, percent))
            self.updated_at = time.time()

    def complete(self) -> None:
        with self.lock:
            self.status = "completed"
            self.step_label = "Rolling credits…"
            self.step_percent = 100
            self.updated_at = time.time()

    def fail(self, message: str) -> None:
        with self.lock:
            self.status = "failed"
            self.error = message
            self.updated_at = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.updated_at) > settings.SESSION_TTL_MINUTES * 60

    def public_source(self) -> dict[str, Any]:
        return {"type": self.source_type, "src": self.source, "lang": self.language}


class SessionStore:
    """Thread-safe registry of active sessions with lazy TTL cleanup."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, source_type: str, source: str, language: str) -> Session:
        session = Session(
            id=uuid.uuid4().hex,
            source_type=source_type,
            source=source,
            language=language,
        )
        with self._lock:
            self._evict_expired()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session and session.is_expired:
            self.delete(session_id)
            return None
        return session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            self._sessions.pop(sid, None)


# Module-level singleton used by the API layer
session_store = SessionStore()
