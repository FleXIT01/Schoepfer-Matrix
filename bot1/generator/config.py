from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


# --- LLM Provider ---
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "")  # empty = use provider default
LLM_API_BASE: str = os.environ.get("LLM_API_BASE", "")

# --- API Keys ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# --- Output ---
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "output"))
MAX_FOLLOWUP_QUESTIONS: int = _env_int("MAX_FOLLOWUP_QUESTIONS", 5)

# --- LLM Temperatures (internal) ---
LLM_TEMPERATURE_EXTRACT: float = 0.1
LLM_TEMPERATURE_FOLLOWUP: float = 0.4
LLM_TEMPERATURE_GENERATE: float = 0.3
LLM_MAX_TOKENS: int = 4096

# --- Agent-Build-System ---
AGENT_MAX_FIX_ATTEMPTS: int = _env_int("AGENT_MAX_FIX_ATTEMPTS", 4)   # pro Tool/Datei
AGENT_MAX_GLOBAL_ITERS: int = _env_int("AGENT_MAX_GLOBAL_ITERS", 3)   # Projekt-Reparaturrunden
SANDBOX_TIMEOUT: float = float(os.environ.get("SANDBOX_TIMEOUT", "30"))
AGENT_FINAL_REAL_RUN: bool = os.environ.get("AGENT_FINAL_REAL_RUN", "1") not in ("0", "false", "False", "")


def get_api_key_for_provider(provider: str) -> str:
    """Return the appropriate API key for the given provider."""
    provider = provider.strip().lower()
    if provider == "anthropic":
        return ANTHROPIC_API_KEY
    if provider == "openai":
        return OPENAI_API_KEY
    if provider in ("openai-compat", "openai_compat", "custom"):
        return OPENAI_API_KEY or ANTHROPIC_API_KEY or ""
    # ollama, lmstudio don't need keys
    return ""
