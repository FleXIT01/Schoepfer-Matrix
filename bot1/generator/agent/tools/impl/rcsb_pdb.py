"""Tool: 3D-Protein-Strukturen via RCSB Protein Data Bank (PDB) suchen.

Die RCSB PDB ist das weltweite Archiv für experimentell bestimmte
3D-Strukturen von Proteinen, DNA und RNA (Röntgenkristallografie, Kryo-EM, NMR).
Die REST-API ist kostenlos und benötigt keinen API-Key.
  Such-API:  https://search.rcsb.org/rcsbsearch/v2/query
  Daten-API: https://data.rcsb.org/rest/v1/core/entry/{id}
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "EGFR kinase", "max_results": 5}
DEFINITION = {
    "name": "rcsb_pdb",
    "description": (
        "Sucht experimentell bestimmte 3D-Strukturen (Röntgen, Kryo-EM, NMR) in der "
        "RCSB Protein Data Bank. Liefert PDB-IDs, Auflösung, Methode und Titel. "
        "Ideal für: reale Kristallstrukturen, Protein-Liganden-Komplexe, Struktur-Biologie."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Protein-/Strukturname (z.B. 'EGFR kinase', 'hemoglobin')"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5)"},
        },
        "required": ["query"],
    },
}

_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
_DATA = "https://data.rcsb.org/rest/v1/core/entry"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def rcsb_pdb(query: str, max_results: int = 5) -> str:
    """Sucht 3D-Strukturen in der RCSB PDB."""
    import httpx

    limit = max(1, min(max_results, 10))
    payload = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": query},
        },
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": limit}},
    }

    try:
        resp = httpx.post(_SEARCH, json=payload, timeout=20, headers=_HEADERS)
        if resp.status_code == 204:
            return f"[PDB: Keine Strukturen für '{query}' gefunden]"
        if resp.status_code != 200:
            return f"[PDB-Suchfehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[PDB-Verbindungsfehler: {exc}]"

    results = data.get("result_set", [])
    if not results:
        return f"[PDB: Keine Strukturen für '{query}' gefunden]"

    lines = [f"RCSB PDB Strukturen für '{query}': {data.get('total_count', len(results))} Treffer (zeige {len(results)})\n"]
    for i, hit in enumerate(results, 1):
        pdb_id = hit.get("identifier", "?")
        detail = _fetch_entry(pdb_id, httpx)
        lines.append(
            f"[{i}] PDB {pdb_id} — {detail['title']}\n"
            f"    Methode: {detail['method']} | Auflösung: {detail['resolution']}\n"
            f"    3D-Viewer: https://www.rcsb.org/3d-view/{pdb_id}\n"
            f"    Download: https://files.rcsb.org/download/{pdb_id}.pdb\n"
        )

    return "\n".join(lines)


def _fetch_entry(pdb_id: str, httpx) -> dict:
    """Holt Metadaten (Titel, Methode, Auflösung) für eine PDB-ID."""
    out = {"title": "?", "method": "?", "resolution": "?"}
    try:
        resp = httpx.get(f"{_DATA}/{pdb_id}", timeout=12, headers=_HEADERS)
        if resp.status_code != 200:
            return out
        d = resp.json()
        struct = d.get("struct") or {}
        out["title"] = (struct.get("title") or "?")[:90]
        methods = d.get("exptl") or []
        if methods:
            out["method"] = methods[0].get("method", "?")
        res = (d.get("rcsb_entry_info") or {}).get("resolution_combined")
        if res:
            out["resolution"] = f"{res[0]} Å"
    except Exception:  # noqa: BLE001
        pass
    return out
