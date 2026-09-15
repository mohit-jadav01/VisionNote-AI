"""
VidSage AI — Audio acquisition & preparation.

Responsibilities:
    • Download best-quality audio from a YouTube URL (yt-dlp).
    • Convert any uploaded audio/video container to mono 16 kHz WAV (pydub+ffmpeg).
    • Split long WAV files into fixed-length chunks for the STT engines.

Improvements over the original demo:
    • No hard-coded Windows ffmpeg path — resolved via config.
    • Unique per-session working directories (no filename collisions).
    • Robust error types and full cleanup helper.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from pathlib import Path

import yt_dlp
from pydub import AudioSegment

from app.config import settings

logger = logging.getLogger("vidsage.audio")

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE
)


class AudioProcessingError(RuntimeError):
    """Raised when download / conversion / chunking fails."""


def is_youtube_url(source: str) -> bool:
    return bool(YOUTUBE_RE.match(source.strip()))


def _workdir(session_id: str) -> Path:
    d = settings.DOWNLOAD_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_youtube_audio(url: str, session_id: str) -> Path:
    """Download best audio stream and convert it to WAV. Returns WAV path."""
    workdir = _workdir(session_id)
    outtmpl = str(workdir / "%(id)s.%(ext)s")
    captured: dict[str, str] = {}

    def hook(d: dict) -> None:
        if d.get("status") == "finished":
            captured["raw_file"] = d.get("filename", "")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "progress_hooks": [hook],
        # IMPORTANT: "android" does NOT support cookies — if a cookies file
        # is attached, yt-dlp silently drops "android" from this list and
        # falls back to the default web client, which is the one currently
        # most likely to get bot-checked and returned only image/storyboard
        # formats ("Only images are available for download"). Use clients
        # that DO support cookies, with fallbacks, instead of pinning to
        # android alone.
        "extractor_args": {
            "youtube": {"player_client": ["tv", "web_safari", "web"]}
        },
    }
    if settings.FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = settings.FFMPEG_LOCATION

    # yt-dlp doesn't just *read* cookiefile — on YoutubeDL.close() it writes
    # the (possibly refreshed) cookie jar back to that same path. Render
    # Secret Files (e.g. /etc/secrets/cookies.txt) are mounted READ-ONLY at
    # runtime, so pointing cookiefile straight at settings.YT_COOKIES_FILE
    # crashes with "OSError: [Errno 30] Read-only file system" during
    # cleanup — which then masks whatever the real download error was.
    # Fix: stage a writable copy per-session and point yt-dlp at that.
    if settings.YT_COOKIES_FILE and os.path.exists(settings.YT_COOKIES_FILE):
        writable_cookies = workdir / "cookies.txt"
        try:
            shutil.copy(settings.YT_COOKIES_FILE, writable_cookies)
            ydl_opts["cookiefile"] = str(writable_cookies)
            logger.info("Using YouTube cookies file for authenticated download")
        except OSError as exc:
            logger.warning("Could not stage a writable cookies copy: %s", exc)

    logger.info("Downloading YouTube audio: %s", url)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:  # yt-dlp raises many exception types
        raise AudioProcessingError(_friendly_download_error(exc)) from exc

    raw_file = captured.get("raw_file", "")
    if not raw_file or not os.path.exists(raw_file):
        raise AudioProcessingError(f"yt-dlp did not produce a file for: {url}")

    return convert_to_wav(Path(raw_file), delete_source=True)


def _friendly_download_error(exc: Exception) -> str:
    """Translate common yt-dlp/YouTube failures into actionable messages
    instead of leaking raw tracebacks (e.g. a cleanup-time OSError) to the
    frontend, which hides the real cause from whoever is debugging it."""
    msg = str(exc)
    lowered = msg.lower()
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return (
            "YouTube blocked this download with a bot-check. The stored "
            "YouTube cookies are expired — export a fresh cookies.txt from "
            "a logged-in browser and re-upload it as the YT_COOKIES_FILE "
            "Secret File on Render, then redeploy."
        )
    if "read-only file system" in lowered:
        return (
            "Internal error: tried to write to a read-only cookies path. "
            "(This is fixed by staging a writable copy — redeploy the "
            "latest backend build.)"
        )
    if "http error 403" in lowered:
        return (
            "YouTube refused the request (403 Forbidden). This usually "
            "means the cookies are stale/rotated or the server IP is "
            "temporarily rate-limited by YouTube."
        )
    return f"YouTube download failed: {msg}"


def convert_to_wav(input_path: Path, delete_source: bool = False) -> Path:
    """Convert any audio/video file to mono 16 kHz WAV (optimal for Whisper)."""
    output_path = input_path.with_suffix("").with_name(
        input_path.stem + f"_{uuid.uuid4().hex[:6]}.wav"
    )
    logger.info("Converting %s → %s", input_path.name, output_path.name)
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(output_path, format="wav")
    except Exception as exc:
        raise AudioProcessingError(f"Audio conversion failed: {exc}") from exc

    if delete_source and input_path != output_path:
        try:
            input_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete raw file %s", input_path)
    return output_path


def chunk_audio(wav_path: Path, chunk_minutes: int | None = None) -> list[Path]:
    """Split a WAV file into fixed-length chunks. Returns ordered chunk paths."""
    chunk_minutes = chunk_minutes or settings.AUDIO_CHUNK_MINUTES
    chunk_ms = chunk_minutes * 60 * 1000

    try:
        audio = AudioSegment.from_wav(wav_path)
    except Exception as exc:
        raise AudioProcessingError(f"Could not read WAV file: {exc}") from exc

    chunk_paths: list[Path] = []
    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        piece = audio[start: start + chunk_ms]
        chunk_path = wav_path.with_name(f"{wav_path.stem}_chunk_{i}.wav")
        piece.export(chunk_path, format="wav")
        chunk_paths.append(chunk_path)

    logger.info("Chunked %s into %d piece(s)", wav_path.name, len(chunk_paths))
    return chunk_paths


def prepare_source(source: str, session_id: str, *, is_upload: bool = False) -> list[Path]:
    """
    Full acquisition pipeline: (YouTube URL | uploaded file path) → WAV chunks.
    """
    if is_upload:
        wav = convert_to_wav(Path(source))
    elif is_youtube_url(source):
        wav = download_youtube_audio(source, session_id)
    else:
        raise AudioProcessingError(
            "Source must be a YouTube URL or an uploaded file."
        )
    return chunk_audio(wav)


def cleanup_session_files(session_id: str) -> None:
    """Delete all temp audio produced for one session."""
    import shutil

    for base in (settings.DOWNLOAD_DIR, settings.UPLOAD_DIR):
        d = base / session_id
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)