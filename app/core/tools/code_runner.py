"""
Tool: run code in the sandboxed Docker executor.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.models.agent import CodeExecution

logger = logging.getLogger(__name__)


async def run_code(
    code: str,
    language: str = "python",
    stdin: str | None = None,
    timeout: int | None = None,
) -> CodeExecution:
    s = get_settings()
    t = timeout or s.max_exec_time
    url = f"{s.sandbox_url}/execute"

    async with httpx.AsyncClient(timeout=t + 5) as client:
        resp = await client.post(
            url,
            json={"code": code, "language": language, "stdin": stdin, "timeout": t},
        )
        resp.raise_for_status()
        data = resp.json()

    result = CodeExecution(**data)
    logger.info(
        "code_runner exit=%d timed_out=%s ms=%.1f",
        result.exit_code,
        result.timed_out,
        result.execution_time_ms,
    )
    return result
