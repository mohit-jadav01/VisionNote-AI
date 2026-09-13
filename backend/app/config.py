"""
VisionNote AI — Central configuration.

Every tunable value (models, chunk sizes, directories, API keys) lives here
so the rest of the codebase never touches os.getenv directly.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# Resolve .env at the backend project root (backend/.env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Immutable runtime settings, read once from the environment."""

    # ── App ────────────────────────────────────────────────────────────
    APP_NAME: str = "VisionNote AI Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Comma-separated list of allowed CORS origins ("*" for dev)
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]

    # ── LLM (Mistral — SAME model as the original demo) ───────────────
    MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-medium-3-5")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "1"))

    # ── Transcription ──────────────────────────────────────────────────
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "tiny")

    SARVAM_API_KEY: str | None = os.getenv("SARVAM_API_KEY")
    SARVAM_STT_MODEL: str | None = os.getenv("SARAVAM_STT_MODEL")  # matches original .env key
    SARVAM_STT_TRANSLATE_URL: str = "https://api.sarvam.ai/speech-to-text-translate"
    SARVAM_PIECE_SECONDS: int = 25       # API hard limit is 30s; keep head-room

    # ── Audio processing ───────────────────────────────────────────────
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    AUDIO_CHUNK_MINUTES: int = int(os.getenv("AUDIO_CHUNK_MINUTES", "10"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "500"))
    ALLOWED_UPLOAD_EXT: set[str] = {
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
        ".mp4", ".mkv", ".mov", ".avi", ".webm",
    }

    # ffmpeg: prefer PATH, fall back to an explicit location from .env
    FFMPEG_LOCATION: str | None = shutil.which("ffmpeg") or os.getenv("FFMPEG_LOCATION")

    # ── Vector store (RAG) — same stack as the demo ────────────────────
    CHROMA_DIR: Path = BASE_DIR / "vector_db"
    COLLECTION_PREFIX: str = "meeting_transcript"
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))

    # ── Summarisation ──────────────────────────────────────────────────
    SUMMARY_CHUNK_SIZE: int = 3000
    SUMMARY_CHUNK_OVERLAP: int = 200

    # ── Sessions ───────────────────────────────────────────────────────
    SESSION_TTL_MINUTES: int = int(os.getenv("SESSION_TTL_MINUTES", "240"))

    def ensure_dirs(self) -> None:
        """Create working directories on startup."""
        for d in (self.DOWNLOAD_DIR, self.UPLOAD_DIR, self.CHROMA_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """Return a list of human-readable configuration warnings."""
        warnings: list[str] = []
        if not self.MISTRAL_API_KEY:
            warnings.append("MISTRAL_API_KEY is not set — LLM features will fail.")
        if not self.FFMPEG_LOCATION:
            warnings.append("ffmpeg not found on PATH — audio conversion may fail.")
        if not self.SARVAM_API_KEY:
            warnings.append("SARVAM_API_KEY not set — Hinglish transcription unavailable.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
