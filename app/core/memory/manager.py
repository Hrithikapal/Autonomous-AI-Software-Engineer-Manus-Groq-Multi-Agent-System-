"""
Memory manager — learns from past bugs and solutions.
Agents call this to persist knowledge and recall relevant context.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.core.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

_store = VectorStore()


def _doc_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


async def remember_solution(
    problem: str,
    solution: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a problem→solution pair for future recall."""
    doc = f"PROBLEM: {problem}\n\nSOLUTION: {solution}"
    doc_id = _doc_id(doc)
    meta = {"type": "solution", **(metadata or {})}
    await _store.add(doc_id, doc, meta)
    logger.info("Memory saved id=%s", doc_id)


async def remember_bug_fix(
    error: str,
    fix: str,
    language: str = "python",
) -> None:
    """Persist a bug→fix pair so the debug agent can reuse it."""
    doc = f"ERROR: {error}\n\nFIX: {fix}"
    doc_id = _doc_id(doc)
    await _store.add(doc_id, doc, {"type": "bug_fix", "language": language})


async def recall(
    query: str,
    n: int = 3,
    memory_type: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over memory. Returns top-n relevant memories."""
    where = {"type": memory_type} if memory_type else None
    hits = await _store.query(query, n_results=n, where=where)
    return hits


async def recall_as_context(query: str, n: int = 3) -> str:
    """Return relevant memories formatted as a string for injection into prompts."""
    try:
        hits = await recall(query, n)
        if not hits:
            return ""
        lines = ["## Relevant past experience"]
        for h in hits:
            lines.append(f"- {h['document'][:500]}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("recall_as_context failed (non-critical): %s", exc)
        return ""
