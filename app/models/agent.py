from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class AgentResult(BaseModel):
    success: bool
    output: str
    error: Optional[str] = None
    code: Optional[str] = None
    files: dict[str, str] = {}
    metadata: dict[str, Any] = {}


class CodeExecution(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    execution_time_ms: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class EvaluationResult(BaseModel):
    score: float                 # 0.0 – 10.0
    passed: bool
    correctness_score: float
    quality_score: float
    test_pass_rate: float
    latency_ms: float
    feedback: str
    suggestions: list[str] = []
