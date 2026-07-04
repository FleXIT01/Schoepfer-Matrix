"""Knowledge Service-Bridge: Das Langzeitgedächtnis.

Vereint MaxKB, WeKnora und Khoj zu einem einheitlichen Wissens-Layer.
Speichert, indiziert und durchsucht Informationen aus allen Quellen
(Lern-Repos, PDFs, Web-Recherche, generierter Code).

Lokale Pfade:
  - n:\\allinall\\MaxKB-2      (RAG-Server, Vue/Python)
  - n:\\allinall\\WeKnora-main  (Wiki-Generator)
  - n:\\allinall\\khoj-master   (Personal Second Brain)
"""
from __future__ import annotations

import logging
from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_maxkb_config(repo_path: str = r"n:\allinall\MaxKB-2") -> ServiceConfig:
    return ServiceConfig(
        name="maxkb",
        display_name="MaxKB (RAG Knowledge Base)",
        port=8080,
        health_endpoint="/api/health",
        # Docker: versuche bestehenden Container zu starten, sonst neu erstellen
        start_command="docker start omega-maxkb || docker run -d --name omega-maxkb -p 8080:8080 1panel/maxkb",
        auto_start=False,  # Docker nicht immer verfügbar
        capabilities=[
            "rag", "vector_search", "knowledge_store",
            "document_ingestion", "semantic_search",
        ],
        tags=["memory", "rag", "knowledge"],
        repo_path=repo_path,
    )


def create_weknora_config(repo_path: str = r"n:\allinall\WeKnora-main") -> ServiceConfig:
    return ServiceConfig(
        name="weknora",
        display_name="WeKnora (Interactive Wiki Generator)",
        port=8081,
        health_endpoint="/api/health",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=600,
        capabilities=["wiki_generation", "knowledge_visualization", "document_transform"],
        tags=["memory", "wiki", "documentation"],
        repo_path=repo_path,
    )


def create_khoj_config(repo_path: str = r"n:\allinall\khoj-master") -> ServiceConfig:
    return ServiceConfig(
        name="khoj",
        display_name="Khoj (Personal Second Brain)",
        port=42110,
        health_endpoint="/api/health",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=600,
        capabilities=[
            "personal_search", "file_indexing", "note_search",
            "local_file_rag",
        ],
        tags=["memory", "personal", "search"],
        repo_path=repo_path,
    )


class KnowledgeService(HttpService):
    """Einheitlicher Zugriff auf das gesamte Wissenssystem (MaxKB + WeKnora + Khoj).

    Bietet eine stabile API für:
      - Wissen speichern (ingest)
      - Wissen suchen (search / RAG)
      - Wissen strukturieren (wiki generation)
    """

    def __init__(self, repo_path: str = r"n:\allinall\MaxKB-2") -> None:
        config = create_maxkb_config(repo_path)
        super().__init__(config)

    def search(self, query: str, *, top_k: int = 5, dataset: str = "") -> ServiceResult:
        """Semantische Suche über die gesamte Wissensbasis."""
        return self.execute("search", {
            "query": query,
            "top_k": top_k,
            "dataset": dataset,
        })

    def ingest_text(self, title: str, content: str, *, source: str = "",
                    tags: list[str] | None = None) -> ServiceResult:
        """Speist einen Text in die Vektordatenbank ein."""
        return self.execute("ingest", {
            "title": title,
            "content": content,
            "source": source,
            "tags": tags or [],
        })

    def ingest_file(self, file_path: str, *, dataset: str = "") -> ServiceResult:
        """Speist eine Datei (Markdown, PDF, Code) in die Wissensbasis ein."""
        return self.execute("ingest/file", {
            "file_path": file_path,
            "dataset": dataset,
        })

    def ingest_repository(self, repo_path: str, *, dataset: str = "",
                          file_patterns: list[str] | None = None) -> ServiceResult:
        """Speist ein komplettes Repository in die Wissensbasis ein.

        Wird für die Lern-Repos (build-your-own-x, developer-roadmap, etc.)
        verwendet, um das System zum „Senior Developer" zu machen.
        """
        return self.execute("ingest/repository", {
            "repo_path": repo_path,
            "dataset": dataset,
            "file_patterns": file_patterns or ["*.md", "*.py", "*.js", "*.ts", "*.rst"],
        })

    def list_datasets(self) -> ServiceResult:
        """Listet alle verfügbaren Wissensdatenbanken."""
        return self._timed_execute("list_datasets", self.get, "/api/datasets")

    def ask(self, question: str, *, dataset: str = "", with_sources: bool = True) -> ServiceResult:
        """Stellt eine Frage an das RAG-System und erhält eine KI-generierte Antwort."""
        return self.execute("ask", {
            "question": question,
            "dataset": dataset,
            "with_sources": with_sources,
        })


# ─── Die Lern-Repositories, die in MaxKB injiziert werden ───────────────

KNOWLEDGE_REPOS = {
    "system-design-primer": {
        "path": r"n:\allinall\system-design-primer-master",
        "dataset": "software_architecture",
        "description": "System Design Patterns, Skalierung, Caching, Load Balancing",
        "patterns": ["*.md"],
    },
    "developer-roadmap": {
        "path": r"n:\allinall\developer-roadmap-master",
        "dataset": "developer_skills",
        "description": "Lernpfade für Frontend, Backend, DevOps, AI/ML",
        "patterns": ["*.md", "*.json"],
    },
    "build-your-own-x": {
        "path": r"n:\allinall\build-your-own-x-master",
        "dataset": "build_templates",
        "description": "Schritt-für-Schritt-Anleitungen: eigene DB, OS, Compiler, etc.",
        "patterns": ["*.md"],
    },
    "free-programming-books": {
        "path": r"n:\allinall\free-programming-books-main",
        "dataset": "programming_books",
        "description": "Kuratierte Liste freier Programmierbücher und Kurse",
        "patterns": ["*.md"],
    },
    "coding-interview-university": {
        "path": r"n:\allinall\coding-interview-university-main",
        "dataset": "cs_fundamentals",
        "description": "Algorithmen, Datenstrukturen, Interviewvorbereitung",
        "patterns": ["*.md"],
    },
    "project-based-learning": {
        "path": r"n:\allinall\project-based-learning-master",
        "dataset": "project_templates",
        "description": "Projektbasierte Tutorials für alle Sprachen",
        "patterns": ["*.md"],
    },
    "freeCodeCamp": {
        "path": r"n:\allinall\freeCodeCamp-main",
        "dataset": "web_curriculum",
        "description": "Vollständiger Web-Entwicklungs-Lehrplan",
        "patterns": ["*.md", "*.js"],
    },
    "public-apis": {
        "path": r"n:\allinall\public-apis-master",
        "dataset": "api_catalog",
        "description": "Katalog kostenloser öffentlicher APIs",
        "patterns": ["*.md"],
    },
    "awesome": {
        "path": r"n:\allinall\awesome-main",
        "dataset": "awesome_resources",
        "description": "Kuratierte Listen zu allen Tech-Themen",
        "patterns": ["*.md"],
    },
}
