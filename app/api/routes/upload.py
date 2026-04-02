"""
Upload routes — ingest files and URLs into the RAG pipeline for a session.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.rag.extractor import (
    SUPPORTED_EXTENSIONS,
    extract_from_bytes,
    extract_from_url,
)
from app.core.rag.pipeline import get_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])

MAX_FILE_SIZE = 5 * 1024 * 1024   # 5 MB


class UploadResult(BaseModel):
    session_id: str
    name: str
    type: str
    chunks: int
    chars: int
    status: str = "ok"


class URLIngestRequest(BaseModel):
    url: str
    session_id: str


@router.post("/file", response_model=UploadResult)
async def upload_file(
    session_id: Annotated[str, Form()],
    file: UploadFile = File(...),
):
    """Upload a file and ingest it into the RAG pipeline for the given session."""
    from pathlib import Path

    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    text = await extract_from_bytes(file.filename or "upload", data)
    pipeline = get_pipeline(session_id)
    summary = await pipeline.ingest(file.filename or "upload", text, source_type="file")

    return UploadResult(
        session_id=session_id,
        name=summary["name"],
        type=summary["type"],
        chunks=summary["chunks"],
        chars=summary["chars"],
    )


@router.post("/url", response_model=UploadResult)
async def ingest_url(body: URLIngestRequest):
    """Fetch a URL and ingest its content into the RAG pipeline."""
    title, text = await extract_from_url(body.url)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from URL")

    pipeline = get_pipeline(body.session_id)
    summary = await pipeline.ingest(title or body.url, text, source_type="url")

    return UploadResult(
        session_id=body.session_id,
        name=summary["name"],
        type=summary["type"],
        chunks=summary["chunks"],
        chars=summary["chars"],
    )


@router.get("/sources/{session_id}")
async def list_sources(session_id: str):
    """List all ingested sources for a session."""
    pipeline = get_pipeline(session_id)
    return {"session_id": session_id, "sources": pipeline.sources()}
