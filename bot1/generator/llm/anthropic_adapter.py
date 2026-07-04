"""Anthropic Claude adapter."""
from __future__ import annotations

import anthropic

from .base import (
    BaseLLMAdapter,
    LLMAuthError,
    LLMConnectionError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponseError,
)


class AnthropicAdapter(BaseLLMAdapter):
    """LLM adapter for the Anthropic Messages API (Claude)."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        *,
        max_retries: int = 3,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _call_api(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        effective_system = (
            self._append_json_constraint(system) if force_json else system
        )

        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": api_messages,
        }
        if effective_system:
            kwargs["system"] = effective_system

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(f"Anthropic auth failed: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(f"Anthropic rate limit: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMConnectionError(f"Anthropic connection error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMResponseError(f"Anthropic API error ({exc.status_code}): {exc}") from exc

        if not response.content:
            raise LLMResponseError("Anthropic returned empty content.")
        return response.content[0].text
