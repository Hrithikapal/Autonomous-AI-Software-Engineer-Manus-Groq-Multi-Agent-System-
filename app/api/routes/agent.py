"""
Agent execution routes.
POST /agent/run  → Server-Sent Events stream
POST /agent/sync → Blocking (for testing)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.manus import Manus
from app.api.routes.tasks import get_store
from app.evaluation.metrics import ACTIVE_TASKS, record_task_completed, record_task_failed
from app.models.task import Task, TaskCreate, TaskStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ------------------------------------------------------------------
# SSE streaming endpoint (recommended)
# ------------------------------------------------------------------

@router.post("/run")
async def run_agent_stream(body: TaskCreate):
    """
    Stream task execution as Server-Sent Events.
    Connect with: EventSource('/api/v1/agent/run', {method:'POST', ...})
    """
    task = Task(description=body.description, context=body.context)
    get_store()[task.id] = task

    async def event_stream() -> AsyncIterator[str]:
        ACTIVE_TASKS.inc()
        start = time.monotonic()
        try:
            orchestrator = Manus(task)
            async for event in orchestrator.run():
                get_store()[task.id] = task  # keep store in sync
                payload = json.dumps(event.model_dump(mode="json"))
                yield f"event: {event.event}\ndata: {payload}\n\n"
                await asyncio.sleep(0)  # yield to event loop

            score = 0.0
            if task.result and task.result.evaluation:
                score = task.result.evaluation.get("score", 0.0)
            record_task_completed(time.monotonic() - start, score)

        except Exception as exc:
            logger.exception("Stream error task=%s", task.id)
            record_task_failed()
            payload = json.dumps({"error": str(exc), "task_id": task.id})
            yield f"event: task_failed\ndata: {payload}\n\n"
        finally:
            ACTIVE_TASKS.dec()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Task-ID": task.id,
        },
    )


# ------------------------------------------------------------------
# Blocking endpoint (convenient for curl / testing)
# ------------------------------------------------------------------

@router.post("/sync", response_model=Task)
async def run_agent_sync(body: TaskCreate):
    """
    Run the full agent pipeline and return when done.
    Suitable for short tasks or automated tests.
    """
    task = Task(description=body.description, context=body.context)
    get_store()[task.id] = task
    ACTIVE_TASKS.inc()
    start = time.monotonic()

    try:
        orchestrator = Manus(task)
        async for _ in orchestrator.run():
            get_store()[task.id] = task

        score = 0.0
        if task.result and task.result.evaluation:
            score = task.result.evaluation.get("score", 0.0)
        record_task_completed(time.monotonic() - start, score)
        return task

    except Exception as exc:
        record_task_failed()
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        return task
    finally:
        ACTIVE_TASKS.dec()
