"""Deterministic mock adapter for tests. Returns canned responses."""
from __future__ import annotations

import json

from .base import LLMMessage


class MockAdapter:
    """Deterministic adapter for tests. Returns canned responses."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_count = 0

    def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        if self._responses:
            idx = min(self._call_count, len(self._responses) - 1)
            self._call_count += 1
            return self._responses[idx]
        return "Mock-Antwort"

    def chat_structured(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        result = self.chat(messages, system, temperature, max_tokens)
        # Ensure the mock always returns valid JSON
        try:
            json.loads(result)
            return result
        except json.JSONDecodeError:
            return "{}"
