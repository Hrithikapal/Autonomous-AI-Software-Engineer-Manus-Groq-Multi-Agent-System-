"""
Manus info endpoints — exposes the agent architecture publicly.
Great for portfolio demos.
"""
from fastapi import APIRouter

from app.agents.manus import Manus

router = APIRouter(prefix="/manus", tags=["manus"])


@router.get("/info")
async def manus_info():
    """Returns Manus architecture, available tools, and version."""
    return {
        "name": "Manus",
        "version": Manus.VERSION,
        "description": (
            "Manus is the orchestration brain. It plans tasks, delegates to "
            "specialist agents (Research, Coding, Debug, Test), runs the "
            "self-healing debug loop, and evaluates output quality using "
            "Kimi K2 as the reasoning engine."
        ),
        "reasoning_engine": "Groq (llama-3.1-8b-instant)",
        "architecture": {
            "flow": [
                "User Request",
                "Manus — dynamic planning via Kimi",
                "ResearchAgent — web research + doc lookup",
                "CodingAgent — production code generation",
                "DebugAgent — self-healing loop (up to 3 retries)",
                "TestAgent — pytest generation + execution",
                "Manus — LLM-as-judge evaluation",
                "Manus — improvement loop if score < 6/10",
                "Final Output + memory persistence",
            ],
        },
        "tools": Manus.available_tools(),
        "memory": "ChromaDB vector store — learns from past solutions",
        "execution": "Sandboxed Docker container",
        "evaluation": "LLM-as-judge (Kimi) scoring correctness, quality, completeness",
    }
