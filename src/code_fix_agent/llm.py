"""LLM client wrappers.

Real Anthropic client for benchmarks; MockLLM that scripts a sequence of
responses for tests. Both expose `respond(...)` returning a tuple of
(content_blocks, stop_reason, usage).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMClient(Protocol):
    def respond(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> tuple[list[dict[str, Any]], str, dict[str, int]]: ...


class AnthropicLLM:
    """Wraps anthropic.Anthropic. Returns (content, stop_reason, usage)."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: str | None = None):
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("install anthropic to use AnthropicLLM") from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set; use MockLLM in tests")
        self._client = Anthropic(api_key=key)
        self.model = model

    def respond(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> tuple[list[dict[str, Any]], str, dict[str, int]]:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.0,
            system=system,
            messages=messages,
            tools=tools,
        )
        content_blocks: list[dict[str, Any]] = []
        for block in resp.content:
            if hasattr(block, "model_dump"):
                content_blocks.append(block.model_dump())
            else:
                content_blocks.append(dict(block))
        usage = (
            resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
        )
        return content_blocks, resp.stop_reason or "end_turn", usage


@dataclass
class MockLLM:
    """Scripted LLM stub.

    Pass a list of response payloads. Each payload is a tuple of
    (content_blocks, stop_reason). The mock cycles through them on
    successive calls. After the script is exhausted, all subsequent calls
    return a final text block ("done") with stop_reason=end_turn.
    """

    script: list[tuple[list[dict[str, Any]], str]] = field(default_factory=list)
    call_count: int = 0
    last_messages: list[list[dict[str, Any]]] = field(default_factory=list)

    def respond(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> tuple[list[dict[str, Any]], str, dict[str, int]]:
        idx = self.call_count
        self.call_count += 1
        self.last_messages.append(list(messages))

        if idx < len(self.script):
            content, stop_reason = self.script[idx]
        else:
            content = [{"type": "text", "text": "done"}]
            stop_reason = "end_turn"

        # Stub usage so tests can assert call count > 0.
        usage = {"input_tokens": 10, "output_tokens": 5}
        return content, stop_reason, usage
