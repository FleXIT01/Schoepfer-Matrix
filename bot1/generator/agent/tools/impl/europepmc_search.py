"""Tool: Biomedizinische Literatur + Preprints via Europe PMC suchen.

Europe PMC (EMBL-EBI) vereint PubMed, PubMed Central, Patente, klinische Leitlinien
UND Preprint-Server (bioRxiv, medRxiv) in einer einzigen kostenlosen API ohne Key.
Damit deckt dieses Tool zugleich 'biorxiv' und 'europepmc' aus dem Plan ab.
  https://europepmc.org/RestfulWebService
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "CRISPR base editing", "max_results": 5, "preprints_only": False}
DEFINITION = {
    "name": "europepmc_search",
    "description": (
        "Sucht biomedizinische Literatur UND Preprints (bioRxiv/medRxiv) über Europe PMC. "
        "Liefert Titel, Autoren, Jahr, Quelle, Zitationen, DOI und Abstract. "
        "Ideal für: neueste Forschung inkl. unveröffentlichter Preprints."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Suchbegriff (z.B. 'CRISPR base editing')"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5)"},
            "preprints_only": {"type": "boolean", "description": "Nur bioRxiv/medRxiv-Preprints (Standard: False)"},
        },
        "required": ["query"],
    },
}

_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
}


def europepmc_search(query: str, max_results: int = 5, preprints_only: bool = False) -> str:
    """Sucht Literatur und Preprints in Europe PMC."""
    import httpx

    search_query = query.strip()
    if preprints_only:
        search_query = f"({search_query}) AND SRC:PPR"

    try:
        resp = httpx.get(
            _BASE,
            params={
                "query": search_query,
                "format": "json",
                "pageSize": max(1, min(max_results, 15)),
                "resultType": "core",
                "sort": "CITED desc",
            },
            timeout=20, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[Europe PMC-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[Europe PMC-Verbindungsfehler: {exc}]"

    results = (data.get("resultList") or {}).get("result", [])
    if not results:
        return f"[Europe PMC: Keine Treffer für '{query}']"

    label = "Preprints" if preprints_only else "Publikationen"
    lines = [f"Europe PMC {label} für '{query}': {len(results)} Treffer\n"]
    for i, art in enumerate(results, 1):
        title = (art.get("title") or "?").strip().rstrip(".")
        authors = art.get("authorString", "?")
        year = art.get("pubYear", "?")
        source = art.get("source", "?")  # MED, PPR (preprint), PMC...
        cited = art.get("citedByCount", 0)
        doi = art.get("doi", "")
        abstract = (art.get("abstractText") or "").strip()
        if len(abstract) > 350:
            abstract = abstract[:350] + "…"

        src_label = "📄 Preprint" if source == "PPR" else f"Quelle: {source}"
        lines.append(
            f"[{i}] {title}\n"
            f"    {authors[:120]} ({year}) | {src_label} | Zitationen: {cited}\n"
            + (f"    DOI: https://doi.org/{doi}\n" if doi else "")
            + (f"    Abstract: {abstract}\n" if abstract else "")
        )

    return "\n".join(lines)
