"""
═══════════════════════════════════════════════════════════════════════════
 VisionNote AI — FastAPI Backend  (main.py)
═══════════════════════════════════════════════════════════════════════════

 All HTTP routes live here. The API mirrors the contract documented in the
 frontend (js/analyze.js "BACKEND INTEGRATION POINTS"):

 ┌───────────────────────────────────────────────────────────────────────┐
 │  POST   /api/upload                multipart file → { upload_id }     │
 │  POST   /api/analyze               start async pipeline → 202         │
 │  GET    /api/status/{session_id}   poll pipeline progress (overlay)   │
 │  GET    /api/summary/{session_id}  final title + markdown summary     │
 │  POST   /api/summarize             synchronous one-shot (contract     │
 │                                    alias: { type, src, lang } → JSON) │
 │  POST   /api/chat                  { question, session_id } →         │
 │                                    { answer, citations[] }  (RAG)     │
 │  GET    /api/transcript/{id}       raw transcript (bottom drawer)     │
 │  GET    /api/extract/{id}/{kind}   action_items|decisions|questions   │
 │  DELETE /api/session/{id}          free transcript, vectors, files    │
 │  GET    /api/health                liveness + config warnings         │
 └───────────────────────────────────────────────────────────────────────┘

 Run locally:
     cd backend
     uvicorn main:app --reload --port 8000

 Interactive docs:  http://localhost:8000/docs
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core import audio
from app.core.extractor import EXTRACTORS
from app.core.rag_engine import answer_question
from app.core.vector_store import delete_vector_store
from app.schemas import (
    AnalyzeAccepted,
    AnalyzeRequest,
    ChatRequest,
    ChatResponse,
    ExtractKind,
    ExtractResponse,
    HealthResponse,
    JobStatus,
    ProgressStep,
    SourceType,
    StatusResponse,
    SummarizeRequest,
    SummaryResponse,
    TranscriptResponse,
    UploadResponse,
)
from app.services.pipeline import submit_analysis
from app.services.sessions import session_store

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("visionnote.api")


# ── Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    for warning in settings.validate():
        logger.warning("CONFIG: %s", warning)
    logger.info("%s v%s ready.", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="LangChain + Mistral + Whisper/Sarvam + Chroma RAG backend "
                "powering the VisionNote AI cinematic video-intelligence frontend.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _get_session_or_404(session_id: str):
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )
    return session


def _require_completed(session):
    if session.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Analysis failed: {session.error}",
        )
    if session.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is still processing. Poll GET /api/status/{session_id}.",
        )


def _resolve_upload(upload_id: str) -> Path:
    """Map an upload_id back to the stored file (uploads/<id>/<original name>)."""
    folder = settings.UPLOAD_DIR / upload_id
    if not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found. POST the file to /api/upload first.",
        )
    files = [p for p in folder.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="Uploaded file is missing.")
    return files[0]


# ═════════════════════════════ ROUTES ═══════════════════════════════════

# ── 1. Upload ───────────────────────────────────────────────────────────
@app.post(
    "/api/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ingest"],
    summary="Upload an audio/video file for analysis",
)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """
    Streams the uploaded media to disk and returns an `upload_id`.
    Pass that id as `src` (with `type='file'`) to POST /api/analyze.
    """
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in settings.ALLOWED_UPLOAD_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{suffix}'. "
                   f"Allowed: {sorted(settings.ALLOWED_UPLOAD_EXT)}",
        )

    upload_id = uuid.uuid4().hex
    folder = settings.UPLOAD_DIR / upload_id
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(file.filename).name

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await file.close()

    logger.info("Upload stored: %s (%d bytes)", dest.name, written)
    return UploadResponse(upload_id=upload_id, filename=dest.name, size_bytes=written)


# ── 2. Analyze (async — recommended) ────────────────────────────────────
@app.post(
    "/api/analyze",
    response_model=AnalyzeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["pipeline"],
    summary="Start the full analysis pipeline (async)",
)
async def start_analysis(body: AnalyzeRequest) -> AnalyzeAccepted:
    """
    Kicks off: audio → transcription → RAG indexing → summary + title.
    Returns immediately with a `session_id`; the frontend overlay polls
    GET /api/status/{session_id} for real progress.
    """
    upload_path: Path | None = None

    if body.type == SourceType.file:
        upload_path = _resolve_upload(body.src)
        source_label = upload_path.name
    else:
        if not audio.is_youtube_url(body.src):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="src must be a valid YouTube URL when type='youtube'.",
            )
        source_label = body.src

    session = session_store.create(
        source_type=body.type.value,
        source=source_label,
        language=body.lang.value,
    )
    submit_analysis(session, upload_path=upload_path)

    return AnalyzeAccepted(
        session_id=session.id,
        status=JobStatus.queued,
        message="Analysis started. Poll /api/status/{session_id} for progress.",
    )


# ── 3. Status polling (drives the processing overlay) ───────────────────
@app.get(
    "/api/status/{session_id}",
    response_model=StatusResponse,
    tags=["pipeline"],
    summary="Poll pipeline progress",
)
async def get_status(session_id: str) -> StatusResponse:
    session = _get_session_or_404(session_id)
    return StatusResponse(
        session_id=session.id,
        status=JobStatus(session.status),
        step=ProgressStep(label=session.step_label, percent=session.step_percent),
        error=session.error,
        result_ready=session.status == "completed",
    )


# ── 4. Summary result ───────────────────────────────────────────────────
@app.get(
    "/api/summary/{session_id}",
    response_model=SummaryResponse,
    tags=["intelligence"],
    summary="Fetch the generated title + structured markdown summary",
)
async def get_summary(session_id: str) -> SummaryResponse:
    session = _get_session_or_404(session_id)
    _require_completed(session)
    return SummaryResponse(
        session_id=session.id,
        title=session.title,
        summary_markdown=session.summary,
        language=session.language,
        transcript_chars=len(session.transcript),
        source=session.public_source(),
    )


# ── 5. Synchronous one-shot (frontend contract alias) ──────────────────
@app.post(
    "/api/summarize",
    response_model=SummaryResponse,
    tags=["intelligence"],
    summary="One-shot analyze + wait + return summary (blocking)",
)
async def summarize_sync(body: SummarizeRequest) -> SummaryResponse:
    """
    Contract-compatible endpoint from js/analyze.js:
        POST /api/summarize { type, src, lang } → summary JSON
    Internally starts the async pipeline and awaits completion, so prefer
    /api/analyze + /api/status for long videos.
    """
    accepted = await start_analysis(body)
    session = _get_session_or_404(accepted.session_id)

    # Await pipeline completion without blocking the event loop.
    while session.status in ("queued", "processing"):
        await asyncio.sleep(1.5)

    _require_completed(session)
    return await get_summary(session.id)


# ── 6. RAG chat ─────────────────────────────────────────────────────────
@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["intelligence"],
    summary="Ask the RAG assistant a question about the analyzed content",
)
async def chat(body: ChatRequest) -> ChatResponse:
    """
    Frontend contract:  POST /api/chat { question, session_id }
                        → { answer, citations[] }
    Retrieval + generation are CPU/network bound → run in a worker thread.
    """
    session = _get_session_or_404(body.session_id)
    _require_completed(session)

    try:
        answer, citations = await asyncio.to_thread(
            answer_question, body.question, session.id, session.language
        )
    except Exception as exc:
        logger.exception("Chat failed for session %s", session.id)
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc

    return ChatResponse(
        session_id=session.id,
        question=body.question,
        answer=answer,
        citations=citations,
    )


# ── 7. Raw transcript (bottom drawer in analyze.html) ──────────────────
@app.get(
    "/api/transcript/{session_id}",
    response_model=TranscriptResponse,
    tags=["intelligence"],
    summary="Fetch the raw transcript",
)
async def get_transcript(session_id: str) -> TranscriptResponse:
    session = _get_session_or_404(session_id)
    if not session.transcript:
        _require_completed(session)
    return TranscriptResponse(
        session_id=session.id,
        transcript=session.transcript,
        chars=len(session.transcript),
    )


# ── 8. Extract hub: action items / decisions / questions ───────────────
@app.get(
    "/api/extract/{session_id}/{kind}",
    response_model=ExtractResponse,
    tags=["intelligence"],
    summary="Extract action items, key decisions, or open questions",
)
async def extract(session_id: str, kind: ExtractKind) -> ExtractResponse:
    """
    Powers the Extract Hub flyout tabs. Results are computed once per kind
    and cached on the session for instant tab switching.
    """
    session = _get_session_or_404(session_id)
    _require_completed(session)

    cached = session.extracts.get(kind.value)
    if cached is None:
        extractor = EXTRACTORS[kind.value]
        try:
            cached = await asyncio.to_thread(extractor, session.transcript)
        except Exception as exc:
            logger.exception("Extractor '%s' failed", kind.value)
            raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc
        with session.lock:
            session.extracts[kind.value] = cached

    return ExtractResponse(session_id=session.id, kind=kind, content=cached)


# ── 9. Session cleanup ──────────────────────────────────────────────────
@app.delete(
    "/api/session/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["pipeline"],
    summary="Delete a session (transcript, vector index, temp files)",
)
async def delete_session(session_id: str):
    _get_session_or_404(session_id)
    delete_vector_store(session_id)
    audio.cleanup_session_files(session_id)
    session_store.delete(session_id)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


# ── 10. Health ──────────────────────────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        warnings=settings.validate(),
    )


# ── Static frontend (serves index.html / analyze.html when present) ────
# Put the VisionNote AI frontend files in backend/static/ (or symlink the repo
# root) and the whole app runs from a single origin — no CORS needed.
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
