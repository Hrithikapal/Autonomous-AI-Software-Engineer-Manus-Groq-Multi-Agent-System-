"""
LLM-as-judge evaluator.
Scores code output on correctness, quality, and completeness.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.core import kimi_client
from app.models.agent import EvaluationResult

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """You are a senior software engineer acting as a code reviewer.
Evaluate the provided code implementation against the task requirements.

Score each dimension from 0 to 10:
1. correctness   — does it solve the task?
2. quality       — clean, idiomatic, no obvious bugs?
3. completeness  — are all requirements addressed?

Respond ONLY with valid JSON (no markdown):
{
  "correctness": <0-10>,
  "quality": <0-10>,
  "completeness": <0-10>,
  "overall": <0-10>,
  "passed": <true|false>,
  "feedback": "<one paragraph>",
  "suggestions": ["<suggestion 1>", "<suggestion 2>"]
}
"""


async def evaluate(
    task: str,
    code: str,
    files: dict[str, Any] | None = None,
    test_pass_rate: float = 0.0,
    latency_ms: float = 0.0,
) -> EvaluationResult:
    code_context = code
    if files:
        code_context = "\n\n".join(f"# {k}\n{v}" for k, v in list(files.items())[:6])

    prompt = (
        f"Task: {task}\n\n"
        f"Implementation:\n```\n{code_context[:6000]}\n```\n\n"
        "Evaluate and return the JSON."
    )
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    resp = await kimi_client.chat(messages, temperature=0.1)
    raw = resp["content"].strip()

    try:
        data = _parse_json(raw)
        return EvaluationResult(
            score=float(data.get("overall", 5)),
            passed=bool(data.get("passed", False)),
            correctness_score=float(data.get("correctness", 5)),
            quality_score=float(data.get("quality", 5)),
            test_pass_rate=test_pass_rate,
            latency_ms=latency_ms,
            feedback=data.get("feedback", ""),
            suggestions=data.get("suggestions", []),
        )
    except Exception as exc:
        logger.warning("Evaluator parse error: %s", exc)
        return EvaluationResult(
            score=5.0,
            passed=False,
            correctness_score=5.0,
            quality_score=5.0,
            test_pass_rate=test_pass_rate,
            latency_ms=latency_ms,
            feedback="Could not parse evaluation response.",
        )


def _parse_json(text: str) -> dict[str, Any]:
    # Strip markdown fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    import json
    return json.loads(text)
