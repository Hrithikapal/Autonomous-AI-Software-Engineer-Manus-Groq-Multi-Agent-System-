"""
Debug Agent — self-healing loop.
Receives code + execution error → produces fixed code.
Retries up to MAX_DEBUG_RETRIES times.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.agents.coding import parse_files
from app.config import get_settings
from app.core.memory.manager import remember_bug_fix
from app.core.tools.code_runner import run_code
from app.core.tools.file_manager import write_file
from app.models.agent import AgentResult, CodeExecution

logger = logging.getLogger(__name__)

SYSTEM = """You are an expert Debugger.
You receive code that failed to run and the error output.
Your job:
1. Identify the root cause of the error.
2. Fix ALL issues in one go.
3. Return the complete fixed file(s) using ===FILE: <name>=== ... ===END=== format.
4. Do NOT truncate — always return the full corrected file content.
"""


class DebugAgent(BaseAgent):
    name = "debug"
    system_prompt = SYSTEM

    async def run(  # type: ignore[override]
        self,
        input_text: str,
        code: str = "",
        error: str = "",
        files: dict[str, str] | None = None,
        **kwargs,
    ) -> AgentResult:
        s = get_settings()
        logger.info("[DebugAgent] task=%s", self.task_id)

        current_code = code
        current_files = files or {"main.py": code}
        last_error = error
        last_result: CodeExecution | None = None

        for attempt in range(1, s.max_debug_retries + 1):
            logger.info("[DebugAgent] attempt %d/%d", attempt, s.max_debug_retries)

            # Ask Kimi to fix it
            files_dump = "\n\n".join(
                f"===FILE: {k}===\n{v}\n===END===" for k, v in current_files.items()
            )
            prompt = (
                f"The following code raised an error.\n\n"
                f"ERROR:\n{last_error}\n\n"
                f"CODE:\n{files_dump}\n\n"
                f"Fix the bug(s) and return the complete corrected file(s)."
            )
            resp = await self._chat(prompt, inject_memory=True)
            fixed_files = parse_files(resp["content"])

            if not fixed_files:
                fixed_files = {"main.py": resp["content"]}

            # Persist fixed files
            for fname, content in fixed_files.items():
                await write_file(self.task_id, fname, content)

            # Re-run the primary file
            primary_name = next(
                (k for k in fixed_files if k.endswith(".py") and "test" not in k),
                next(iter(fixed_files)),
            )
            last_result = await run_code(fixed_files[primary_name])

            if last_result.success:
                # Persist this fix to memory
                await remember_bug_fix(
                    error=last_error,
                    fix=fixed_files.get(primary_name, ""),
                )
                logger.info("[DebugAgent] fixed on attempt %d", attempt)
                return AgentResult(
                    success=True,
                    output=f"Fixed after {attempt} attempt(s).\n\n{last_result.stdout}",
                    code=fixed_files.get(primary_name, ""),
                    files=fixed_files,
                    metadata={"attempts": attempt},
                )

            current_files = fixed_files
            last_error = last_result.stderr or last_result.stdout
            current_code = fixed_files.get(primary_name, current_code)

        return AgentResult(
            success=False,
            output=f"Failed after {s.max_debug_retries} debug attempts.",
            error=last_error,
            code=current_code,
            files=current_files,
            metadata={"attempts": s.max_debug_retries},
        )
