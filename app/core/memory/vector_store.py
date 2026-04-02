"""
ChromaDB vector store for persistent agent memory.
Stores bug fixes, solutions, and reusable knowledge.
"""
from __future__ import annotations

import logging
from typing import Any

import chromadb

from app.config import get_settings

logger = logging.getLogger(__name__)

_chroma = None


async def get_chroma():
    global _chroma
    if _chroma is None:
        s = get_settings()
        _chroma = await chromadb.AsyncHttpClient(
            host=s.chroma_host,
            port=s.chroma_port,
        )
    return _chroma


async def get_collection(name: str | None = None):
    s = get_settings()
    client = await get_chroma()
    col = await client.get_or_create_collection(name=name or s.chroma_collection)
    return col


class VectorStore:
    """High-level async wrapper around a single ChromaDB collection."""

    def __init__(self, collection_name: str | None = None):
        self._collection_name = collection_name
        self._col = None

    async def _ensure(self):
        if self._col is None:
            self._col = await get_collection(self._collection_name)

    async def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        try:
            await self._ensure()
            # ChromaDB metadata values must be str/int/float/bool only
            safe_meta = {k: str(v) for k, v in (metadata or {}).items()}
            await self._col.upsert(ids=[doc_id], documents=[text], metadatas=[safe_meta])
            logger.debug("VectorStore.add id=%s", doc_id)
        except Exception as exc:
            logger.warning("VectorStore.add failed (non-critical): %s", exc)

    async def query(self, query_text: str, n_results: int = 5, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            await self._ensure()
            kwargs: dict[str, Any] = dict(
                query_texts=[query_text],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            if where:
                kwargs["where"] = where

            results = await self._col.query(**kwargs)
            hits = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    hits.append({
                        "id": doc_id,
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    })
            return hits
        except Exception as exc:
            logger.warning("VectorStore.query failed (non-critical): %s", exc)
            return []

    async def delete(self, doc_id: str) -> None:
        try:
            await self._ensure()
            await self._col.delete(ids=[doc_id])
        except Exception as exc:
            logger.warning("VectorStore.delete failed (non-critical): %s", exc)
