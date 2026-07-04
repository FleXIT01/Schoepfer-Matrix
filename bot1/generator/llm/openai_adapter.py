"""OpenAI ChatCompletion adapter (GPT-4o, GPT-4, o1, etc.)."""
from __future__ import annotations

import openai

from .base import (
    BaseLLMAdapter,
    LLMAuthError,
    LLMConnectionError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponseError,
)


class OpenAIAdapter(BaseLLMAdapter):
    """LLM adapter for the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        *,
        max_retries: int = 3,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def _call_api(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        api_messages: list[dict] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for m in messages:
            api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMAuthError(f"OpenAI auth failed: {exc}") from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(f"OpenAI rate limit: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMConnectionError(f"OpenAI connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            raise LLMResponseError(f"OpenAI API error ({exc.status_code}): {exc}") from exc

        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message or not choice.message.content:
            raise LLMResponseError("OpenAI returned empty content.")
        return choice.message.content
