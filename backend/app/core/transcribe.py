"""
VidSage AI — Speech-to-text engines.

Routing (identical behaviour to the original demo):
    english  → local OpenAI Whisper model
    hinglish → Sarvam AI speech-to-text-translate (Hinglish → English)

Improvements:
    • Thread-safe lazy Whisper loading.
    • Retry with exponential backoff for Sarvam HTTP calls.
    • Guaranteed temp-piece cleanup.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import requests
from pydub import AudioSegment

from app.config import settings

logger = logging.getLogger("vidsage.transcribe")

_model = None
_model_lock = threading.Lock()


class TranscriptionError(RuntimeError):
    """Raised when transcription fails."""


# ─────────────────────────── Whisper (English) ───────────────────────────

def load_whisper():
    """Lazily load the Whisper model once, in a thread-safe manner."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-checked locking
                import whisper  # heavy import deferred until needed

                logger.info("Loading Whisper model: %s ...", settings.WHISPER_MODEL)
                _model = whisper.load_model(settings.WHISPER_MODEL)
                logger.info("Whisper model loaded.")
    return _model


def transcribe_chunk_whisper(chunk_path: Path) -> str:
    model = load_whisper()
    try:
        result = model.transcribe(str(chunk_path))
    except Exception as exc:
        raise TranscriptionError(f"Whisper failed on {chunk_path.name}: {exc}") from exc
    return (result.get("text") or "").strip()


# ─────────────────────────── Sarvam (Hinglish) ───────────────────────────

def _send_to_sarvam(piece_path: Path, retries: int = 3) -> str:
    """POST one ≤30s WAV piece to Sarvam with retry/backoff."""
    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            with open(piece_path, "rb") as f:
                response = requests.post(
                    settings.SARVAM_STT_TRANSLATE_URL,
                    headers=headers,
                    files={"file": (piece_path.name, f, "audio/wav")},
                    data={"model": settings.SARVAM_STT_MODEL, "with_diarization": "false"},
                    timeout=120,
                )
            if response.ok:
                return response.json().get("transcript", "")
            # Retry only on transient statuses
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = 2 ** attempt
                logger.warning("Sarvam %s — retrying in %ss", response.status_code, wait)
                time.sleep(wait)
                continue
            raise TranscriptionError(
                f"Sarvam returned {response.status_code}: {response.text[:300]}"
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 ** attempt)

    raise TranscriptionError(f"Sarvam request failed after {retries} attempts: {last_error}")


def transcribe_chunk_sarvam(chunk_path: Path) -> str:
    """
    Sarvam's sync API only accepts ≤30s audio, so each chunk is split into
    25-second pieces which are transcribed and re-joined.
    """
    if not settings.SARVAM_API_KEY:
        raise TranscriptionError("SARVAM_API_KEY is not set — cannot use Hinglish mode.")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = settings.SARVAM_PIECE_SECONDS * 1000
    total = (len(audio) + piece_ms - 1) // piece_ms
    parts: list[str] = []

    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece_path = chunk_path.with_name(f"{chunk_path.stem}_sv_{i}.wav")
        audio[start: start + piece_ms].export(piece_path, format="wav")
        try:
            logger.info("Sarvam piece %d/%d ...", i + 1, total)
            parts.append(_send_to_sarvam(piece_path))
        finally:
            if piece_path.exists():
                os.remove(piece_path)

    return " ".join(p for p in parts if p).strip()


# ─────────────────────────── Public API ───────────────────────────

def transcribe_chunk(chunk_path: Path, language: str = "english") -> str:
    """Route one chunk to the correct STT engine."""
    if language.lower() == "hinglish":
        return transcribe_chunk_sarvam(chunk_path)
    return transcribe_chunk_whisper(chunk_path)


def transcribe_all(
    chunks: list[Path],
    language: str = "english",
    on_progress=None,
) -> str:
    """
    Transcribe every chunk in order and return the full transcript.
    `on_progress(current, total)` is invoked after each chunk so the API layer
    can surface pipeline progress to the frontend overlay.
    """
    engine = "Sarvam AI" if language.lower() == "hinglish" else "Whisper"
    logger.info("Transcribing %d chunk(s) with %s", len(chunks), engine)

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info("Chunk %d/%d ...", i, len(chunks))
        parts.append(transcribe_chunk(chunk, language=language))
        if on_progress:
            on_progress(i, len(chunks))

    transcript = " ".join(p for p in parts if p).strip()
    if not transcript:
        raise TranscriptionError("Transcription produced empty text.")
    logger.info("Transcription complete (%d chars).", len(transcript))
    return transcript
