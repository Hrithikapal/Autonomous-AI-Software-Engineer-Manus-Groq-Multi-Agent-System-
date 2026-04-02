"""
Coding Agent — generates production-quality code based on task + research context.
"""
from __future__ import annotations

import logging
import re

from app.agents.base import BaseAgent
from app.core.tools.file_manager import write_file
from app.models.agent import AgentResult

logger = logging.getLogger(__name__)

SYSTEM = """You are an expert Software Engineer. You write clean, production-ready code.

Rules:
- Follow PEP-8 for Python; use type hints throughout.
- Add only necessary comments (for non-obvious logic).
- Structure output as multiple files when appropriate.
- For each file, use this format exactly:

===FILE: <filename>===
<file content>
===END===

- Always include a requirements.txt if third-party packages are used.
- Always include a basic test file (test_<module>.py).
- Prefer FastAPI for APIs, pytest for tests, standard library where possible.
"""

FILE_PATTERN = re.compile(r"===FILE:\s*(.+?)===\s*(.*?)===END===", re.DOTALL)


def parse_files(text: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for m in FILE_PATTERN.finditer(text):
        name = m.group(1).strip()
        content = m.group(2).strip()
        files[name] = content
    return files


class CodingAgent(BaseAgent):
    name = "coding"
    system_prompt = SYSTEM

    async def run(self, input_text: str, research_context: str = "", **kwargs) -> AgentResult:
        logger.info("[CodingAgent] task=%s", self.task_id)

        prompt = f"Task:\n{input_text}"
        if research_context:
            prompt += f"\n\nResearch Context:\n{research_context[:1500]}"
        prompt += (
            "\n\nGenerate the complete implementation. "
            "Use the ===FILE: <name>=== ... ===END=== format for each file."
        )

        resp = await self._chat(prompt, inject_memory=True)
        raw = resp["content"]
        files = parse_files(raw)

        if not files:
            # Fallback: treat entire response as main.py
            files = {"main.py": raw}

        # Persist to workspace
        for fname, content in files.items():
            await write_file(self.task_id, fname, content)

        # Return the primary code file
        primary = next(
            (v for k, v in files.items() if k.endswith(".py") and "test" not in k),
            next(iter(files.values()), ""),
        )

        return AgentResult(
            success=True,
            output=raw,
            code=primary,
            files=files,
            metadata={"file_count": len(files)},
        )
