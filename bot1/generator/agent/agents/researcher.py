"""ResearcherAgent: durchsucht das Web, wissenschaftliche Datenbanken und lokale Quellen.

Nutzt gpt-researcher für Deep Research, SurfSense für Web-Monitoring
und die Science-Plugins (PubMed, arXiv, etc.) für wissenschaftliche Recherche.
Kann auch DeepWiki triggern, um automatisch Dokumentation aus Code zu generieren.
"""
from __future__ import annotations

import logging
from typing import Any

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Agent für Forschung, Recherche und Wissenssammlung.

    Wird vom Orchestrator aufgerufen, wenn:
      - Vor der Code-Generierung Hintergrundinformationen benötigt werden
      - Eine tiefe Analyse eines Themas erforderlich ist
      - Wissenschaftliche Papers durchsucht werden müssen
      - Web-Quellen auf neue Inhalte überwacht werden sollen
    """

    def research(self, query: str, *, depth: str = "standard",
                 sources: list[str] | None = None) -> dict[str, Any]:
        """Führt eine Recherche durch und gibt strukturierte Ergebnisse zurück.

        Args:
            query: Die Forschungsfrage.
            depth: "quick" (Web-Suche), "standard" (Deep Research), "scientific" (PubMed/arXiv).
            sources: Optionale Einschränkung der Quellen.

        Returns:
            Dict mit "summary", "sources", "raw_data", "confidence".
        """
        if not self.has_registry:
            return self._research_via_llm(query)

        if depth == "quick":
            return self._quick_search(query)
        elif depth == "scientific":
            return self._scientific_research(query)
        else:
            return self._deep_research(query, sources)

    def _quick_search(self, query: str) -> dict[str, Any]:
        """Schnelle Web-Suche: GitHub-Docs + OpenAlex, dann gpt-researcher wenn verfügbar."""
        findings: list[str] = []

        # 1) GitHub-Dokumentation (immer verfügbar)
        try:
            from ..tools.impl.web_search import web_search
            gh = web_search(query)
            if not gh.startswith("[Keine"):
                findings.append(gh[:3000])
        except Exception as exc:
            logger.debug("web_search fehlgeschlagen: %s", exc)

        # 2) OpenAlex für wissenschaftliche Begriffe
        try:
            from ..tools.impl.openalex_search import openalex_search
            oa = openalex_search(query, max_results=3)
            if not oa.startswith("["):
                findings.append(oa[:2000])
        except Exception as exc:
            logger.debug("openalex_search fehlgeschlagen: %s", exc)

        # 3) gpt-researcher — nur nutzen wenn er bereits läuft (kein Auto-Start)
        researcher = self.registry.get_service("gpt-researcher")
        if researcher and researcher.health_check():
            result = researcher.execute("search", {"query": query})
            if result.ok:
                findings.append(str(result.data)[:2000])

        if findings:
            return {"summary": "\n\n---\n\n".join(findings), "sources": [], "depth": "quick"}
        return self._research_via_llm(query)

    def _deep_research(self, query: str, _sources: list[str] | None) -> dict[str, Any]:
        """Tiefe Recherche: gpt-researcher + Knowledge-Base."""
        findings: dict[str, Any] = {"summary": "", "sources": [], "depth": "deep"}

        # 1) Knowledge-Base durchsuchen (nur wenn bereits aktiv)
        knowledge = self.registry.get_service("maxkb")
        if knowledge and knowledge.health_check():
            try:
                kb_result = knowledge.execute("search", {
                    "query": query, "top_k": 5,
                })
                if kb_result.ok and kb_result.data:
                    findings["knowledge_base"] = str(kb_result.data)[:2000]
            except Exception as exc:
                logger.debug("MaxKB-Suche fehlgeschlagen (nicht kritisch): %s", exc)

        # 2) Deep Research via gpt-researcher — nur wenn bereits aktiv (kein Auto-Start)
        researcher = self.registry.get_service("gpt-researcher")
        if researcher and researcher.health_check():
            try:
                result = researcher.execute("research", {
                    "query": query,
                    "report_type": "research_report",
                    "max_sources": 10,
                })
                if result.ok and result.data:
                    findings["summary"] = str(result.data)
            except Exception as exc:
                logger.debug("Deep Research fehlgeschlagen: %s", exc)

        # 3) Fallback auf LLM, wenn nichts gefunden
        if not findings["summary"]:
            llm_result = self._research_via_llm(query)
            findings["summary"] = llm_result.get("summary", "")

        return findings

    def _scientific_research(self, query: str) -> dict[str, Any]:
        """Wissenschaftliche Recherche: ArXiv + PubMed + OpenAlex + optionale Services."""
        findings: dict[str, Any] = {"summary": "", "sources": [], "depth": "scientific"}
        raw_parts: list[str] = []

        # 1) ArXiv — Paper und Preprints
        try:
            from ..tools.impl.arxiv_search import arxiv_search
            ax = arxiv_search(query, max_results=4)
            if not ax.startswith("["):
                raw_parts.append(ax)
                findings["arxiv"] = ax[:3000]
        except Exception as exc:
            logger.debug("arxiv_search fehlgeschlagen: %s", exc)

        # 2) PubMed — biomedizinische Literatur
        try:
            from ..tools.impl.pubmed_search import pubmed_search
            pm = pubmed_search(query, max_results=4)
            if not pm.startswith("["):
                raw_parts.append(pm)
                findings["pubmed"] = pm[:3000]
        except Exception as exc:
            logger.debug("pubmed_search fehlgeschlagen: %s", exc)

        # 3) OpenAlex — breite wissenschaftliche Suche
        try:
            from ..tools.impl.openalex_search import openalex_search
            oa = openalex_search(query, max_results=4)
            if not oa.startswith("["):
                raw_parts.append(oa)
                findings["openalex"] = oa[:3000]
        except Exception as exc:
            logger.debug("openalex_search fehlgeschlagen: %s", exc)

        # 4) SurfSense — nur wenn bereits aktiv
        if self.has_registry:
            surfsense = self.registry.get_service("surfsense")
            if surfsense and surfsense.health_check():
                try:
                    result = surfsense.execute("search", {"query": query})
                    if result.ok and result.data:
                        raw_parts.append(str(result.data)[:2000])
                except Exception as exc:
                    logger.debug("SurfSense fehlgeschlagen: %s", exc)

        if not raw_parts:
            findings.update(self._research_via_llm(query))
            return findings

        # LLM-Synthese der gesammelten Ergebnisse
        context = "\n\n---\n\n".join(raw_parts)[:6000]
        from ...llm.base import LLMMessage
        messages = [LLMMessage(
            role="user",
            content=(
                f"Fasse die folgenden wissenschaftlichen Recherche-Ergebnisse zu '{query}' "
                f"in einem strukturierten Bericht zusammen (Deutsch, maximal 500 Wörter):\n\n"
                f"{context}"
            ),
        )]
        try:
            findings["summary"] = self._llm.chat(messages=messages, temperature=0.2)
        except Exception:
            findings["summary"] = context[:2000]

        return findings

    def generate_documentation(self, repo_path: str) -> dict[str, Any]:
        """Generiert automatisch Dokumentation für ein Repository via DeepWiki."""
        if not self.has_registry:
            return {"error": "Keine Registry verfügbar."}

        deepwiki = self.registry.get_service("deepwiki")
        if deepwiki and deepwiki.health_check():
            result = deepwiki.execute("wiki/generate", {
                "repo_path": repo_path,
                "output_format": "markdown",
            })
            if result.ok:
                return {"documentation": str(result.data), "source": "deepwiki"}

        return {"error": "DeepWiki nicht verfügbar."}

    def ingest_knowledge(self, title: str, content: str, *,
                         source: str = "", tags: list[str] | None = None) -> bool:
        """Speist neues Wissen in die zentrale Wissensbasis (MaxKB) ein."""
        if not self.has_registry:
            return False

        knowledge = self.registry.get_service("maxkb")
        if knowledge:
            result = knowledge.execute("ingest", {
                "title": title,
                "content": content,
                "source": source,
                "tags": tags or [],
            })
            return result.ok
        return False

    def _research_via_llm(self, query: str) -> dict[str, Any]:
        """Fallback: Einfache LLM-basierte Recherche."""
        from ...llm.base import LLMMessage
        messages = [LLMMessage(role="user", content=f"Recherchiere gründlich: {query}")]
        try:
            raw = self._llm.chat(messages=messages, temperature=0.3)
            return {"summary": raw, "sources": [], "depth": "llm_only"}
        except Exception as exc:
            logger.warning("LLM-Recherche fehlgeschlagen: %s", exc)
            return {"summary": "", "sources": [], "error": str(exc)}
