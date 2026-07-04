"""Chimera Service-Bridge: Die Red-Team-Abteilung & LLM-Manipulation.

Koppelt projekt_für_ollama (Activation Steering, Abliteration) und
local-llm-planner (VRAM-Monitoring, Modell-Optimierung) zu einem
Hardware-nahen Eingriffs-Layer.

Lokale Pfade:
  - n:\\allinall\\projekt_für_ollama     (LLM Modding, Steering Vectors)
  - n:\\allinall\\local-llm-planner      (VRAM/GPU Monitoring & Planning)
  - n:\\allinall\\gpt_from_scratch       (Micro-Modell-Training)
"""
from __future__ import annotations

import logging
from typing import Any

from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_chimera_config(repo_path: str = r"n:\allinall\projekt_für_ollama") -> ServiceConfig:
    return ServiceConfig(
        name="chimera",
        display_name="Project Chimera (LLM Manipulation & Steering)",
        port=3030,
        health_endpoint="/health",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=180,
        capabilities=[
            "activation_steering", "abliteration", "model_modding",
            "censorship_removal", "focus_injection",
        ],
        tags=["chimera", "llm", "hardware", "red-team"],
        repo_path=repo_path,
    )


def create_planner_config(repo_path: str = r"n:\allinall\local-llm-planner") -> ServiceConfig:
    return ServiceConfig(
        name="llm-planner",
        display_name="Local LLM Planner (VRAM/GPU Monitor)",
        port=3031,
        health_endpoint="/health",
        auto_start=True,
        scale_to_zero=False,  # Ressourcen-Monitor bleibt immer an
        capabilities=[
            "vram_monitoring", "gpu_monitoring", "model_recommendation",
            "resource_planning", "optimization",
        ],
        tags=["chimera", "monitoring", "hardware"],
        repo_path=repo_path,
    )


class ChimeraService(HttpService):
    """Bridge zu Project Chimera: Direkte LLM-Manipulation im VRAM.

    Wird vom Orchestrator als letzte Instanz aufgerufen, wenn ein
    Coder-Agent nach mehreren Fix-Versuchen scheitert. Chimera
    injiziert Steering-Vectors, um das LLM in einen fokussierten
    Zustand zu zwingen.
    """

    def __init__(self, repo_path: str = r"n:\allinall\projekt_für_ollama") -> None:
        config = create_chimera_config(repo_path)
        super().__init__(config, timeout=60.0)

    def apply_steering(self, vector_name: str, *, strength: float = 1.0,
                       model: str = "") -> ServiceResult:
        """Injiziert einen Steering-Vector in das laufende LLM.

        Args:
            vector_name: Name des Vektors (z.B. "focus_coding", "precision", "creativity")
            strength: Stärke der Einwirkung (0.0 - 2.0)
            model: Zielmodell (leer = aktuell geladenes)
        """
        return self.execute("steer", {
            "vector": vector_name,
            "strength": strength,
            "model": model,
        })

    def abliterate(self, model: str, *, layers: list[int] | None = None) -> ServiceResult:
        """Entfernt Zensurschichten aus einem Modell (Abliteration).

        WARNUNG: Verändert das Modell permanent.
        """
        return self.execute("abliterate", {
            "model": model,
            "layers": layers or [],
        })

    def reset_steering(self) -> ServiceResult:
        """Setzt alle aktiven Steering-Vectors zurück auf Neutral."""
        return self.execute("steer/reset", {})


class ResourcePlannerService(HttpService):
    """Bridge zum Local LLM Planner: VRAM/GPU-Monitoring & Modellberatung.

    Läuft dauerhaft im Hintergrund und gibt dem Orchestrator Auskunft:
      - Wie viel VRAM ist frei?
      - Passt Modell X in den Speicher?
      - Welche Container müssen gestoppt werden, bevor ComfyUI starten kann?
    """

    def __init__(self, repo_path: str = r"n:\allinall\local-llm-planner") -> None:
        config = create_planner_config(repo_path)
        super().__init__(config)

    def get_resources(self) -> ServiceResult:
        """Aktueller Zustand von RAM, VRAM und GPU.

        Returns:
            ServiceResult mit data = {
                "ram_total_gb": float,
                "ram_used_gb": float,
                "vram_total_gb": float,
                "vram_used_gb": float,
                "gpu_name": str,
                "gpu_utilization": float (0-100),
            }
        """
        return self._timed_execute("resources", self.get, "/api/resources")

    def can_load_model(self, model_name: str) -> ServiceResult:
        """Prüft, ob ein bestimmtes Modell in den VRAM passt."""
        return self.execute("check", {
            "model": model_name,
        })

    def recommend_model(self, *, task: str = "coding") -> ServiceResult:
        """Empfiehlt das beste Modell für die aktuelle Hardware-Situation."""
        return self.execute("recommend", {
            "task": task,
        })

    def suggest_shutdowns(self, required_vram_gb: float) -> ServiceResult:
        """Empfiehlt, welche Services gestoppt werden müssen, um Platz zu schaffen."""
        return self.execute("suggest_shutdown", {
            "required_vram_gb": required_vram_gb,
        })
