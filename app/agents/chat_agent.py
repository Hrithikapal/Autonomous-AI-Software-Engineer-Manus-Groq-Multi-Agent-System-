"""
Chat Agent — conversational interface.
Has full context of the current session: tasks run, code generated, evaluations.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core import kimi_client

logger = logging.getLogger(__name__)

SYSTEM = """You are Manus, an autonomous AI software engineer assistant.
You are helpful, concise, and technical. You have memory of everything done in this session.

You can:
- Explain what you built and why you made certain decisions
- Walk through the code you generated
- Discuss the evaluation scores and what they mean
- Suggest improvements or next steps
- Answer general software engineering questions
- Help debug issues the user notices

Be conversational but precise. When referencing code, be specific about files and functions.
Keep responses concise — this is a chat, not a report.
"""


class ChatAgent:
    """Stateful conversational agent with session context."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._history: list[dict[str, Any]] = []
        self._task_context: str = ""

    def set_task_context(self, context: str) -> None:
        self._task_context = context

    async def chat(self, message: str) -> str:
        system_content = SYSTEM
        if self._task_context:
            system_content += f"\n\n## Session Context\n{self._task_context}"

        messages = (
            [{"role": "system", "content": system_content}]
            + self._history[-20:]
            + [{"role": "user", "content": message}]
        )

        resp = await kimi_client.chat(messages, temperature=0.5, max_tokens=1024)
        reply = resp["content"]

        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": reply})

        return reply

    def clear_history(self) -> None:
        self._history = []
