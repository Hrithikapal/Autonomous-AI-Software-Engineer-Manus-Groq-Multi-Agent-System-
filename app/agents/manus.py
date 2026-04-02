"""
Manus — the top-level orchestration agent.

Manus is named after the Latin word for "hand" — it does the work.
Architecture:

    User Request
         ↓
      Manus (Planner + Orchestrator)
         ↓
    ┌────────────────────────────────────┐
    │  ResearchAgent  (Kimi reasoning)   │
    │  CodingAgent    (Kimi reasoning)   │
    │  DebugAgent     (Kimi reasoning)   │
    │  TestAgent      (Kimi reasoning)   │
    └────────────────────────────────────┘
         ↓
      Manus (Evaluation + Decision)
         ↓
      Final Output

Manus:
  - Breaks tasks into steps (dynamic planning via Kimi)
  - Assigns steps to the right specialist agent
  - Runs the self-debug loop automatically
  - Triggers the improvement loop if quality < threshold
  - Persists successful solutions to memory (ChromaDB)
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agents.coding import CodingAgent
from app.agents.debug import DebugAgent
from app.agents.research import ResearchAgent
from app.agents.test_agent import TestAgent
from app.core import kimi_client
from app.core.memory.manager import recall_as_context, remember_solution
from app.models.task import Task, TaskCreate, TaskEvent, TaskStatus

logger = logging.getLogger(__name__)


class Manus:
    """
    The orchestration brain of the autonomous agent system.

    Usage (programmatic):
        task = Task(description="Build a URL shortener with analytics")
        manus = Manus(task)
        async for event in manus.run():
            print(event)

    Usage (via API):
        POST /api/v1/agent/run   → SSE stream
        POST /api/v1/agent/sync  → blocking response
    """

    VERSION = "1.0.0"

    # Specialist agents available to Manus
    AGENTS = {
        "research": ResearchAgent,
        "coding": CodingAgent,
        "debug": DebugAgent,
        "test": TestAgent,
    }

    def __init__(self, task: Task):
        self.task = task
        # Import here to avoid circular; Orchestrator IS the Manus engine
        from app.agents.orchestrator import Orchestrator
        self._engine = Orchestrator(task)

    async def run(self) -> AsyncIterator[TaskEvent]:
        """
        Execute the full autonomous pipeline.
        Yields TaskEvent objects in real-time (suitable for SSE).
        """
        async for event in self._engine.run():
            yield event

    async def run_to_completion(self) -> Task:
        """
        Blocking helper — runs the full pipeline and returns the final Task.
        Useful for scripts and tests.
        """
        async for _ in self.run():
            pass
        return self.task

    # ------------------------------------------------------------------
    # Class-level tool registry (mirrors the spec)
    # ------------------------------------------------------------------

    @classmethod
    def available_tools(cls) -> list[dict[str, Any]]:
        return [
            {"name": "research",  "agent": "ResearchAgent",  "description": "Web research and doc lookup"},
            {"name": "code",      "agent": "CodingAgent",    "description": "Code generation"},
            {"name": "debug",     "agent": "DebugAgent",     "description": "Self-healing debug loop"},
            {"name": "run_tests", "agent": "TestAgent",      "description": "Generate and run test suite"},
        ]

    @classmethod
    def create(cls, description: str, context: str | None = None) -> "Manus":
        """Convenience factory."""
        task = Task(description=description, context=context)
        return cls(task)
