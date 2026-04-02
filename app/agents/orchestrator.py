"""
Orchestrator — the brain of the system (Manus-style).

Flow:
  1. Plan  → break task into steps
  2. Execute steps using specialised agents
  3. Self-debug loop if code fails
  4. Evaluate final output
  5. Retry / improve if quality is low
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.coding import CodingAgent
from app.agents.debug import DebugAgent
from app.agents.research import ResearchAgent
from app.agents.test_agent import TestAgent
from app.config import get_settings
from app.core import kimi_client
from app.core.memory.manager import recall_as_context, remember_solution
from app.core.tools.code_runner import run_code
from app.core.tools.file_manager import collect_workspace
from app.evaluation.evaluator import evaluate
from app.models.task import AgentType, PlanStep, StepStatus, Task, TaskEvent, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """You are Manus, an elite AI software engineering orchestrator.
Given a task, produce a concise execution plan as a JSON array of steps.

Each step must have:
- "order": int (1-based)
- "description": str (what to do)
- "agent": one of ["research", "coding", "debug", "test"]

Rules:
- Always start with research unless the task is trivial.
- coding always follows research.
- test always follows coding.
- debug is inserted automatically — do NOT include it in the plan.
- Keep the plan to ≤ 8 steps.
- Return ONLY valid JSON, no markdown fences, no explanation.
"""

IMPROVER_SYSTEM = """You are a senior engineer reviewing code output.
The evaluation score is below threshold. Suggest specific, actionable improvements.
Be brief — the Coding Agent will implement your suggestions.
"""


class Orchestrator:
    def __init__(self, task: Task):
        self.task = task
        self.s = get_settings()
        self._research_result: str = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> AsyncIterator[TaskEvent]:
        start_ms = time.monotonic() * 1000
        t = self.task

        try:
            # 1. Planning
            t.status = TaskStatus.PLANNING
            async for ev in self._plan():
                yield ev

            # 2. Execute plan
            t.status = TaskStatus.IN_PROGRESS
            async for ev in self._execute_plan():
                yield ev

            # 3. Evaluate
            t.status = TaskStatus.EVALUATING
            async for ev in self._evaluate():
                yield ev

            t.status = TaskStatus.COMPLETED
            t.latency_ms = time.monotonic() * 1000 - start_ms
            t.touch()
            yield TaskEvent(event="task_done", task_id=t.id, data=t.model_dump(mode="json"))

        except Exception as exc:
            logger.exception("Orchestrator error task=%s", t.id)
            t.status = TaskStatus.FAILED
            t.error = str(exc)
            t.touch()
            yield TaskEvent(event="task_failed", task_id=t.id, data={"error": str(exc)})

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan(self) -> AsyncIterator[TaskEvent]:
        t = self.task
        memory_ctx = await recall_as_context(t.description, n=2)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM + (f"\n\n{memory_ctx}" if memory_ctx else "")},
            {"role": "user", "content": t.description},
        ]
        resp = await kimi_client.chat(messages, temperature=0.1)
        raw = resp["content"].strip()

        try:
            steps_data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON array from response
            import re
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            steps_data = json.loads(match.group()) if match else []

        t.plan = [
            PlanStep(
                order=s["order"],
                description=s["description"],
                agent=AgentType(s["agent"]),
            )
            for s in steps_data[: self.s.max_plan_steps]
        ]
        t.touch()
        yield TaskEvent(
            event="plan_ready",
            task_id=t.id,
            data={"steps": [s.model_dump() for s in t.plan]},
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute_plan(self) -> AsyncIterator[TaskEvent]:
        t = self.task
        coding_result = None
        files: dict[str, str] = {}

        for step in t.plan:
            step.status = StepStatus.IN_PROGRESS
            t.touch()
            yield TaskEvent(
                event="step_start",
                task_id=t.id,
                data={"step": step.model_dump()},
            )

            step_start = time.monotonic()
            try:
                result = await self._run_step(step, files=files)
                step.execution_time_ms = (time.monotonic() - step_start) * 1000

                if step.agent == AgentType.RESEARCH:
                    self._research_result = result.output

                elif step.agent == AgentType.CODING:
                    coding_result = result
                    files = result.files

                    # Self-debug loop
                    if result.code:
                        exec_result = await run_code(result.code)
                        if not exec_result.success:
                            t.status = TaskStatus.DEBUGGING
                            t.touch()
                            yield TaskEvent(
                                event="debug_start",
                                task_id=t.id,
                                data={"error": exec_result.stderr[:500]},
                            )
                            debug_agent = DebugAgent(t.id)
                            debug_result = await debug_agent.run(
                                t.description,
                                code=result.code,
                                error=exec_result.stderr,
                                files=files,
                            )
                            if debug_result.success:
                                coding_result = debug_result
                                files = debug_result.files
                            t.status = TaskStatus.IN_PROGRESS

                elif step.agent == AgentType.TEST:
                    pass  # results captured in evaluation

                step.output = result.output[:2000]
                step.status = StepStatus.COMPLETED

            except Exception as exc:
                step.status = StepStatus.FAILED
                step.error = str(exc)
                logger.exception("Step failed task=%s step=%s", t.id, step.id)
                yield TaskEvent(
                    event="step_error",
                    task_id=t.id,
                    data={"step": step.model_dump(), "error": str(exc)},
                )
                continue

            t.touch()
            yield TaskEvent(
                event="step_done",
                task_id=t.id,
                data={"step": step.model_dump()},
            )

        # Persist final workspace
        all_files = await collect_workspace(t.id)
        primary_code = (coding_result.code if coding_result else "") or ""
        t.result = TaskResult(files=all_files, code=primary_code)

    async def _run_step(self, step: PlanStep, files: dict[str, str]) -> Any:
        t = self.task
        if step.agent == AgentType.RESEARCH:
            agent = ResearchAgent(t.id)
            return await agent.run(t.description)

        elif step.agent == AgentType.CODING:
            agent = CodingAgent(t.id)
            return await agent.run(t.description, research_context=self._research_result)

        elif step.agent == AgentType.TEST:
            agent = TestAgent(t.id)
            primary = next(
                (v for k, v in files.items() if k.endswith(".py") and "test" not in k), ""
            )
            return await agent.run(t.description, code=primary, files=files)

        else:
            from app.models.agent import AgentResult
            return AgentResult(success=True, output=f"Step {step.agent} skipped.")

    # ------------------------------------------------------------------
    # Evaluation + improvement loop
    # ------------------------------------------------------------------

    async def _evaluate(self) -> AsyncIterator[TaskEvent]:
        t = self.task
        if not t.result:
            return

        eval_result = await evaluate(
            task=t.description,
            code=t.result.code or "",
            files=t.result.files,
        )
        t.result.evaluation = eval_result.model_dump()
        t.touch()

        yield TaskEvent(
            event="evaluation_done",
            task_id=t.id,
            data={"evaluation": eval_result.model_dump()},
        )

        # Improvement loop if score < 6
        if eval_result.score < 6.0 and t.result.code:
            yield TaskEvent(
                event="improving",
                task_id=t.id,
                data={"score": eval_result.score, "feedback": eval_result.feedback},
            )
            messages = [
                {"role": "system", "content": IMPROVER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Task: {t.description}\n\n"
                        f"Score: {eval_result.score}/10\n"
                        f"Feedback: {eval_result.feedback}\n\n"
                        "List specific improvements."
                    ),
                },
            ]
            resp = await kimi_client.chat(messages, temperature=0.3)
            suggestions = resp["content"]

            # Re-run coding with improvements
            coding_agent = CodingAgent(t.id)
            improved = await coding_agent.run(
                f"{t.description}\n\nIMPROVEMENTS REQUIRED:\n{suggestions}",
                research_context=self._research_result,
            )
            if improved.success:
                t.result.code = improved.code
                t.result.files.update(improved.files)

                # Re-evaluate
                eval2 = await evaluate(t.description, code=improved.code or "", files=improved.files)
                t.result.evaluation = eval2.model_dump()
                yield TaskEvent(
                    event="evaluation_done",
                    task_id=t.id,
                    data={"evaluation": eval2.model_dump(), "improved": True},
                )

        # Persist to long-term memory
        if eval_result.score >= 7.0:
            await remember_solution(
                problem=t.description,
                solution=t.result.code or "",
                metadata={"score": eval_result.score},
            )
