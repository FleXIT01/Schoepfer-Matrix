"""Review Service-Bridge: Die QA-Abteilung.

Koppelt repo-critic-ai (AST-Analyse, Security-Scans) mit dem
Fixer-Workflow. Wenn Code generiert wird, muss er durch diesen
Service, bevor er in die Produktion darf.

Lokaler Pfad: n:\\allinall\\repo-critic-ai
"""
from __future__ import annotations

import logging
from typing import Any

from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_review_config(repo_path: str = r"n:\allinall\repo-critic-ai") -> ServiceConfig:
    return ServiceConfig(
        name="repo-critic",
        display_name="Repo Critic AI (Code Review & Security)",
        port=3020,
        health_endpoint="/health",
        start_command="python start.py web --port 3020",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=300,
        capabilities=[
            "code_review", "security_scan", "ast_analysis",
            "linting", "quality_check", "todo_detection",
        ],
        tags=["review", "security", "qa"],
        repo_path=repo_path,
    )


class ReviewService(HttpService):
    """Bridge zu repo-critic-ai: Automatisiertes Code-Review & Security-Scans.

    Fungiert als CI/CD-Gate: Kein generierter Code darf den Orchestrator
    verlassen, ohne diese Prüfung bestanden zu haben.
    """

    def __init__(self, repo_path: str = r"n:\allinall\repo-critic-ai") -> None:
        config = create_review_config(repo_path)
        super().__init__(config)

    def review_code(self, source: str, *, language: str = "python",
                    file_path: str = "") -> ServiceResult:
        """Führt ein vollständiges Code-Review durch.

        Returns:
            ServiceResult mit data = {
                "score": float (0-100),
                "issues": list[{severity, line, message, category}],
                "suggestions": list[str],
                "security_alerts": list[dict],
            }
        """
        return self.execute("review", {
            "source": source,
            "language": language,
            "file_path": file_path,
        })

    def security_scan(self, source: str, *, check_hardcoded_keys: bool = True,
                      check_sql_injection: bool = True) -> ServiceResult:
        """Prüft Code auf Sicherheitslücken."""
        return self.execute("security", {
            "source": source,
            "checks": {
                "hardcoded_keys": check_hardcoded_keys,
                "sql_injection": check_sql_injection,
                "command_injection": True,
                "path_traversal": True,
            },
        })

    def scan_repository(self, repo_path: str) -> ServiceResult:
        """Scannt ein ganzes Repository auf Qualität und Sicherheit."""
        return self.execute("scan/repo", {
            "repo_path": repo_path,
        })

    def lint(self, source: str, *, language: str = "python") -> ServiceResult:
        """Schneller Lint-Check ohne vollständiges Review."""
        return self.execute("lint", {
            "source": source,
            "language": language,
        })
