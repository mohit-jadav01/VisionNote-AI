"""
VisionNote AI — FAISS vector store for RAG.

Uses FAISS (faiss-cpu) instead of ChromaDB because FAISS ships with
pre-built Windows wheels — no C++ compiler required.

Stack: FAISS + all-MiniLM-L6-v2 HuggingFace embeddings
  • per-session index files so concurrent users never mix transcripts,
  • cached embedding model (loaded once per process),
  • typed, documented API.

Import notes
  -----------
  HuggingFaceEmbeddings and FAISS are intentionally NOT imported at module
  level.  Both pull in sentence-transformers / torch / faiss which can take
  tens of seconds on a cold start.  We defer them to the first real request
  so that Uvicorn binds its port instantly and Render detects the service
  as healthy before any ML work begins.
"""

from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

# Lightweight langchain-core imports are fine at module level.
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Heavy ML packages are imported lazily inside the functions that need them.
# TYPE_CHECKING=False at runtime, so these aliases are never actually imported
# during normal execution — they exist only to satisfy static type checkers.
if TYPE_CHECKING:
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

logger = logging.getLogger("visionnote.vectorstore")


@lru_cache
def get_embedding_model() -> "HuggingFaceEmbeddings":
    """Load the sentence-transformer embedding model once per process.

    Heavy import (sentence-transformers / torch) is deferred to the first
    call so that Uvicorn starts instantly on cold boots.
    """
    # Lazy import: only runs when a vector store is actually built or loaded.
    from langchain_huggingface import HuggingFaceEmbeddings  # noqa: PLC0415

    logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )


def _index_path(session_id: str) -> Path:
    """Return the directory where this session's FAISS index is stored."""
    return settings.CHROMA_DIR / f"faiss_{session_id}"


def build_vector_store(transcript: str, session_id: str) -> "FAISS":
    """Chunk a transcript, embed it and persist a per-session FAISS index."""
    # Lazy import: FAISS pulls in faiss-cpu which is not needed at startup.
    from langchain_community.vectorstores import FAISS  # noqa: PLC0415

    logger.info("Building FAISS vector store for session %s", session_id)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " "],
    )
    chunks = splitter.split_text(transcript)
    docs = [
        Document(page_content=chunk, metadata={"chunk_index": i, "session_id": session_id})
        for i, chunk in enumerate(chunks)
    ]

    embeddings = get_embedding_model()
    vectorstore = FAISS.from_documents(docs, embeddings)

    # Persist to disk so the index survives across the pipeline steps
    idx_path = _index_path(session_id)
    idx_path.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(idx_path))

    logger.info("Indexed %d chunks for session %s → %s", len(docs), session_id, idx_path)
    return vectorstore


def load_vector_store(session_id: str) -> "FAISS":
    """Load a persisted FAISS index for a session."""
    # Lazy import: mirrors build_vector_store; only runs during RAG queries.
    from langchain_community.vectorstores import FAISS  # noqa: PLC0415

    idx_path = _index_path(session_id)
    if not idx_path.exists():
        raise FileNotFoundError(
            f"No FAISS index found for session '{session_id}'. "
            "Run the analysis pipeline first."
        )
    embeddings = get_embedding_model()
    return FAISS.load_local(
        str(idx_path),
        embeddings,
        allow_dangerous_deserialization=True,   # safe: we wrote these files ourselves
    )


def get_retriever(vectorstore: "FAISS", k: int | None = None) -> VectorStoreRetriever:
    return vectorstore.as_retriever(search_kwargs={"k": k or settings.RAG_TOP_K})


def delete_vector_store(session_id: str) -> None:
    """Remove the FAISS index directory for a session."""
    idx_path = _index_path(session_id)
    if idx_path.exists():
        try:
            shutil.rmtree(idx_path)
            logger.info("Deleted FAISS index for session %s", session_id)
        except Exception as exc:
            logger.warning("Vector store cleanup skipped: %s", exc)
