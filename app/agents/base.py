"""
Base agent class — all agents inherit from this.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core import kimi_client
from app.core.memory.manager import recall_as_context
from app.models.agent import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_BASE = (
    "You are part of an autonomous AI software engineering system. "
    "Be precise, practical, and production-quality in everything you produce."
)


class BaseAgent(ABC):
    name: str = "base"
    system_prompt: str = SYSTEM_BASE

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._history: list[dict[str, Any]] = []

    def _sys(self, extra: str = "") -> dict[str, Any]:
        content = self.system_prompt
        if extra:
            content += f"\n\n{extra}"
        return {"role": "system", "content": content}

    async def _chat(
        self,
        user_msg: str,
        *,
        inject_memory: bool = True,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        memory_ctx = ""
        if inject_memory:
            memory_ctx = await recall_as_context(user_msg)

        messages = [self._sys(memory_ctx)] + self._history + [{"role": "user", "content": user_msg}]
        result = await kimi_client.chat(messages, tools=tools, temperature=temperature)
        # Keep only last 4 turns to stay within token limits
        self._history.append({"role": "user", "content": user_msg[:2000]})
        self._history.append({"role": "assistant", "content": result["content"][:2000]})
        self._history = self._history[-8:]
        return result

    @abstractmethod
    async def run(self, input_text: str, **kwargs) -> AgentResult:
        ...
