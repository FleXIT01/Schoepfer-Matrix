"""OpenClaw Service-Bridge: Das Gehirn des AI-OS.

OpenClaw dient als zentrales API-Gateway mit Intent-Erkennung und
LLM-Proxy. OmegaAgent schickt jede Nutzeranfrage zuerst hierher.
OpenClaw klassifiziert den Intent und schlägt eine Routing-Strategie vor.

Fällt OpenClaw aus, übernimmt das LLM direkt (Graceful Degradation).

Lokaler Pfad: n:\\allinall\\openclaw-main
Tech-Stack: TypeScript/Node.js (pnpm workspace, Docker)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)

# OpenClaw Docker-Compose nutzt Port 18789 (Gateway)
OPENCLAW_PORT = 18789


def create_openclaw_config(repo_path: str = r"n:\allinall\openclaw-main") -> ServiceConfig:
    import sys as _sys
    from pathlib import Path as _Path
    # Pfad zur bridge (relativ zu diesem File)
    _bridge_path = _Path(__file__).resolve().parent / "openclaw_bridge.py"
    return ServiceConfig(
        name="openclaw",
        display_name="OpenClaw (Gateway & Brain)",
        port=OPENCLAW_PORT,
        # Starte die Python-Bridge mit korrektem Pfad
        start_command=(
            f"{_sys.executable} \"{_bridge_path}\" --port {OPENCLAW_PORT}"
        ),
        health_endpoint="/health",
        auto_start=False,  # start.py's _ensure_openclaw_bridge() übernimmt den Start
        scale_to_zero=False,  # Das Gehirn bleibt immer an
        capabilities=[
            "intent_routing", "gateway", "task_delegation",
            "skill_discovery", "plugin_management", "llm_proxy",
        ],
        tags=["core", "brain", "gateway"],
        repo_path=repo_path,
    )

# ─── Intent-Klassifizierungs-Prompt (wird an OpenClaw geschickt) ───────

_INTENT_CLASSIFY_SYSTEM = (
    "Du bist der zentrale Intent-Router des OmegaAgent-Betriebssystems. "
    "Analysiere die Nutzeranfrage und bestimme:\n"
    "1. Den primären Intent (research, science, build, task, review, deploy)\n"
    "2. Ob das Ziel zerlegt werden muss (1=simple, 5=komplex)\n"
    "3. Welche Sub-Agenten gebraucht werden\n\n"
    "Antworte AUSSCHLIESSLICH als JSON:\n"
    '{"intent": "research", "complexity": 2, "suggested_agents": ["research"],'
    '"plan_hint": "Kurze Beschreibung der optimalen Strategie"}\n'
    "Kein Text vor oder nach dem JSON."
)


class OpenClawService(HttpService):
    """Bridge zum OpenClaw API-Gateway — das zentrale Nervensystem.

    OpenClaw empfängt ALLE Anfragen zuerst. Es klassifiziert den Intent
    und gibt eine Routing-Strategie zurück. Der OmegaAgent nutzt diese
    Strategie für die Task-Zerlegung.

    Bei Ausfall von OpenClaw übernimmt das lokale LLM direkt.
    """

    def __init__(self, repo_path: str = r"n:\allinall\openclaw-main") -> None:
        config = create_openclaw_config(repo_path)
        super().__init__(config, timeout=180.0)

    def route_intent(self, user_message: str, context: dict | None = None) -> ServiceResult:
        """Klassifiziert eine Nutzeranfrage und schlägt Routing vor.

        Sendet die Anfrage an OpenClaw's Chat-Endpunkt mit einem
        Klassifizierungs-Prompt. OpenClaw antwortet mit JSON:

        {
            "intent": "research|science|build|task|review|deploy",
            "complexity": 1-5,
            "suggested_agents": ["research", "build"],
            "plan_hint": "Strategie-Beschreibung"
        }
        """
        return self.execute("classify", {
            "message": user_message,
            "context": context or {},
            "system": _INTENT_CLASSIFY_SYSTEM,
        })

    def chat(self, messages: list[dict], system: str = "",
             temperature: float = 0.3, max_tokens: int = 2048) -> ServiceResult:
        """Nutzt OpenClaw als LLM-Proxy (OpenAI-kompatibler Endpunkt)."""
        return self.execute("chat", {
            "messages": messages,
            "system": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

    def health_check(self) -> bool:
        """OpenClaw Health: GET /health muss 200 zurückgeben."""
        import httpx
        try:
            # Kurzer Timeout — wenn OpenClaw nicht läuft, schnell aufgeben
            resp = httpx.get(f"{self.base_url}/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False
