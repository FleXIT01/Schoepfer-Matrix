"""Tool: Arzneimittel-Daten via openFDA (US Food & Drug Administration).

openFDA stellt offizielle FDA-Daten bereit: Arzneimittel-Beipackzettel
(Indikation, Warnungen, Wechselwirkungen) und gemeldete Nebenwirkungen.
Die API ist kostenlos und benötigt für moderate Nutzung keinen API-Key.
  https://open.fda.gov/apis/
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"drug": "ibuprofen", "data_type": "label", "max_results": 3}
DEFINITION = {
    "name": "openfda_search",
    "description": (
        "Fragt offizielle FDA-Arzneimitteldaten ab: 'label' (Indikation, Warnungen, "
        "Wechselwirkungen) oder 'event' (gemeldete Nebenwirkungen). "
        "Ideal für: Medikamenten-Sicherheit, Indikationen, Pharmakovigilanz."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "drug": {"type": "string", "description": "Wirkstoff-/Markenname (z.B. 'ibuprofen', 'aspirin')"},
            "data_type": {"type": "string", "description": "'label' (Beipackzettel) oder 'event' (Nebenwirkungen)"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 3)"},
        },
        "required": ["drug"],
    },
}

_BASE = "https://api.fda.gov/drug"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)", "Accept": "application/json"}


def openfda_search(drug: str, data_type: str = "label", max_results: int = 3) -> str:
    """Sucht Arzneimitteldaten in openFDA."""
    import httpx

    dt = data_type.lower().strip()
    if dt in ("event", "adverse", "events"):
        return _search_events(drug, max_results, httpx)
    return _search_label(drug, max_results, httpx)


def _search_label(drug: str, limit: int, httpx) -> str:
    try:
        resp = httpx.get(
            f"{_BASE}/label.json",
            params={
                "search": f'openfda.generic_name:"{drug}" openfda.brand_name:"{drug}"',
                "limit": max(1, min(limit, 5)),
            },
            timeout=20, headers=_HEADERS,
        )
        if resp.status_code == 404:
            return f"[openFDA: Kein Beipackzettel für '{drug}' gefunden]"
        if resp.status_code != 200:
            return f"[openFDA-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[openFDA-Verbindungsfehler: {exc}]"

    results = data.get("results", [])
    if not results:
        return f"[openFDA: Kein Beipackzettel für '{drug}']"

    lines = [f"openFDA Arzneimittel-Label für '{drug}': {len(results)} Eintrag/Einträge\n"]
    for i, r in enumerate(results, 1):
        fda = r.get("openfda", {})
        brand = ", ".join(fda.get("brand_name", [])[:3]) or "?"
        generic = ", ".join(fda.get("generic_name", [])[:3]) or "?"
        purpose = _first(r.get("purpose") or r.get("indications_and_usage"))
        warnings = _first(r.get("warnings") or r.get("boxed_warning"))
        interactions = _first(r.get("drug_interactions"))
        lines.append(
            f"[{i}] {brand}  (Wirkstoff: {generic})\n"
            f"    Indikation: {purpose[:250]}\n"
            + (f"    ⚠ Warnung: {warnings[:200]}\n" if warnings else "")
            + (f"    Wechselwirkungen: {interactions[:200]}\n" if interactions else "")
        )
    return "\n".join(lines)


def _search_events(drug: str, limit: int, httpx) -> str:
    """Aggregierte Nebenwirkungs-Häufigkeiten (count über reaction)."""
    try:
        resp = httpx.get(
            f"{_BASE}/event.json",
            params={
                "search": f'patient.drug.medicinalproduct:"{drug}"',
                "count": "patient.reaction.reactionmeddrapt.exact",
            },
            timeout=20, headers=_HEADERS,
        )
        if resp.status_code == 404:
            return f"[openFDA: Keine Nebenwirkungsdaten für '{drug}']"
        if resp.status_code != 200:
            return f"[openFDA-Event-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[openFDA-Verbindungsfehler: {exc}]"

    results = data.get("results", [])[:max(1, min(limit * 3, 15))]
    if not results:
        return f"[openFDA: Keine Nebenwirkungsdaten für '{drug}']"

    lines = [f"openFDA häufigste gemeldete Nebenwirkungen für '{drug}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"  {i:>2}. {r.get('term', '?')}: {r.get('count', 0):,} Meldungen")
    return "\n".join(lines)


def _first(field) -> str:
    if isinstance(field, list) and field:
        return str(field[0]).strip()
    if isinstance(field, str):
        return field.strip()
    return ""
