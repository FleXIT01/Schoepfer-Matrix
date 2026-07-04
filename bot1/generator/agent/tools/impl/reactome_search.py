"""Tool: Biologische Signal- und Stoffwechselwege via Reactome.

Reactome ist eine kuratierte Datenbank biologischer Pathways (Signalwege,
Stoffwechsel, Krankheitsmechanismen). Die Content-Service-API ist kostenlos
und benötigt keinen API-Key.
  https://reactome.org/ContentService/
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "apoptosis", "species": "Homo sapiens", "max_results": 5}
DEFINITION = {
    "name": "reactome_search",
    "description": (
        "Sucht biologische Pathways (Signalwege, Stoffwechsel) in Reactome. "
        "Liefert Pathway-Namen, Reactome-IDs und Typ. "
        "Ideal für: Mechanismen, Signalkaskaden, Krankheitswege, System-Biologie."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Pathway-/Gen-/Prozessname (z.B. 'apoptosis', 'EGFR signaling')"},
            "species": {"type": "string", "description": "Spezies (Standard: 'Homo sapiens')"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5)"},
        },
        "required": ["query"],
    },
}

_BASE = "https://reactome.org/ContentService"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
}


def reactome_search(query: str, species: str = "Homo sapiens", max_results: int = 5) -> str:
    """Sucht Pathways in Reactome."""
    import httpx

    try:
        resp = httpx.get(
            f"{_BASE}/search/query",
            params={
                "query": query.strip(),
                "species": species,
                "types": "Pathway",
                "cluster": "true",
            },
            timeout=20, headers=_HEADERS,
        )
        if resp.status_code == 404:
            return f"[Reactome: Keine Pathways für '{query}' gefunden]"
        if resp.status_code != 200:
            return f"[Reactome-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[Reactome-Verbindungsfehler: {exc}]"

    # Ergebnisse stecken in results[].entries[]
    entries: list[dict] = []
    for group in data.get("results", []):
        entries.extend(group.get("entries", []))
    if not entries:
        return f"[Reactome: Keine Pathways für '{query}']"

    limit = max(1, min(max_results, 10))
    lines = [f"Reactome Pathways für '{query}' ({species}): {len(entries)} Treffer (zeige {min(limit, len(entries))})\n"]
    for i, e in enumerate(entries[:limit], 1):
        name = _clean(e.get("name", "?"))
        st_id = e.get("stId") or e.get("id", "?")
        exact = e.get("exactType", e.get("typeName", "Pathway"))
        compartment = ", ".join(e.get("compartmentNames", [])[:2])
        lines.append(
            f"[{i}] {name} ({st_id})\n"
            f"    Typ: {exact}" + (f" | Kompartiment: {compartment}" if compartment else "") + "\n"
            f"    Diagramm: https://reactome.org/PathwayBrowser/#/{st_id}\n"
        )
    return "\n".join(lines)


def _clean(text: str) -> str:
    """Entfernt HTML-Hervorhebungs-Tags aus Reactome-Suchergebnissen."""
    import re
    return re.sub(r"</?[^>]+>", "", text).strip()
