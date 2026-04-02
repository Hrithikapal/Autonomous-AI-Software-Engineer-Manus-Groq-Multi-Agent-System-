"""
Prometheus metrics for the agent system.
"""
from prometheus_client import Counter, Gauge, Histogram

TASK_COUNTER = Counter(
    "agent_tasks_total",
    "Total tasks processed",
    ["status"],
)

TASK_LATENCY = Histogram(
    "agent_task_duration_seconds",
    "Task end-to-end latency",
    buckets=[5, 15, 30, 60, 120, 300],
)

EVAL_SCORE = Histogram(
    "agent_evaluation_score",
    "LLM-as-judge score distribution",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

DEBUG_ATTEMPTS = Counter(
    "agent_debug_attempts_total",
    "Number of debug retries",
)

ACTIVE_TASKS = Gauge(
    "agent_active_tasks",
    "Currently running tasks",
)


def record_task_completed(latency_s: float, score: float) -> None:
    TASK_COUNTER.labels(status="completed").inc()
    TASK_LATENCY.observe(latency_s)
    EVAL_SCORE.observe(score)


def record_task_failed() -> None:
    TASK_COUNTER.labels(status="failed").inc()
