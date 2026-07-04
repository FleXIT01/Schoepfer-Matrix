"""Tool: Moleküle, Targets und Bioaktivität via ChEMBL suchen.

ChEMBL (EMBL-EBI) ist die größte öffentliche Datenbank für bioaktive Moleküle
mit 2M+ Verbindungen und 19M+ Aktivitätsmessungen.
Die REST-API ist kostenlos und benötigt keinen API-Key.
https://chembl.gitbook.io/chembl-interface-documentation/web-services
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "aspirin", "search_type": "compound"}
DEFINITION = {
    "name": "chembl_search",
    "description": (
        "Sucht Moleküle, biologische Targets und Bioaktivitätsdaten in ChEMBL. "
        "Ideal für: Wirkstoffe, Inhibitoren, Proteintargets, Medikamenten-Forschung."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Name des Moleküls, Targets oder Wirkstoffs"},
            "search_type": {
                "type": "string",
                "description": "'compound' (Moleküle), 'target' (Proteine/Targets), 'activity' (Messwerte)",
            },
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5)"},
        },
        "required": ["query"],
    },
}

_BASE = "https://www.ebi.ac.uk/chembl/api/data"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
}


def chembl_search(query: str, search_type: str = "compound", max_results: int = 5) -> str:
    """Sucht in ChEMBL nach Molekülen oder Targets."""
    import httpx

    search_type = search_type.lower().strip()

    if search_type in ("compound", "molecule"):
        return _search_compounds(query, max_results, httpx)
    elif search_type == "target":
        return _search_targets(query, max_results, httpx)
    elif search_type == "activity":
        return _search_activity(query, max_results, httpx)
    else:
        # Standard: erst Compound, dann Target
        compound_result = _search_compounds(query, max_results, httpx)
        target_result = _search_targets(query, 3, httpx)
        return compound_result + "\n\n" + target_result


def _search_compounds(query: str, limit: int, httpx) -> str:
    try:
        resp = httpx.get(
            f"{_BASE}/molecule/search",
            params={"q": query, "limit": min(limit, 10), "format": "json"},
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[ChEMBL-Compound-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:
        return f"[ChEMBL-Verbindungsfehler: {exc}]"

    molecules = data.get("molecules", [])
    if not molecules:
        return f"[ChEMBL: Keine Moleküle für '{query}' gefunden]"

    lines = [f"ChEMBL Moleküle für '{query}': {len(molecules)} Ergebnis(se)\n"]
    for i, mol in enumerate(molecules, 1):
        name = mol.get("pref_name") or mol.get("molecule_chembl_id", "?")
        chembl_id = mol.get("molecule_chembl_id", "?")
        mol_type = mol.get("molecule_type", "?")
        props = mol.get("molecule_properties") or {}
        mw = props.get("full_mwt", "?")
        alogp = props.get("alogp", "?")
        hbd = props.get("hbd", "?")  # H-Brücken-Donor
        hba = props.get("hba", "?")  # H-Brücken-Akzeptor
        max_phase = mol.get("max_phase", "?")

        lines.append(
            f"[{i}] {name} ({chembl_id})\n"
            f"    Typ: {mol_type} | Molekulargewicht: {mw} Da | LogP: {alogp}\n"
            f"    H-Donor: {hbd} | H-Akzeptor: {hba} | Max. klinische Phase: {max_phase}\n"
            f"    Link: https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/\n"
        )

    return "\n".join(lines)


def _search_targets(query: str, limit: int, httpx) -> str:
    try:
        resp = httpx.get(
            f"{_BASE}/target/search",
            params={"q": query, "limit": min(limit, 10), "format": "json"},
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[ChEMBL-Target-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:
        return f"[ChEMBL-Target-Verbindungsfehler: {exc}]"

    targets = data.get("targets", [])
    if not targets:
        return f"[ChEMBL: Keine Targets für '{query}' gefunden]"

    lines = [f"ChEMBL Targets für '{query}': {len(targets)} Ergebnis(se)\n"]
    for i, target in enumerate(targets, 1):
        name = target.get("pref_name", "?")
        tid = target.get("target_chembl_id", "?")
        t_type = target.get("target_type", "?")
        organism = target.get("organism", "?")

        lines.append(
            f"[{i}] {name} ({tid})\n"
            f"    Typ: {t_type} | Organismus: {organism}\n"
            f"    Link: https://www.ebi.ac.uk/chembl/target_report_card/{tid}/\n"
        )

    return "\n".join(lines)


def _search_activity(query: str, limit: int, httpx) -> str:
    """Sucht Bioaktivitätsmessungen für ein Molekül oder Target."""
    try:
        resp = httpx.get(
            f"{_BASE}/activity",
            params={
                "molecule_chembl_id": query.upper(),
                "limit": min(limit, 10),
                "format": "json",
            },
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[ChEMBL-Activity-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:
        return f"[ChEMBL-Activity-Verbindungsfehler: {exc}]"

    activities = data.get("activities", [])
    if not activities:
        return f"[ChEMBL: Keine Aktivitätsdaten für '{query}']"

    lines = [f"ChEMBL Bioaktivität für '{query}': {len(activities)} Messung(en)\n"]
    for i, act in enumerate(activities, 1):
        target_name = act.get("target_pref_name", "?")
        activity_type = act.get("activity_type", "?")
        value = act.get("value", "?")
        units = act.get("units", "")
        assay_type = act.get("assay_type", "?")

        lines.append(
            f"[{i}] Target: {target_name}\n"
            f"    Typ: {activity_type} = {value} {units} | Assay: {assay_type}\n"
        )

    return "\n".join(lines)
