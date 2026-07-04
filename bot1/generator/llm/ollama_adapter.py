"""Native Ollama adapter via REST API.

Uses ``httpx`` directly — no external SDK dependency required.
Default endpoint: ``http://localhost:11434``
"""
from __future__ import annotations

import json
import logging

import httpx

from .base import (
    BaseLLMAdapter,
    LLMConnectionError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaAdapter(BaseLLMAdapter):
    """LLM adapter for a local Ollama instance.

    Parameters
    ----------
    model:
        Ollama model tag, e.g. ``"llama3.1"``, ``"mistral"``, ``"gemma2"``.
    base_url:
        Ollama server URL.  Defaults to ``http://localhost:11434``.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = _DEFAULT_BASE_URL,
        *,
        max_retries: int = 3,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _call_api(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        effective_system = system
        if force_json:
            effective_system = self._append_json_constraint(system)

        api_messages: list[dict] = []
        if effective_system:
            api_messages.append({"role": "system", "content": effective_system})
        for m in messages:
            api_messages.append({"role": m.role, "content": m.content})

        payload: dict = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if force_json:
            payload["format"] = "json"

        url = f"{self._base_url}/api/chat"
        try:
            resp = httpx.post(url, json=payload, timeout=self._timeout)
        except httpx.ConnectError as exc:
            raise LLMConnectionError(
                f"Ollama nicht erreichbar ({self._base_url}). "
                f"Läuft 'ollama serve'? Fehler: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMConnectionError(
                f"Ollama Timeout nach {self._timeout}s: {exc}"
            ) from exc

        if resp.status_code == 429:
            raise LLMRateLimitError("Ollama rate limit reached.")
        if resp.status_code != 200:
            raise LLMResponseError(
                f"Ollama error (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseError(f"Ollama invalid JSON response: {exc}") from exc

        content = data.get("message", {}).get("content", "")
        if not content:
            raise LLMResponseError("Ollama returned empty content.")
        return content


def get_available_models(base_url: str = _DEFAULT_BASE_URL, timeout: float = 3.0) -> list[str]:
    """Fetch available models from a running Ollama instance."""
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        resp = httpx.get(url, timeout=timeout)
        if resp.status_code == 200:
            return [m.get("name") for m in resp.json().get("models", []) if "name" in m]
    except httpx.RequestError:
        pass
    return []
