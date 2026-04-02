"""
Orchestrator — Manus execution engine.

Upgrades over v1:
- Parallel step execution: independent research steps run concurrently
- ReAct trace emission: streams Thought→Action→Observation to UI
- Token budget tracking per task
- Code diff generation when debug agent fixes code
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import clear_token_usage, get_token_usage
from app.core.rag.pipeline import get_pipeline
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
from app.models.task import (
    AgentType, PlanStep, StepStatus, Task, TaskEvent, TaskResult, TaskStatus,
)

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """You are Manus, an elite AI software engineering orchestrator.
Given a task, produce a concise execution plan as a JSON array of steps.

Each step must have:
- "order": int (1-based)
- "description": str (what to do)
- "agent": one of ["research", "coding", "test"]
- "parallel_group": int (steps with the same group number can run in parallel; use null if sequential)

Rules:
- Start with 1 research step (or 2 parallel research steps for complex tasks).
- coding always follows research.
- test always follows coding.
- debug is inserted automatically — do NOT include it.
- Keep the plan to ≤ 6 steps.
- Return ONLY valid JSON array, no markdown, no explanation.
"""

IMPROVER_SYSTEM = """You are a senior engineer reviewing code output.
The evaluation score is below threshold. Suggest specific, actionable improvements.
Be brief — 3-5 bullet points max.
"""


class Orchestrator:
    def __init__(self, task: Task):
        self.task = task
        self.s = get_settings()
        self._research_result: str = ""
        self._rag_context: str = ""
        clear_token_usage(task.id)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> AsyncIterator[TaskEvent]:
        start_ms = time.monotonic() * 1000
        t = self.task

        try:
            t.status = TaskStatus.PLANNING
            async for ev in self._plan():
                yield ev

            t.status = TaskStatus.IN_PROGRESS
            async for ev in self._execute_plan():
                yield ev

            t.status = TaskStatus.EVALUATING
            async for ev in self._evaluate():
                yield ev

            t.status = TaskStatus.COMPLETED
            t.latency_ms = time.monotonic() * 1000 - start_ms
            t.total_tokens = get_token_usage(t.id)
            t.touch()
            yield TaskEvent(event="task_done", task_id=t.id, data=t.model_dump(mode="json"))

        except Exception as exc:
            logger.exception("Orchestrator error task=%s", t.id)
            t.status = TaskStatus.FAILED
            t.error = str(exc)
            t.total_tokens = get_token_usage(t.id)
            t.touch()
            yield TaskEvent(event="task_failed", task_id=t.id, data={"error": str(exc)})

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan(self) -> AsyncIterator[TaskEvent]:
        t = self.task

        # Pull RAG context from uploaded files/URLs if session_id provided
        if t.session_id:
            try:
                pipeline = get_pipeline(t.session_id)
                self._rag_context = await pipeline.retrieve(t.description, n=5)
                if self._rag_context:
                    yield TaskEvent(
                        event="rag_context_loaded",
                        task_id=t.id,
                        data={"sources": pipeline.sources(), "chars": len(self._rag_context)},
                    )
            except Exception as exc:
                logger.warning("RAG context load failed: %s", exc)

        memory_ctx = await recall_as_context(t.description, n=2)

        yield TaskEvent(
            event="agent_thought",
            task_id=t.id,
            data={
                "agent": "manus",
                "thought": f"Analysing task: '{t.description[:100]}'. Determining optimal agent pipeline.",
                "action": "Generating execution plan with parallel steps where possible",
                "observation": "Will use ReAct loop: Research → Code → Test, with parallel research if needed",
            },
        )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM + (f"\n\n{memory_ctx}" if memory_ctx else "")},
            {"role": "user", "content": t.description},
        ]
        resp = await kimi_client.chat(messages, temperature=0.1)
        raw = resp["content"].strip()

        try:
            steps_data = json.loads(raw)
        except json.JSONDecodeError:
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
    # Execution — with parallel group support
    # ------------------------------------------------------------------

    async def _execute_plan(self) -> AsyncIterator[TaskEvent]:
        t = self.task
        coding_result = None
        files: dict[str, str] = {}

        # Group consecutive research steps for parallel execution
        groups = _group_steps(t.plan)

        for group in groups:
            if len(group) == 1:
                async for ev in self._run_single_step(group[0], files):
                    yield ev
                    # Capture results
                if group[0].status == StepStatus.COMPLETED:
                    result = getattr(self, f"_last_{group[0].agent.value}", None)
                    if result and group[0].agent == AgentType.RESEARCH:
                        self._research_result = result.output
                    elif result and group[0].agent == AgentType.CODING:
                        coding_result = result
                        files = result.files
            else:
                # Parallel execution
                yield TaskEvent(
                    event="agent_thought",
                    task_id=t.id,
                    data={
                        "agent": "manus",
                        "thought": f"Steps {[s.order for s in group]} are independent — running in parallel",
                        "action": f"asyncio.gather({len(group)} tasks)",
                        "observation": "Parallel execution reduces total latency",
                    },
                )
                tasks = [self._run_step_capture(step, files) for step in group]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for step, result in zip(group, results):
                    if isinstance(result, Exception):
                        step.status = StepStatus.FAILED
                        step.error = str(result)
                        yield TaskEvent(event="step_error", task_id=t.id, data={"step": step.model_dump(), "error": str(result)})
                    else:
                        step.status = StepStatus.COMPLETED
                        step.output = result.output[:1000] if result else ""
                        if step.agent == AgentType.RESEARCH and result:
                            self._research_result += "\n\n" + result.output
                        yield TaskEvent(event="step_done", task_id=t.id, data={"step": step.model_dump()})

                        # Emit ReAct steps from the agent
                        if hasattr(result, '_agent_react') and result._agent_react:
                            for react in result._agent_react:
                                yield TaskEvent(event="agent_thought", task_id=t.id, data=react)

        # Run coding + test sequentially after all research
        for step in t.plan:
            if step.agent in (AgentType.CODING, AgentType.TEST) and step.status == StepStatus.PENDING:
                async for ev in self._run_single_step(step, files):
                    yield ev

                if step.status == StepStatus.COMPLETED:
                    if step.agent == AgentType.CODING:
                        result = getattr(self, "_last_coding", None)
                        if result:
                            coding_result = result
                            files = result.files
                            # Self-debug loop
                            if result.code:
                                exec_result = await run_code(result.code)
                                if not exec_result.success:
                                    t.status = TaskStatus.DEBUGGING
                                    t.touch()
                                    yield TaskEvent(event="debug_start", task_id=t.id, data={"error": exec_result.stderr[:500]})

                                    original_code = result.code
                                    debug_agent = DebugAgent(t.id)
                                    debug_result = await debug_agent.run(
                                        t.description,
                                        code=result.code,
                                        error=exec_result.stderr,
                                        files=files,
                                    )

                                    # Emit diff
                                    if debug_result.success and debug_result.code:
                                        diff = _make_diff(original_code, debug_result.code)
                                        yield TaskEvent(
                                            event="code_diff",
                                            task_id=t.id,
                                            data={
                                                "diff": diff,
                                                "attempts": debug_result.metadata.get("attempts", 1),
                                            },
                                        )
                                        coding_result = debug_result
                                        files = debug_result.files

                                    t.status = TaskStatus.IN_PROGRESS

        all_files = await collect_workspace(t.id)
        primary_code = (coding_result.code if coding_result else "") or ""
        t.result = TaskResult(files=all_files, code=primary_code)

    async def _run_single_step(self, step: PlanStep, files: dict[str, str]) -> AsyncIterator[TaskEvent]:
        t = self.task
        step.status = StepStatus.IN_PROGRESS
        t.touch()
        yield TaskEvent(event="step_start", task_id=t.id, data={"step": step.model_dump()})

        start = time.monotonic()
        try:
            result = await self._run_step(step, files)
            step.execution_time_ms = (time.monotonic() - start) * 1000
            step.output = result.output[:1000] if result else ""
            step.status = StepStatus.COMPLETED

            # Emit ReAct traces
            if hasattr(result, "metadata") and result.metadata.get("react_steps"):
                for react in result.metadata["react_steps"]:
                    yield TaskEvent(event="agent_thought", task_id=t.id, data=react)

            # Store last result per agent type
            setattr(self, f"_last_{step.agent.value}", result)

        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            logger.exception("Step failed task=%s step=%s", t.id, step.id)
            yield TaskEvent(event="step_error", task_id=t.id, data={"step": step.model_dump(), "error": str(exc)})
            return

        t.touch()
        yield TaskEvent(event="step_done", task_id=t.id, data={"step": step.model_dump()})

    async def _run_step_capture(self, step: PlanStep, files: dict[str, str]):
        return await self._run_step(step, files)

    async def _run_step(self, step: PlanStep, files: dict[str, str]) -> Any:
        t = self.task
        if step.agent == AgentType.RESEARCH:
            agent = ResearchAgent(t.id)
            result = await agent.run(t.description)
            result.metadata["react_steps"] = agent.get_react_steps()
            return result

        elif step.agent == AgentType.CODING:
            agent = CodingAgent(t.id)
            combined_context = "\n\n".join(filter(None, [self._rag_context, self._research_result]))
            result = await agent.run(t.description, research_context=combined_context)
            result.metadata["react_steps"] = agent.get_react_steps()
            return result

        elif step.agent == AgentType.TEST:
            agent = TestAgent(t.id)
            primary = next((v for k, v in files.items() if k.endswith(".py") and "test" not in k), "")
            result = await agent.run(t.description, code=primary, files=files)
            result.metadata["react_steps"] = agent.get_react_steps()
            return result

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

        yield TaskEvent(
            event="agent_thought",
            task_id=t.id,
            data={
                "agent": "manus",
                "thought": "All steps complete. Running LLM-as-judge evaluation.",
                "action": "Score correctness, quality, completeness on 0–10 scale",
                "observation": "Will trigger improvement loop if score < 6.0",
            },
        )

        eval_result = await evaluate(task=t.description, code=t.result.code or "", files=t.result.files)
        t.result.evaluation = eval_result.model_dump()
        t.touch()

        yield TaskEvent(
            event="evaluation_done",
            task_id=t.id,
            data={
                "evaluation": eval_result.model_dump(),
                "tokens_used": get_token_usage(t.id),
            },
        )

        if eval_result.score < 6.0 and t.result.code:
            yield TaskEvent(event="improving", task_id=t.id, data={"score": eval_result.score})

            messages = [
                {"role": "system", "content": IMPROVER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Task: {t.description}\nScore: {eval_result.score}/10\n"
                        f"Feedback: {eval_result.feedback}\nList improvements."
                    ),
                },
            ]
            resp = await kimi_client.chat(messages, temperature=0.3)
            suggestions = resp["content"]

            coding_agent = CodingAgent(t.id)
            improved = await coding_agent.run(
                f"{t.description}\n\nIMPROVEMENTS REQUIRED:\n{suggestions}",
                research_context=self._research_result,
            )
            if improved.success:
                t.result.code = improved.code
                t.result.files.update(improved.files)
                eval2 = await evaluate(t.description, code=improved.code or "", files=improved.files)
                t.result.evaluation = eval2.model_dump()
                yield TaskEvent(
                    event="evaluation_done",
                    task_id=t.id,
                    data={"evaluation": eval2.model_dump(), "improved": True},
                )

        if eval_result.score >= 7.0:
            await remember_solution(
                problem=t.description,
                solution=t.result.code or "",
                metadata={"score": eval_result.score},
            )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _group_steps(steps: list[PlanStep]) -> list[list[PlanStep]]:
    """Group consecutive research steps for parallel execution; rest are solo."""
    groups: list[list[PlanStep]] = []
    i = 0
    while i < len(steps):
        step = steps[i]
        if step.agent == AgentType.RESEARCH:
            group = [step]
            while i + 1 < len(steps) and steps[i + 1].agent == AgentType.RESEARCH:
                i += 1
                group.append(steps[i])
            groups.append(group)
        else:
            groups.append([step])
        i += 1
    return groups


def _make_diff(before: str, after: str) -> str:
    """Generate a unified diff between two code strings."""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="before_fix.py",
        tofile="after_fix.py",
        n=3,
    )
    return "".join(list(diff)[:80])  # cap at 80 lines
