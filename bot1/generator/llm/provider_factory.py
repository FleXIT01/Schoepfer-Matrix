"""Factory for creating LLM adapters from a provider string.

Usage::

    from generator.llm.provider_factory import create_llm_adapter

    llm = create_llm_adapter("anthropic", api_key="sk-...", model="claude-sonnet-4-6")
    llm = create_llm_adapter("openai", api_key="sk-...", model="gpt-4o")
    llm = create_llm_adapter("ollama", model="llama3.1")
    llm = create_llm_adapter("lmstudio", model="local-model")
    llm = create_llm_adapter("openai-compat", base_url="https://api.groq.com/openai/v1",
                              api_key="gsk-...", model="llama-3.1-70b-versatile")
"""
from __future__ import annotations

from .base import LLMAdapter, LLMError


def create_llm_adapter(
    provider: str,
    *,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    supports_json_mode: bool = False,
    max_retries: int = 3,
) -> LLMAdapter:
    """Create an LLM adapter for the given provider.

    Parameters
    ----------
    provider:
        One of: ``anthropic``, ``openai``, ``ollama``, ``lmstudio``,
        ``openai-compat``.
    api_key:
        API key.  Not required for ``ollama`` and ``lmstudio``.
    model:
        Model identifier.  Each provider has a sensible default.
    base_url:
        Custom endpoint URL.  Required for ``openai-compat``,
        optional for ``ollama`` and ``lmstudio``.
    supports_json_mode:
        Whether the ``openai-compat`` endpoint supports
        ``response_format={"type": "json_object"}``.
    max_retries:
        Max retry attempts for transient errors.

    Returns
    -------
    LLMAdapter
        An adapter instance ready to use.

    Raises
    ------
    LLMError
        If configuration is invalid (missing key, unknown provider, etc.).
    """
    provider = provider.strip().lower()

    if provider == "anthropic":
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY fehlt. "
                "Bitte in .env setzen oder als Parameter übergeben."
            )
        from .anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            api_key=api_key,
            model=model or "claude-sonnet-4-6",
            max_retries=max_retries,
        )

    if provider == "openai":
        if not api_key:
            raise LLMError(
                "OPENAI_API_KEY fehlt. "
                "Bitte in .env setzen oder als Parameter übergeben."
            )
        from .openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            api_key=api_key,
            model=model or "gpt-4o",
            max_retries=max_retries,
        )

    if provider == "ollama":
        from .ollama_adapter import OllamaAdapter

        return OllamaAdapter(
            model=model or "llama3.1",
            base_url=base_url or "http://localhost:11434",
            max_retries=max_retries,
        )

    if provider == "lmstudio":
        from .openai_compat_adapter import OpenAICompatAdapter

        return OpenAICompatAdapter(
            base_url=base_url or "http://localhost:1234/v1",
            model=model or "local-model",
            api_key=api_key or "lm-studio",
            supports_json_mode=supports_json_mode,
            max_retries=max_retries,
        )

    if provider in ("openai-compat", "openai_compat", "custom"):
        if not base_url:
            raise LLMError(
                "LLM_API_BASE fehlt für openai-compat Provider. "
                "Bitte in .env setzen oder als Parameter übergeben."
            )
        from .openai_compat_adapter import OpenAICompatAdapter

        return OpenAICompatAdapter(
            base_url=base_url,
            model=model or "default",
            api_key=api_key or "no-key",
            supports_json_mode=supports_json_mode,
            max_retries=max_retries,
        )

    raise LLMError(
        f"Unbekannter LLM-Provider: '{provider}'. "
        f"Unterstützt: anthropic, openai, ollama, lmstudio, openai-compat"
    )
