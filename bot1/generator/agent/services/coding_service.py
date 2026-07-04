"""Coding Service-Bridge: Die autonomen Programmierer.

Vereint agenticSeek (autonomes Coding), SuperAGI (Langzeit-Agenten)
und Langchain-Chatchat (multilinguales RAG) zu einem einheitlichen
Code-Generierungs-Layer.

Lokale Pfade:
  - n:\\allinall\\agenticSeek-main     (Offline Manus-Alternative)
  - n:\\allinall\\SuperAGI-main        (Autonome Agenten-Framework)
  - n:\\allinall\\Langchain-Chatchat-master  (RAG + Chat)
"""
from __future__ import annotations

import logging
from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_agenticseek_config(repo_path: str = r"n:\allinall\agenticSeek-main") -> ServiceConfig:
    return ServiceConfig(
        name="agenticseek",
        display_name="agenticSeek (Autonomer Coder)",
        port=5000,
        health_endpoint="/health",
        start_command="python api/main.py --port 5000",
        auto_start=False,  # Nur bei Bedarf via ensure_running()
        idle_timeout_seconds=300,
        capabilities=[
            "code_generation", "code_editing", "file_manipulation",
            "autonomous_coding", "project_scaffolding",
        ],
        tags=["coding", "autonomous", "worker"],
        repo_path=repo_path,
    )


def create_superagi_config(repo_path: str = r"n:\allinall\SuperAGI-main") -> ServiceConfig:
    return ServiceConfig(
        name="superagi",
        display_name="SuperAGI (Long-Running Agent Framework)",
        port=3011,
        health_endpoint="/health",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=600,
        capabilities=[
            "long_running_tasks", "autonomous_agents", "background_jobs",
            "multi_step_planning", "goal_decomposition",
        ],
        tags=["coding", "autonomous", "long-running"],
        repo_path=repo_path,
    )


class CodingService(HttpService):
    """Einheitlicher Zugriff auf die Programmier-Agenten.

    Der Orchestrator ruft hier an, wenn Code geschrieben, editiert
    oder ein ganzes Projekt scaffolded werden muss.
    """

    def __init__(self, repo_path: str = r"n:\allinall\agenticSeek-main") -> None:
        config = create_agenticseek_config(repo_path)
        super().__init__(config, timeout=300.0)  # Coding kann lange dauern

    def generate_code(self, task: str, *, language: str = "python",
                      context: str = "", constraints: list[str] | None = None) -> ServiceResult:
        """Generiert Code für einen bestimmten Task."""
        return self.execute("generate", {
            "task": task,
            "language": language,
            "context": context,
            "constraints": constraints or [],
        })

    def edit_code(self, source: str, instruction: str, *,
                  file_path: str = "") -> ServiceResult:
        """Editiert existierenden Code nach Anweisung."""
        return self.execute("edit", {
            "source": source,
            "instruction": instruction,
            "file_path": file_path,
        })

    def scaffold_project(self, description: str, *, tech_stack: list[str] | None = None,
                         output_dir: str = "") -> ServiceResult:
        """Erstellt ein komplettes Projektgerüst."""
        return self.execute("scaffold", {
            "description": description,
            "tech_stack": tech_stack or [],
            "output_dir": output_dir,
        })

    def fix_code(self, source: str, error: str, *, context: str = "") -> ServiceResult:
        """Repariert fehlerhaften Code anhand eines Tracebacks."""
        return self.execute("fix", {
            "source": source,
            "error": error,
            "context": context,
        })

    def explain_code(self, source: str) -> ServiceResult:
        """Erklärt, was ein Code-Abschnitt tut."""
        return self.execute("explain", {
            "source": source,
        })
