"""LLM adapter layer — provider-agnostic interface.

Quick start::

    from generator.llm import create_llm_adapter

    llm = create_llm_adapter("anthropic", api_key="sk-...", model="claude-sonnet-4-6")
    llm = create_llm_adapter("ollama", model="llama3.1")
"""
from .base import (
    BaseLLMAdapter,
    LLMAdapter,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponseError,
)
from .provider_factory import create_llm_adapter

__all__ = [
    # Protocol + ABC
    "LLMAdapter",
    "BaseLLMAdapter",
    "LLMMessage",
    # Exceptions
    "LLMError",
    "LLMAuthError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMResponseError",
    # Factory
    "create_llm_adapter",
]
