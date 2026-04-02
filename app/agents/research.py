"""
Research Agent — gathers context, docs, and best practices before coding.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.core.tools.web_search import format_search_results, web_search
from app.models.agent import AgentResult

logger = logging.getLogger(__name__)

SYSTEM = """You are a Research Agent in an autonomous software engineering system.
Your job:
1. Understand the technical requirements of a task.
2. Search the web for relevant documentation, libraries, and best practices.
3. Summarise findings concisely for the Coding Agent.

Always prefer official documentation and reputable sources.
Output a structured research summary with:
- Key libraries / frameworks to use
- Relevant API documentation snippets
- Recommended patterns
- Potential pitfalls
"""


class ResearchAgent(BaseAgent):
    name = "research"
    system_prompt = SYSTEM

    async def run(self, input_text: str, **kwargs) -> AgentResult:
        logger.info("[ResearchAgent] task=%s query=%s", self.task_id, input_text[:80])

        # 1. Generate targeted search queries
        plan_resp = await self._chat(
            f"Generate 3 focused search queries to research this task:\n\n{input_text}\n\n"
            "Return ONLY the queries, one per line.",
            inject_memory=False,
            temperature=0.1,
        )
        queries = [q.strip() for q in plan_resp["content"].splitlines() if q.strip()][:3]

        # 2. Execute searches
        all_results: list[str] = []
        for q in queries:
            results = await web_search(q, max_results=4)
            if results:
                all_results.append(f"### Search: {q}\n{format_search_results(results)}")

        search_context = "\n\n".join(all_results) if all_results else "No web results found."

        # 3. Synthesise
        synthesis = await self._chat(
            f"Task: {input_text}\n\nSearch Results:\n{search_context}\n\n"
            "Produce a structured research summary for the Coding Agent.",
            inject_memory=True,
        )

        return AgentResult(
            success=True,
            output=synthesis["content"],
            metadata={"queries": queries, "sources": len(all_results)},
        )
