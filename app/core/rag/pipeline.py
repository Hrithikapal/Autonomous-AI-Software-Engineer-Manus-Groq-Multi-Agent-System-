"""
RAG pipeline — chunk, store, and retrieve context from uploaded files and URLs.
Each upload session gets a namespace in ChromaDB so contexts don't bleed between tasks.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.core.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 150    # overlap between chunks


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks at sentence/newline boundaries."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to break at a newline or period
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", " "):
                pos = text.rfind(sep, start + overlap, end)
                if pos != -1:
                    end = pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def _doc_id(session_id: str, source: str, idx: int) -> str:
    key = f"{session_id}:{source}:{idx}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class RAGPipeline:
    """Per-session RAG context manager."""

    COLLECTION = "rag_context"

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._store = VectorStore(self.COLLECTION)
        self._sources: list[dict[str, Any]] = []   # [{id, name, type, char_count}]

    async def ingest(self, name: str, text: str, source_type: str = "file") -> dict[str, Any]:
        """Chunk and store text. Returns ingestion summary."""
        if not text.strip():
            return {"name": name, "chunks": 0, "chars": 0}

        chunks = _chunk(text)
        for i, chunk in enumerate(chunks):
            doc_id = _doc_id(self.session_id, name, i)
            await self._store.add(
                doc_id=doc_id,
                text=chunk,
                metadata={
                    "session_id": self.session_id,
                    "source": name,
                    "source_type": source_type,
                    "chunk_index": str(i),
                },
            )

        summary = {"name": name, "chunks": len(chunks), "chars": len(text), "type": source_type}
        self._sources.append(summary)
        logger.info("RAG ingested %s — %d chunks", name, len(chunks))
        return summary

    async def retrieve(self, query: str, n: int = 5) -> str:
        """Return top-n relevant chunks as a formatted context string."""
        try:
            hits = await self._store.query(
                query_text=query,
                n_results=n,
                where={"session_id": self.session_id},
            )
        except Exception as exc:
            logger.warning("RAG retrieve failed: %s", exc)
            return ""

        if not hits:
            return ""

        parts = ["## Context from uploaded files/URLs"]
        seen_sources: set[str] = set()
        for h in hits:
            src = h["metadata"].get("source", "unknown")
            if src not in seen_sources:
                parts.append(f"\n### {src}")
                seen_sources.add(src)
            parts.append(h["document"])

        return "\n".join(parts)

    def sources(self) -> list[dict[str, Any]]:
        return self._sources


# ── Global session registry ──────────────────────────────
_pipelines: dict[str, RAGPipeline] = {}


def get_pipeline(session_id: str) -> RAGPipeline:
    if session_id not in _pipelines:
        _pipelines[session_id] = RAGPipeline(session_id)
    return _pipelines[session_id]
