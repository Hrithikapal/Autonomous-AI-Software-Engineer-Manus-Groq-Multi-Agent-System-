from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    DEBUGGING = "debugging"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentType(str, Enum):
    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    CODING = "coding"
    DEBUG = "debug"
    TEST = "test"
    EVALUATION = "evaluation"


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    order: int
    description: str
    agent: AgentType
    status: StepStatus = StepStatus.PENDING
    input: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    execution_time_ms: Optional[float] = None


class TaskCreate(BaseModel):
    description: str = Field(..., min_length=5, max_length=4000)
    context: Optional[str] = None


class TaskResult(BaseModel):
    files: dict[str, str] = {}           # filename -> content
    code: Optional[str] = None
    explanation: Optional[str] = None
    test_results: Optional[dict[str, Any]] = None
    evaluation: Optional[dict[str, Any]] = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    context: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    plan: list[PlanStep] = []
    result: Optional[TaskResult] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    total_tokens: int = 0
    latency_ms: Optional[float] = None

    def model_post_init(self, __context: Any) -> None:
        pass

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()


class TaskEvent(BaseModel):
    """SSE event emitted during task execution."""
    event: str          # plan_ready | step_start | step_done | step_error | task_done | task_failed
    task_id: str
    data: dict[str, Any] = {}
