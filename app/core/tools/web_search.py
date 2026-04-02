"""
Tool: web search via DuckDuckGo (no API key required).
Falls back to returning an empty list on error so the agent can continue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Return a list of {title, url, snippet} dicts."""
    try:
        from duckduckgo_search import DDGS

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(query, max_results=max_results)),
        )
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        ]
    except Exception as exc:
        logger.warning("web_search failed: %s", exc)
        return []


def format_search_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**\n   {r['url']}\n   {r['snippet']}")
    return "\n\n".join(lines)
