"""
Chat routes — conversational interface with session + task context.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.chat_agent import ChatAgent
from app.api.routes.tasks import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory session store: session_id → ChatAgent
_sessions: dict[str, ChatAgent] = {}


def _get_or_create_session(session_id: str) -> ChatAgent:
    if session_id not in _sessions:
        _sessions[session_id] = ChatAgent(session_id)
    return _sessions[session_id]


def _build_task_context(task_id: str | None) -> str:
    """Build a context string from a completed task so the agent can discuss it."""
    if not task_id:
        return _build_session_summary()

    store = get_store()
    task = store.get(task_id)
    if not task:
        return _build_session_summary()

    parts = [f"## Last Task: {task.description}", f"Status: {task.status.value}"]

    if task.plan:
        steps = ", ".join(f"{s.agent.value}({s.status.value})" for s in task.plan)
        parts.append(f"Plan steps: {steps}")

    if task.result:
        if task.result.files:
            parts.append(f"Generated files: {', '.join(task.result.files.keys())}")
        if task.result.code:
            parts.append(f"Primary code (first 1500 chars):\n```python\n{task.result.code[:1500]}\n```")
        if task.result.evaluation:
            ev = task.result.evaluation
            parts.append(
                f"Evaluation — score: {ev.get('score')}/10, "
                f"passed: {ev.get('passed')}, "
                f"feedback: {ev.get('feedback', '')[:300]}"
            )

    if task.latency_ms:
        parts.append(f"Total time: {task.latency_ms/1000:.1f}s")

    return "\n".join(parts)


def _build_session_summary() -> str:
    """Summarise all tasks in the session when no specific task is referenced."""
    store = get_store()
    if not store:
        return "No tasks have been run in this session yet."
    lines = ["## Tasks run this session"]
    for t in list(store.values())[-5:]:
        score = ""
        if t.result and t.result.evaluation:
            score = f" | score: {t.result.evaluation.get('score')}/10"
        lines.append(f"- [{t.status.value}] {t.description[:80]}{score}")
    return "\n".join(lines)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    task_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("/", response_model=ChatResponse)
async def send_message(body: ChatRequest):
    agent = _get_or_create_session(body.session_id)

    # Always refresh context with latest task state
    context = _build_task_context(body.task_id)
    agent.set_task_context(context)

    reply = await agent.chat(body.message)
    return ChatResponse(reply=reply, session_id=body.session_id)


@router.delete("/{session_id}")
async def clear_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
    return {"cleared": True}
