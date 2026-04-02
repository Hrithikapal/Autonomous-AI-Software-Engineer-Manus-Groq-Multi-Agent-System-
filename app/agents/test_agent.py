"""
Test Agent — generates and runs test cases, reports pass/fail rates.
"""
from __future__ import annotations

import logging
import re

from app.agents.base import BaseAgent
from app.core.tools.code_runner import run_code
from app.core.tools.file_manager import write_file
from app.models.agent import AgentResult

logger = logging.getLogger(__name__)

SYSTEM = """You are a Test Engineer.
Given a task description and its implementation, write comprehensive pytest test cases.

Rules:
- Cover happy path, edge cases, and error cases.
- Use pytest fixtures where appropriate.
- Do NOT mock internal logic — test observable behaviour.
- Return ONLY the test file content (no explanations).
- The test file should be importable and runnable with: python -m pytest test_solution.py -v
"""


def _parse_pass_rate(output: str) -> float:
    """Parse pytest output → fraction of tests passed."""
    # e.g. "5 passed, 1 failed"
    passed = len(re.findall(r"\b(\d+) passed", output))
    failed = len(re.findall(r"\b(\d+) failed", output))
    total = passed + failed
    if total == 0:
        return 0.0
    return passed / total


class TestAgent(BaseAgent):
    name = "test"
    system_prompt = SYSTEM

    async def run(  # type: ignore[override]
        self,
        input_text: str,
        code: str = "",
        files: dict[str, str] | None = None,
        **kwargs,
    ) -> AgentResult:
        logger.info("[TestAgent] task=%s", self.task_id)

        # 1. Generate test file
        files = files or {}
        code_context = "\n\n".join(f"# {k}\n{v}" for k, v in files.items()) if files else code

        resp = await self._chat(
            f"Task: {input_text}\n\nImplementation:\n{code_context}\n\nWrite pytest tests.",
            inject_memory=False,
        )
        test_code = resp["content"]

        # Strip markdown fences if present
        test_code = re.sub(r"```python\s*", "", test_code)
        test_code = re.sub(r"```\s*", "", test_code)

        await write_file(self.task_id, "test_solution.py", test_code)

        # 2. Build a combined runner script
        all_code = "\n\n# ---- implementation ----\n" + code_context
        runner = (
            all_code
            + "\n\n# ---- tests ----\n"
            + test_code
            + "\n\nif __name__ == '__main__':\n"
            + "    import pytest, sys\n"
            + "    sys.exit(pytest.main([__file__, '-v', '--tb=short']))\n"
        )

        result = await run_code(runner)
        pass_rate = _parse_pass_rate(result.stdout + result.stderr)

        summary = (
            f"Pass rate: {pass_rate:.0%}\n"
            f"Exit code: {result.exit_code}\n\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )

        return AgentResult(
            success=result.success or pass_rate > 0,
            output=summary,
            code=test_code,
            metadata={"pass_rate": pass_rate, "exit_code": result.exit_code},
        )
