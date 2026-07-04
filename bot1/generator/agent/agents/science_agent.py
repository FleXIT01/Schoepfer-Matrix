"""ScienceAgent: Autonomer Bio-Science Recherche-Agent.

Kombiniert ChEMBL, PubMed, ArXiv, OpenAlex und AlphaFold zu einer
vollständigen wissenschaftlichen Analyse-Pipeline:

  Query → Molekül-Suche → Protein-Struktur → Literatur → LLM-Synthese → Bericht

Anwendungsfälle:
  - "Finde Inhibitoren für EGFR"
  - "Welche Proteine sind mit Alzheimer assoziiert?"
  - "Suche neue CRISPR-Therapien für Lungenkrebs"
  - "Analysiere das Molekül Imatinib"
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Bekannte Gen-Symbole für die automatische Vertiefung (Ensembl/STRING/PDB).
# Längere Symbole zuerst, damit z.B. "BRCA1" vor "BRAF" matcht.
_KNOWN_GENES = [
    "BRCA1", "BRCA2", "PARP1", "VEGFR", "HER2", "EGFR", "KRAS", "BRAF",
    "TP53", "BCL2", "ABL1", "CDK2", "CDK4", "ALK", "MET", "PTEN", "MYC",
    "PIK3CA", "AKT1", "MTOR", "JAK2", "STAT3", "APP", "MAPT", "SNCA",
    "INS", "TNF", "IL6", "ACE2", "VEGFA",
]


class ScienceAgent(BaseAgent):
    """Agent für vollständige Bio-Science-Analyse-Workflows.

    Wird vom Orchestrator aktiviert wenn:
      - Ein wissenschaftliches Ziel erkannt wird (Stichwörter: Protein, Molekül, Krankheit,
        Inhibitor, Gene, CRISPR, klinische Studie, etc.)
      - Der ResearcherAgent depth="scientific" erhält
    """

    def analyze(
        self,
        query: str,
        *,
        save_report: bool = True,
        report_path: str = "",
        depth: str = "full",
    ) -> dict[str, Any]:
        """Führt eine vollständige wissenschaftliche Analyse durch.

        Args:
            query: Forschungsfrage (z.B. "EGFR inhibitors lung cancer")
            save_report: Bericht als Markdown-Datei speichern
            report_path: Pfad für den Bericht (Standard: Downloads)
            depth: "quick" (nur Literatur), "full" (Literatur + Struktur + Moleküle)

        Returns:
            Dict mit allen Ergebnissen und dem Bericht-Pfad.
        """
        logger.info("ScienceAgent: Analysiere '%s'", query)
        results: dict[str, Any] = {"query": query, "sections": {}}

        # Domain-Check: Nur Bio/Chemie/Medizin bekommt die volle Pipeline
        is_bio = self._is_bio_relevant(query)
        effective_depth = depth if is_bio else "quick"
        if not is_bio and depth == "full":
            logger.info("ScienceAgent: Query ist nicht bio-relevant — nur Literatur (quick mode)")

        # 1) Literatur-Recherche (immer)
        results["sections"]["arxiv"] = self._search_arxiv(query)
        results["sections"]["pubmed"] = self._search_pubmed(query)
        results["sections"]["openalex"] = self._search_openalex(query)
        results["sections"]["preprints"] = self._search_preprints(query)

        # 2) Molekül-Suche (nur bei bio-relevanten "full" Queries)
        if effective_depth == "full":
            results["sections"]["compounds"] = self._search_compounds(query)
            results["sections"]["targets"] = self._search_targets(query)
            results["sections"]["pathways"] = self._search_pathways(query)
            results["sections"]["drug_safety"] = self._search_drug_safety(query)

            # 3) Gen-/Protein-Vertiefung wenn ein bekanntes Gen erkannt wird
            gene = self._extract_gene(query, results)
            if gene:
                results["gene"] = gene
                results["sections"]["gene_annotation"] = self._lookup_gene(gene)
                results["sections"]["interactions"] = self._fetch_interactions(gene)
                results["sections"]["pdb_structures"] = self._search_pdb(gene)

            # 4) Protein-Struktur (AlphaFold) wenn eine UniProt-ID extrahiert werden kann
            uniprot_id = self._extract_uniprot_id(query, results)
            if uniprot_id:
                results["sections"]["structure"] = self._fetch_structure(uniprot_id)
                results["uniprot_id"] = uniprot_id

        # 4) LLM-Synthese
        results["report"] = self._synthesize(query, results["sections"])

        # 5) Bericht speichern
        if save_report:
            path = report_path or (
                str(Path.home() / "Downloads" / f"science_{_safe_filename(query)}.md")
            )
            try:
                _write_report(path, query, results)
                results["report_path"] = path
                logger.info("Bericht gespeichert: %s", path)
            except Exception as exc:
                logger.warning("Bericht konnte nicht gespeichert werden: %s", exc)

        return results

    @staticmethod
    def _is_bio_relevant(query: str) -> bool:
        """Prüft ob die Query biochemisch/medizinisch relevant ist.
        Überspringt ChEMBL/Reactome/openFDA für Physik/Astronomie/Mathe."""
        low = query.lower()
        # Bio/Medizin-Keywords
        bio_kw = (
            "protein", "molekül", "gen", "dna", "rna", "zelle", "enzym",
            "rezeptor", "inhibitor", "krankheit", "krebs", "tumor",
            "therapie", "medikament", "wirkstoff", "impfstoff", "vakzin",
            "virus", "bakterie", "infektion", "immun", "antikörper",
            "mutation", "sequenz", "crispr", "genom", "proteom",
            "stoffwechsel", "signalweg", "transkription", "translation",
            "pharma", "klinisch", "patient", "diagnose", "biomarker",
            "metabol", "neuro", "kardiovaskulär", "onko", "hämato",
        )
        # Nicht-Bio-Killer (Physik, Astronomie, Mathe, Informatik)
        non_bio_kw = (
            "himmel", "blau", "sonnenlicht", "gravitation", "schwerkraft",
            "planet", "stern", "galaxie", "universum", "schwarzes loch",
            "quanten", "relativität", "astronomie", "teleskop",
            "algorithmus", "datenstruktur", "programmiersprache",
            "server", "docker", "api", "json", "html", "css",
        )
        for kw in non_bio_kw:
            if kw in low:
                return False
        for kw in bio_kw:
            if kw in low:
                return True
        # Bei Unsicherheit: kein Bio → nur Literatur
        return False

    # ── Einzelne Recherche-Schritte ──────────────────────────────────────────

    def _search_arxiv(self, query: str) -> str:
        try:
            from ..tools.impl.arxiv_search import arxiv_search
            return arxiv_search(query, max_results=5)
        except Exception as exc:
            return f"[ArXiv nicht verfügbar: {exc}]"

    def _search_pubmed(self, query: str) -> str:
        try:
            from ..tools.impl.pubmed_search import pubmed_search
            return pubmed_search(query, max_results=5)
        except Exception as exc:
            return f"[PubMed nicht verfügbar: {exc}]"

    def _search_openalex(self, query: str) -> str:
        try:
            from ..tools.impl.openalex_search import openalex_search
            return openalex_search(query, max_results=5)
        except Exception as exc:
            return f"[OpenAlex nicht verfügbar: {exc}]"

    def _search_compounds(self, query: str) -> str:
        try:
            from ..tools.impl.chembl_search import chembl_search
            return chembl_search(query, search_type="compound", max_results=5)
        except Exception as exc:
            return f"[ChEMBL-Compound nicht verfügbar: {exc}]"

    def _search_targets(self, query: str) -> str:
        try:
            from ..tools.impl.chembl_search import chembl_search
            return chembl_search(query, search_type="target", max_results=5)
        except Exception as exc:
            return f"[ChEMBL-Target nicht verfügbar: {exc}]"

    def _fetch_structure(self, uniprot_id: str) -> str:
        try:
            from ..tools.impl.alphafold_fetch import alphafold_fetch
            return alphafold_fetch(uniprot_id)
        except Exception as exc:
            return f"[AlphaFold nicht verfügbar: {exc}]"

    def _search_preprints(self, query: str) -> str:
        try:
            from ..tools.impl.europepmc_search import europepmc_search
            return europepmc_search(query, max_results=5, preprints_only=True)
        except Exception as exc:
            return f"[Europe PMC nicht verfügbar: {exc}]"

    def _search_pathways(self, query: str) -> str:
        try:
            from ..tools.impl.reactome_search import reactome_search
            return reactome_search(query, max_results=5)
        except Exception as exc:
            return f"[Reactome nicht verfügbar: {exc}]"

    def _search_drug_safety(self, query: str) -> str:
        try:
            from ..tools.impl.openfda_search import openfda_search
            # Erstes aussagekräftiges Wort als Wirkstoff-Heuristik
            term = next((w for w in query.split() if len(w) > 3), query)
            return openfda_search(term, data_type="label", max_results=2)
        except Exception as exc:
            return f"[openFDA nicht verfügbar: {exc}]"

    def _lookup_gene(self, gene: str) -> str:
        try:
            from ..tools.impl.ensembl_lookup import ensembl_lookup
            return ensembl_lookup(gene)
        except Exception as exc:
            return f"[Ensembl nicht verfügbar: {exc}]"

    def _fetch_interactions(self, gene: str) -> str:
        try:
            from ..tools.impl.string_db import string_db
            return string_db(gene, max_partners=8)
        except Exception as exc:
            return f"[STRING nicht verfügbar: {exc}]"

    def _search_pdb(self, gene: str) -> str:
        try:
            from ..tools.impl.rcsb_pdb import rcsb_pdb
            return rcsb_pdb(gene, max_results=3)
        except Exception as exc:
            return f"[PDB nicht verfügbar: {exc}]"

    def _extract_gene(self, query: str, results: dict) -> str:
        """Erkennt ein bekanntes Gen-Symbol in der Query oder den ChEMBL-Targets."""
        q_upper = query.upper()
        target_text = results.get("sections", {}).get("targets", "").upper()
        for gene in _KNOWN_GENES:
            if gene in q_upper or gene in target_text:
                logger.info("Gen '%s' für Vertiefung erkannt", gene)
                return gene
        return ""

    def _extract_uniprot_id(self, query: str, results: dict) -> str:
        """Versucht eine UniProt-ID aus der Query oder den ChEMBL-Ergebnissen zu extrahieren."""
        import re

        # Direkt in der Query? (z.B. "P00533" oder "UniProt:P00533")
        m = re.search(r"\b([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})\b",
                      query.upper())
        if m:
            return m.group(1)

        # Aus ChEMBL-Target-Ergebnissen extrahieren (häufige Gene → UniProt-Mapping)
        target_text = results.get("sections", {}).get("targets", "")
        known_targets = {
            "EGFR": "P00533", "BRCA1": "P38398", "BRCA2": "P51587",
            "TP53": "P04637", "KRAS": "P01116", "BCL2": "P10415",
            "ABL1": "P00519", "VEGFR": "P35968", "HER2": "P04626",
            "BRAF": "P15056", "CDK2": "P24941", "CDK4": "P11802",
            "ALK": "Q9UM73", "MET": "P08581", "PARP1": "P09874",
        }
        q_upper = query.upper()
        for gene, uid in known_targets.items():
            if gene in q_upper or gene in target_text.upper():
                logger.info("UniProt-ID '%s' für Gene '%s' gefunden", uid, gene)
                return uid

        return ""

    def _synthesize(self, query: str, sections: dict[str, str]) -> str:
        """LLM-Synthese aller gesammelten Daten zu einem strukturierten Bericht."""
        from ...llm.base import LLMMessage

        context_parts = []
        for section_name, content in sections.items():
            if content and not content.startswith("["):
                context_parts.append(f"### {section_name.upper()}\n{content[:2000]}")

        if not context_parts:
            return self._research_via_llm_summary(query)

        context = "\n\n".join(context_parts[:5])[:8000]
        messages = [LLMMessage(
            role="user",
            content=(
                f"Du bist ein erfahrener Biowissenschaftler. Erstelle einen strukturierten "
                f"Forschungsbericht zu:\n\n**{query}**\n\n"
                f"Nutze folgende Recherche-Ergebnisse:\n\n{context}\n\n"
                f"Format des Berichts:\n"
                f"## Zusammenfassung\n"
                f"## Wichtigste Erkenntnisse\n"
                f"## Relevante Moleküle/Targets\n"
                f"## Aktuelle Forschung (Paper)\n"
                f"## Empfehlung / Nächste Schritte\n\n"
                f"Antworte auf Deutsch. Max. 600 Wörter."
            ),
        )]
        try:
            return self._llm.chat(messages=messages, temperature=0.2, max_tokens=1500)
        except Exception as exc:
            logger.warning("LLM-Synthese fehlgeschlagen: %s", exc)
            return f"[Synthese fehlgeschlagen: {exc}]\n\nRohdaten:\n{context[:2000]}"

    def _research_via_llm_summary(self, query: str) -> str:
        from ...llm.base import LLMMessage
        messages = [LLMMessage(
            role="user",
            content=f"Erstelle eine kurze wissenschaftliche Zusammenfassung zu: {query}",
        )]
        try:
            return self._llm.chat(messages=messages, temperature=0.3)
        except Exception as exc:
            return f"[LLM nicht verfügbar: {exc}]"


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _safe_filename(query: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", query[:40]).strip("_")


def _write_report(path: str, query: str, results: dict) -> None:
    """Schreibt den vollständigen Bericht als Markdown-Datei."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Wissenschaftlicher Bericht: {query}\n",
        f"*Erstellt am {_today()} vom ScienceAgent der Universellen Schöpfer-Matrix*\n\n",
        "---\n\n",
        "## Synthesierter Bericht\n\n",
        results.get("report", "(kein Bericht)"),
        "\n\n---\n\n## Rohdaten\n\n",
    ]

    for section, content in results.get("sections", {}).items():
        lines.append(f"### {section.upper()}\n\n```\n{content[:3000]}\n```\n\n")

    if results.get("uniprot_id"):
        lines.append(
            f"\n**UniProt-ID:** {results['uniprot_id']}\n"
            f"**AlphaFold-Viewer:** https://alphafold.ebi.ac.uk/entry/{results['uniprot_id']}\n"
        )

    p.write_text("".join(lines), encoding="utf-8")


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
