"""
Tool: async file I/O within the task workspace.
Each task gets its own isolated directory: workspace/<task_id>/
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import aiofiles

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", "/app/workspace"))


def task_dir(task_id: str) -> Path:
    d = WORKSPACE_ROOT / task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def write_file(task_id: str, filename: str, content: str) -> Path:
    path = task_dir(task_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)
    logger.debug("file_manager.write %s", path)
    return path


async def read_file(task_id: str, filename: str) -> str:
    path = task_dir(task_id) / filename
    async with aiofiles.open(path, encoding="utf-8") as f:
        return await f.read()


async def list_files(task_id: str) -> list[str]:
    d = task_dir(task_id)
    return [str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()]


async def collect_workspace(task_id: str) -> dict[str, str]:
    """Return all files in the task workspace as {filename: content}."""
    files = await list_files(task_id)
    result: dict[str, str] = {}
    for fname in files:
        try:
            result[fname] = await read_file(task_id, fname)
        except Exception:
            pass
    return result
