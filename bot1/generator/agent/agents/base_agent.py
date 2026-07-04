"""Gemeinsame Basis für die LLM-Agenten: JSON- und Code-Abruf mit Retry.

Erweitert um optionalen Zugriff auf die ServiceRegistry (AI-OS),
damit Agenten nicht nur lokale LLM-Calls machen, sondern das gesamte
Netzwerk aus 36+ Repositories und Tools nutzen können.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ...interview.extractor import parse_json_robust
from ...llm.base import LLMError, LLMMessage

if TYPE_CHECKING:
    from ..services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


def extract_code(raw: str) -> str:
    """Holt Python-Code aus einer Modellantwort möglichst robust."""
    if not raw:
        return ""
    # 1) Fenced block (mit oder ohne Sprach-Tag, auch ohne Zeilenumbruch danach)
    m = re.search(r"```[a-zA-Z0-9_+-]*[ \t]*\r?\n?(.*?)```", raw, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip("\n").rstrip()
    cleaned = raw.strip().strip("`").strip()
    # 2) Beginnt direkt mit Code
    if cleaned.startswith(("def ", "import ", "from ", "class ", "async def ")):
        return cleaned
    # 3) Code beginnt irgendwo nach Prosa — ab erster def/import-Zeile schneiden
    m2 = re.search(r"(?m)^[ \t]*(?:async def |def |import |from )", cleaned)
    if m2:
        return cleaned[m2.start():].strip()
    return ""


class BaseAgent:
    def __init__(self, llm, *, registry: ServiceRegistry | None = None) -> None:
        self._llm = llm
        self._registry = registry

    @property
    def has_registry(self) -> bool:
        """Prüft, ob die AI-OS Service-Registry verfügbar ist."""
        return self._registry is not None

    @property
    def registry(self) -> ServiceRegistry | None:
        """Zugriff auf die zentrale Service-Registry (ClawHub)."""
        return self._registry

    def ask_json(self, system: str, user: str, *, max_attempts: int = 3,
                 temperature: float = 0.1) -> dict:
        messages = [LLMMessage(role="user", content=user)]
        for attempt in range(1, max_attempts + 1):
            try:
                raw = self._llm.chat_structured(
                    messages=messages, system=system, temperature=temperature
                )
            except LLMError as exc:
                logger.warning("Agent JSON-Call fehlgeschlagen (%d/%d): %s",
                               attempt, max_attempts, exc)
                if attempt == max_attempts:
                    return {}
                continue
            data = parse_json_robust(raw)
            if isinstance(data, dict) and data:
                return data
            messages.append(LLMMessage(role="assistant", content=raw))
            messages.append(LLMMessage(
                role="user",
                content="Das war kein gültiges JSON-Objekt. Antworte AUSSCHLIESSLICH mit dem JSON-Objekt.",
            ))
        return {}

    def ask_code(self, system: str, user: str, *, max_attempts: int = 3,
                 temperature: float = 0.2) -> str:
        messages = [LLMMessage(role="user", content=user)]
        for attempt in range(1, max_attempts + 1):
            try:
                raw = self._llm.chat(
                    messages=messages, system=system, temperature=temperature
                )
            except LLMError as exc:
                logger.warning("Agent Code-Call fehlgeschlagen (%d/%d): %s",
                               attempt, max_attempts, exc)
                if attempt == max_attempts:
                    return ""
                continue
            code = extract_code(raw)
            if code:
                return code
            messages.append(LLMMessage(role="assistant", content=raw))
            messages.append(LLMMessage(
                role="user",
                content="Gib NUR einen ```python Codeblock zurück, nichts sonst.",
            ))
        return ""
