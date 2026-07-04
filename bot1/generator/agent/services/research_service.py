"""Research Service-Bridge: Die Forscher.

Vereint gpt-researcher (Deep Research), SurfSense (Web-Monitoring)
und die Literatur-Datenbanken (PubMed, arXiv, OpenAlex, etc.) zu
einem einheitlichen Forschungs-Layer.

Lokale Pfade:
  - n:\\allinall\\gpt-researcher-main    (Deep Research Agent)
  - n:\\allinall\\SurfSense-main         (Web-Monitoring & Sammlung)
  - n:\\allinall\\deepwiki-open-main     (Auto-Wiki-Generator)
"""
from __future__ import annotations

import logging
from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_researcher_config(repo_path: str = r"n:\allinall\gpt-researcher-main") -> ServiceConfig:
    return ServiceConfig(
        name="gpt-researcher",
        display_name="GPT Researcher (Deep Research Agent)",
        port=8000,
        health_endpoint="/health",
        start_command="python backend/run_server.py",
        auto_start=False,  # Nur bei Bedarf via ensure_running()
        idle_timeout_seconds=600,
        capabilities=[
            "deep_research", "web_search", "report_generation",
            "fact_checking", "source_aggregation",
        ],
        tags=["research", "web", "worker"],
        repo_path=repo_path,
    )


def create_surfsense_config(repo_path: str = r"n:\allinall\SurfSense-main") -> ServiceConfig:
    return ServiceConfig(
        name="surfsense",
        display_name="SurfSense (Web Monitoring & Collection)",
        port=8003,
        health_endpoint="/health",
        start_command="python surfsense_backend/main.py",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=600,
        capabilities=[
            "web_monitoring", "web_scraping", "content_collection",
            "news_aggregation", "feed_watching",
        ],
        tags=["research", "web", "monitoring"],
        repo_path=repo_path,
    )


def create_deepwiki_config(repo_path: str = r"n:\allinall\deepwiki-open-main") -> ServiceConfig:
    return ServiceConfig(
        name="deepwiki",
        display_name="DeepWiki (Auto Wiki Generator)",
        port=8004,
        health_endpoint="/health",
        start_command="python api/main.py",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=300,
        capabilities=[
            "wiki_generation", "code_documentation", "architecture_diagrams",
            "auto_documentation",
        ],
        tags=["research", "documentation", "wiki"],
        repo_path=repo_path,
    )


class ResearchService(HttpService):
    """Einheitlicher Zugriff auf Forschung, Web-Monitoring und Dokumentation.

    Der Orchestrator nutzt diesen Service wenn:
      - Tiefe Recherche zu einem Thema nötig ist (gpt-researcher)
      - Das Web auf neue Inhalte überwacht werden soll (SurfSense)
      - Automatische Dokumentation erstellt werden soll (DeepWiki)
    """

    def __init__(self, repo_path: str = r"n:\allinall\gpt-researcher-main") -> None:
        config = create_researcher_config(repo_path)
        super().__init__(config, timeout=600.0)  # Research kann sehr lange dauern

    def deep_research(self, query: str, *, report_type: str = "research_report",
                      max_sources: int = 10) -> ServiceResult:
        """Startet eine tiefe Recherche und generiert einen Report."""
        return self.execute("research", {
            "query": query,
            "report_type": report_type,
            "max_sources": max_sources,
        })

    def quick_search(self, query: str) -> ServiceResult:
        """Schnelle Web-Suche ohne tiefe Analyse."""
        return self.execute("search", {
            "query": query,
        })

    def generate_wiki(self, repo_path: str, *, output_format: str = "markdown") -> ServiceResult:
        """Generiert automatisch eine Wiki/Dokumentation für ein Repository."""
        return self.execute("wiki/generate", {
            "repo_path": repo_path,
            "output_format": output_format,
        })

    def monitor_sources(self, urls: list[str], *, keywords: list[str] | None = None,
                        interval_minutes: int = 60) -> ServiceResult:
        """Startet die Überwachung von Web-Quellen (SurfSense-Modus)."""
        return self.execute("monitor/start", {
            "urls": urls,
            "keywords": keywords or [],
            "interval_minutes": interval_minutes,
        })
