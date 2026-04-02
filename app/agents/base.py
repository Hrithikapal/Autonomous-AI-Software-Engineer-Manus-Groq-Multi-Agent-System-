"""
Base agent class — all agents inherit from this.
Implements ReAct (Reason + Act) pattern with observable reasoning traces.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.core import kimi_client
from app.core.memory.manager import recall_as_context
from app.models.agent import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_BASE = (
    "You are part of an autonomous AI software engineering system. "
    "Be precise, practical, and production-quality in everything you produce.\n\n"
    "Before answering, think step by step:\n"
    "THOUGHT: <your reasoning about what to do>\n"
    "ACTION: <what you will do>\n"
    "Then provide your full response."
)

# Global token counter — shared across all agents in a task run
_token_usage: dict[str, int] = {}


def record_tokens(task_id: str, prompt: int, completion: int) -> None:
    _token_usage[task_id] = _token_usage.get(task_id, 0) + prompt + completion


def get_token_usage(task_id: str) -> int:
    return _token_usage.get(task_id, 0)


def clear_token_usage(task_id: str) -> None:
    _token_usage.pop(task_id, None)


class BaseAgent(ABC):
    name: str = "base"
    system_prompt: str = SYSTEM_BASE

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._history: list[dict[str, Any]] = []
        self._react_steps: list[dict[str, Any]] = []

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

        # Track token usage
        usage = result.get("usage", {})
        record_tokens(self.task_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

        # Parse ReAct trace from response
        content = result["content"]
        react = _parse_react(content, self.name)
        if react:
            self._react_steps.append(react)

        # Rolling history — keep last 4 turns
        self._history.append({"role": "user", "content": user_msg[:2000]})
        self._history.append({"role": "assistant", "content": content[:2000]})
        self._history = self._history[-8:]

        return result

    def get_react_steps(self) -> list[dict[str, Any]]:
        return self._react_steps

    @abstractmethod
    async def run(self, input_text: str, **kwargs) -> AgentResult:
        ...


def _parse_react(text: str, agent_name: str) -> dict[str, Any] | None:
    """Extract THOUGHT/ACTION blocks from agent response."""
    import re
    thought_match = re.search(r"THOUGHT:\s*(.+?)(?=ACTION:|$)", text, re.DOTALL | re.IGNORECASE)
    action_match = re.search(r"ACTION:\s*(.+?)(?=\n\n|THOUGHT:|$)", text, re.DOTALL | re.IGNORECASE)

    if not thought_match:
        return None

    return {
        "agent": agent_name,
        "thought": thought_match.group(1).strip()[:300],
        "action": action_match.group(1).strip()[:200] if action_match else "Generating response",
        "observation": text.split("ACTION:")[-1].strip()[:300] if action_match else text[:300],
    }
