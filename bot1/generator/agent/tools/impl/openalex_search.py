"""Tool: Wissenschaftliche Literatur via OpenAlex durchsuchen.

OpenAlex ist eine kostenlose, offene Datenbank mit 250M+ wissenschaftlichen
Werken (Paper, Bücher, Daten-Sets). Kein API-Key nötig.
https://docs.openalex.org
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "CRISPR gene editing cancer treatment", "max_results": 5}
DEFINITION = {
    "name": "openalex_search",
    "description": (
        "Durchsucht 250M+ wissenschaftliche Werke via OpenAlex (kostenlos, kein Key). "
        "Ideal für: Medizin, Biologie, Chemie, Physik, Sozialwissenschaften."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Suchanfrage (englisch empfohlen)"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5, Max: 10)"},
            "filter_year": {"type": "integer", "description": "Nur Paper ab diesem Jahr (optional)"},
        },
        "required": ["query"],
    },
}

_BASE = "https://api.openalex.org/works"
_HEADERS = {
    "User-Agent": "research-bot/1.0 (mailto:research@example.com)",
}


def openalex_search(query: str, max_results: int = 5, filter_year: int = 0) -> str:
    """Sucht in OpenAlex und gibt strukturierte Ergebnisse zurück."""
    import httpx

    params: dict = {
        "search": query,
        "per_page": min(max_results, 10),
        "sort": "relevance_score:desc",
        "select": "id,title,publication_year,cited_by_count,authorships,abstract_inverted_index,primary_location",
    }
    if filter_year:
        params["filter"] = f"publication_year:>{filter_year - 1}"

    try:
        resp = httpx.get(_BASE, params=params, timeout=15, headers=_HEADERS)
        if resp.status_code != 200:
            return f"[OpenAlex-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:
        return f"[OpenAlex-Verbindungsfehler: {exc}]"

    results = data.get("results", [])
    if not results:
        return f"[Keine OpenAlex-Ergebnisse für: {query}]"

    lines = [f"OpenAlex-Suche: '{query}' — {len(results)} Ergebnis(se)\n"]
    for i, work in enumerate(results, 1):
        title = work.get("title") or "Kein Titel"
        year = work.get("publication_year", "?")
        citations = work.get("cited_by_count", 0)
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in (work.get("authorships") or [])
        ][:3]

        # Abstract aus inverted index rekonstruieren
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

        doi_url = ""
        loc = work.get("primary_location") or {}
        source = loc.get("source") or {}
        if source.get("homepage_url"):
            doi_url = source["homepage_url"]

        lines.append(
            f"[{i}] {title}\n"
            f"    Autoren: {', '.join(filter(None, authors))}{' et al.' if len(authors) == 3 else ''}\n"
            f"    Jahr: {year} | Zitierungen: {citations}\n"
            f"    Abstract: {abstract[:300]}{'…' if len(abstract) > 300 else ''}\n"
            + (f"    Quelle: {doi_url}\n" if doi_url else "")
        )

    return "\n".join(lines)


def _reconstruct_abstract(inverted: dict | None) -> str:
    """Rekonstruiert den Abstract aus dem OpenAlex inverted index."""
    if not inverted:
        return "(kein Abstract verfügbar)"
    try:
        positions: list[tuple[int, str]] = []
        for word, pos_list in inverted.items():
            for pos in pos_list:
                positions.append((pos, word))
        positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in positions)
    except Exception:
        return "(Abstract-Rekonstruktion fehlgeschlagen)"
