"""Generic OpenAI-compatible adapter.

Works with any provider that exposes an OpenAI-compatible
``/v1/chat/completions`` endpoint, e.g.:
  - LM Studio    (http://localhost:1234/v1)
  - vLLM         (http://localhost:8000/v1)
  - LocalAI      (http://localhost:8080/v1)
  - Together AI  (https://api.together.xyz/v1)
  - Groq         (https://api.groq.com/openai/v1)
  - Fireworks AI (https://api.fireworks.ai/inference/v1)
"""
from __future__ import annotations

import logging

import openai

from .base import (
    BaseLLMAdapter,
    LLMAuthError,
    LLMConnectionError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(BaseLLMAdapter):
    """LLM adapter for any OpenAI-compatible API endpoint.

    Parameters
    ----------
    base_url:
        Full base URL *including* ``/v1`` if needed.
        Examples: ``http://localhost:1234/v1``, ``https://api.groq.com/openai/v1``
    api_key:
        API key — use ``"no-key"`` or ``"lm-studio"`` for local servers
        that don't require auth.
    model:
        Model name as the server knows it.
    supports_json_mode:
        If ``True``, ``response_format={"type": "json_object"}`` is sent
        for ``chat_structured()`` calls.  Set to ``False`` for servers
        that don't support it — a system-prompt JSON constraint will be
        used as fallback.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "no-key",
        *,
        supports_json_mode: bool = False,
        max_retries: int = 3,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._supports_json_mode = supports_json_mode

    def _call_api(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        effective_system = system
        if force_json and not self._supports_json_mode:
            effective_system = self._append_json_constraint(system)

        api_messages: list[dict] = []
        if effective_system:
            api_messages.append({"role": "system", "content": effective_system})
        for m in messages:
            api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if force_json and self._supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMAuthError(f"Auth failed ({self._client.base_url}): {exc}") from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(f"Rate limit ({self._client.base_url}): {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMConnectionError(
                f"Connection error ({self._client.base_url}): {exc}"
            ) from exc
        except openai.APIStatusError as exc:
            raise LLMResponseError(
                f"API error ({self._client.base_url}, {exc.status_code}): {exc}"
            ) from exc

        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message or not choice.message.content:
            raise LLMResponseError("Server returned empty content.")
        return choice.message.content
