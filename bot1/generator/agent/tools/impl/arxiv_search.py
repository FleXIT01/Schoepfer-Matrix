"""Tool: Wissenschaftliche Paper auf ArXiv.org suchen.

Nutzt die kostenlose ArXiv API (kein API-Key nötig).
Gibt Titel, Autoren, Abstract und Link der Top-Ergebnisse zurück.
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "protein folding transformer", "max_results": 5}
DEFINITION = {
    "name": "arxiv_search",
    "description": (
        "Sucht wissenschaftliche Paper auf ArXiv.org. "
        "Ideal für: KI/ML, Physik, Bioinformatik, Mathematik, Informatik-Forschung."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Suchanfrage (englisch)"},
            "max_results": {"type": "integer", "description": "Maximale Anzahl Ergebnisse (Standard: 5)"},
            "category": {"type": "string", "description": "ArXiv-Kategorie, z.B. 'cs.AI', 'q-bio.BM' (optional)"},
        },
        "required": ["query"],
    },
}

_BASE = "https://export.arxiv.org/api/query"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}


def arxiv_search(query: str, max_results: int = 5, category: str = "") -> str:
    """Sucht Paper auf ArXiv und gibt formatierte Ergebnisse zurück."""
    import httpx
    import xml.etree.ElementTree as ET

    search_query = query
    if category:
        search_query = f"cat:{category} AND all:{query}"

    params = {
        "search_query": f"all:{search_query}",
        "start": 0,
        "max_results": min(max_results, 10),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    try:
        resp = httpx.get(_BASE, params=params, timeout=15, headers=_HEADERS)
        if resp.status_code != 200:
            return f"[ArXiv-Fehler: HTTP {resp.status_code}]"
    except Exception as exc:
        return f"[ArXiv-Verbindungsfehler: {exc}]"

    try:
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return f"[Keine ArXiv-Paper gefunden für: {query}]"

        lines = [f"ArXiv-Suche: '{query}' — {len(entries)} Ergebnis(se)\n"]
        for i, entry in enumerate(entries, 1):
            title = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
            abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()
            authors = [
                a.findtext("atom:name", "", ns)
                for a in entry.findall("atom:author", ns)
            ][:3]
            link = ""
            for lnk in entry.findall("atom:link", ns):
                if lnk.get("type") == "text/html":
                    link = lnk.get("href", "")
                    break
            published = (entry.findtext("atom:published", "", ns) or "")[:10]

            lines.append(
                f"[{i}] {title}\n"
                f"    Autoren: {', '.join(authors)}{' et al.' if len(authors) == 3 else ''}\n"
                f"    Datum: {published}\n"
                f"    Abstract: {abstract[:300]}{'…' if len(abstract) > 300 else ''}\n"
                f"    Link: {link}\n"
            )

        return "\n".join(lines)

    except ET.ParseError as exc:
        return f"[XML-Parse-Fehler: {exc}]"
