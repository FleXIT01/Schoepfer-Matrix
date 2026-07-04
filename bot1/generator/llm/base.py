"""LLM adapter base classes, protocols and error types."""
from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LLMMessage:
    role: str  # "user" | "assistant" | "system"
    content: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Base exception for all LLM adapter errors."""


class LLMConnectionError(LLMError):
    """Raised when the LLM service is unreachable."""


class LLMAuthError(LLMError):
    """Raised when the API key / credentials are invalid."""


class LLMRateLimitError(LLMError):
    """Raised when the provider returns a rate-limit (429) response."""


class LLMResponseError(LLMError):
    """Raised when the LLM returns an unparseable or empty response."""


# ---------------------------------------------------------------------------
# Protocol (for type-checking — remains backward-compatible)
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMAdapter(Protocol):
    def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str: ...

    def chat_structured(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Forces JSON output via constrained system prompt."""
        ...


# ---------------------------------------------------------------------------
# Abstract base with retry logic
# ---------------------------------------------------------------------------

_JSON_CONSTRAINT_DE = (
    "\n\nANTWORTE AUSSCHLIESSLICH MIT GÜLTIGEM JSON. "
    "Kein Erklärungstext, keine Markdown-Blöcke, keine Kommentare. "
    "Nur das JSON-Objekt selbst."
)

# Transient exception types that should trigger a retry.
_RETRYABLE = (LLMConnectionError, LLMRateLimitError)


class BaseLLMAdapter(abc.ABC):
    """Abstract base with built-in retry / back-off for transient errors.

    Subclasses only need to implement ``_call_api``.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    # -- public API (matches LLMAdapter Protocol) --------------------------

    def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        return self._call_with_retry(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            force_json=False,
        )

    def chat_structured(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        return self._call_with_retry(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            force_json=True,
        )

    # -- subclass hook -----------------------------------------------------

    @abc.abstractmethod
    def _call_api(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        """Perform one raw LLM call.  Must raise ``LLMError`` subclasses on failure."""

    # -- internal ----------------------------------------------------------

    def _call_with_retry(
        self,
        messages: list[LLMMessage],
        system: str | None,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._call_api(
                    messages=messages,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    force_json=force_json,
                )
                if not result or not result.strip():
                    raise LLMResponseError("LLM returned empty response.")
                return result
            except _RETRYABLE as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    self._max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
            except LLMError:
                raise  # non-retryable → propagate immediately
            except Exception as exc:
                raise LLMError(f"Unexpected error from LLM provider: {exc}") from exc

        # All retries exhausted
        raise LLMError(
            f"LLM call failed after {self._max_retries} attempts."
        ) from last_exc

    @staticmethod
    def _append_json_constraint(system: str | None) -> str:
        """Utility for adapters that rely on a system-prompt JSON constraint."""
        return (system or "") + _JSON_CONSTRAINT_DE
