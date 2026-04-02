"""
Async Kimi / Moonshot API client.
OpenAI-compatible — streams, tool calls, and plain completions all supported.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

import httpx
from openai import AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(
        api_key=s.kimi_api_key,
        base_url=s.kimi_base_url,
        timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5),
        max_retries=0,  # tenacity handles retries
    )


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


# ---------------------------------------------------------------------------
# Core completion helpers
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, RateLimitError)),
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    reraise=True,
)
async def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    model: str | None = None,
) -> dict[str, Any]:
    """Single-turn chat completion. Returns the full response message dict."""
    s = get_settings()
    kwargs: dict[str, Any] = dict(
        model=model or s.kimi_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = await get_client().chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    return {
        "role": msg.role,
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in (msg.tool_calls or [])
        ],
        "finish_reason": resp.choices[0].finish_reason,
        "usage": {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
        },
    }


async def stream_chat(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Streaming chat — yields text deltas."""
    s = get_settings()
    stream = await get_client().chat.completions.create(
        model=model or s.kimi_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def simple_prompt(prompt: str, system: str = "", **kwargs) -> str:
    """Convenience wrapper for simple one-shot prompts."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    result = await chat(messages, **kwargs)
    return result["content"]
