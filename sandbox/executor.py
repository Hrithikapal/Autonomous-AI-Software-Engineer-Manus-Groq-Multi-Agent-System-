"""
Sandboxed code execution service.
Runs arbitrary code in an isolated container with strict timeouts.
"""
import asyncio
import os
import sys
import tempfile
import traceback
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Code Sandbox", version="1.0.0")

MAX_EXEC_TIME = int(os.getenv("MAX_EXEC_TIME", "30"))  # seconds
MAX_OUTPUT_SIZE = 50_000  # bytes


class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: Optional[int] = None
    stdin: Optional[str] = None


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    execution_time_ms: float


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute_code(req: ExecuteRequest):
    timeout = min(req.timeout or MAX_EXEC_TIME, MAX_EXEC_TIME)

    if req.language == "python":
        return await _run_python(req.code, timeout, req.stdin)
    elif req.language in ("bash", "sh"):
        return await _run_bash(req.code, timeout, req.stdin)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")


async def _run_python(code: str, timeout: int, stdin: Optional[str]) -> ExecuteResponse:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(code)
        script_path = f.name

    return await _run_subprocess(
        [sys.executable, "-u", script_path],
        timeout,
        stdin,
        cleanup=script_path,
    )


async def _run_bash(code: str, timeout: int, stdin: Optional[str]) -> ExecuteResponse:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, dir="/tmp") as f:
        f.write(code)
        script_path = f.name

    return await _run_subprocess(
        ["/bin/sh", script_path],
        timeout,
        stdin,
        cleanup=script_path,
    )


async def _run_subprocess(
    cmd: list[str],
    timeout: int,
    stdin: Optional[str],
    cleanup: Optional[str] = None,
) -> ExecuteResponse:
    import time

    start = time.monotonic()
    timed_out = False

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else None,
        )

        try:
            stdin_bytes = stdin.encode() if stdin else None
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            timed_out = True
            stdout_bytes = b""
            stderr_bytes = b"TimeoutError: execution exceeded limit"

        elapsed_ms = (time.monotonic() - start) * 1000

        stdout = stdout_bytes[:MAX_OUTPUT_SIZE].decode("utf-8", errors="replace")
        stderr = stderr_bytes[:MAX_OUTPUT_SIZE].decode("utf-8", errors="replace")

        return ExecuteResponse(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode if not timed_out else -1,
            timed_out=timed_out,
            execution_time_ms=round(elapsed_ms, 2),
        )
    finally:
        if cleanup and os.path.exists(cleanup):
            os.unlink(cleanup)
