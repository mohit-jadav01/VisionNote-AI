"""
VisionNote AI — Analysis pipeline orchestrator.

Runs the full flow in a background thread:

    source (YouTube URL / uploaded file)
        └─▶ 1. audio acquisition + WAV chunking        (audio.py)
        └─▶ 2. speech-to-text (Whisper / Sarvam)       (transcribe.py)
        └─▶ 3. chunk + embed + index into Chroma       (vector_store.py)
        └─▶ 4. map-reduce summary + title              (summarizer.py)
        └─▶ 5. session marked complete → frontend polls /api/status

The step labels + percentages intentionally match the processing overlay
steps in js/analyze.js so the UI reflects real backend progress.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core import audio, transcribe
from app.core.rag_engine import index_transcript
from app.core.summarizer import generate_title, summarize
from app.services.sessions import Session

logger = logging.getLogger("visionnote.pipeline")

# Dedicated worker pool: heavy jobs never block the API event loop.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vidsage-pipeline")


def submit_analysis(session: Session, *, upload_path: Path | None = None) -> None:
    """Queue the pipeline for execution and return immediately (HTTP 202)."""
    _executor.submit(_run_pipeline, session, upload_path)


def _run_pipeline(session: Session, upload_path: Path | None) -> None:
    sid = session.id
    try:
        # ── 1. Acquire audio ───────────────────────────────────────────
        session.set_step("Extracting audio stream…", 15)
        if upload_path is not None:
            chunks = audio.prepare_source(str(upload_path), sid, is_upload=True)
        else:
            chunks = audio.prepare_source(session.source, sid)

        # ── 2. Transcribe ──────────────────────────────────────────────
        engine = "Sarvam AI" if session.language == "hinglish" else "Whisper"
        session.set_step(f"Transcribing speech with {engine}…", 25)

        def stt_progress(done: int, total: int) -> None:
            # Transcription spans 25% → 55% of the overall pipeline
            session.set_step(
                f"Transcribing speech with {engine}… ({done}/{total})",
                25 + int(30 * done / max(total, 1)),
            )

        transcript = transcribe.transcribe_all(
            chunks, language=session.language, on_progress=stt_progress
        )
        with session.lock:
            session.transcript = transcript

        # ── 3. Vector index (RAG) ──────────────────────────────────────
        session.set_step("Chunking & embedding transcript…", 60)
        n_chunks = index_transcript(transcript, sid)
        session.set_step("Indexing into vector store (RAG)…", 78)
        logger.info("Session %s: indexed %d chunks", sid, n_chunks)

        # ── 4. Summary + title ─────────────────────────────────────────
        session.set_step("LangChain agents drafting your summary…", 84)

        def sum_progress(done: int, total: int) -> None:
            session.set_step(
                f"LangChain agents drafting your summary… ({done}/{total})",
                84 + int(10 * done / max(total, 1)),
            )

        summary = summarize(transcript, on_progress=sum_progress)
        title = generate_title(transcript)
        with session.lock:
            session.summary = summary
            session.title = title

        # ── 5. Done ────────────────────────────────────────────────────
        session.complete()
        logger.info("Session %s pipeline completed.", sid)

    except Exception as exc:  # surface any stage failure to the frontend
        logger.exception("Pipeline failed for session %s", sid)
        session.fail(str(exc))
    finally:
        audio.cleanup_session_files(sid)
