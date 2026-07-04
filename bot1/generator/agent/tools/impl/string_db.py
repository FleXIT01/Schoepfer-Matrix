"""Tool: Protein-Protein-Interaktionen via STRING-Datenbank abfragen.

STRING (EMBL) ist eine Datenbank bekannter und vorhergesagter Protein-Protein-
Interaktionen — funktionale Assoziationen aus Experimenten, Datenbanken und Text-Mining.
Die REST-API ist kostenlos und benötigt keinen API-Key.
  https://string-db.org/help/api/
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"gene": "TP53", "species": 9606, "max_partners": 10}
DEFINITION = {
    "name": "string_db",
    "description": (
        "Findet Protein-Protein-Interaktionspartner eines Gens/Proteins über STRING. "
        "Liefert Interaktionspartner mit Konfidenz-Score. "
        "Ideal für: Signalwege, Protein-Netzwerke, funktionale Assoziationen, Target-Kontext."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene": {"type": "string", "description": "Gen-/Proteinsymbol (z.B. 'TP53', 'EGFR')"},
            "species": {"type": "integer", "description": "NCBI Taxon-ID (Standard: 9606 = Mensch)"},
            "max_partners": {"type": "integer", "description": "Max. Interaktionspartner (Standard: 10)"},
        },
        "required": ["gene"],
    },
}

_BASE = "https://string-db.org/api"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}


def string_db(gene: str, species: int = 9606, max_partners: int = 10) -> str:
    """Holt Interaktionspartner eines Proteins aus STRING."""
    import httpx

    limit = max(1, min(max_partners, 25))
    try:
        resp = httpx.get(
            f"{_BASE}/json/interaction_partners",
            params={
                "identifiers": gene.strip(),
                "species": species,
                "limit": limit,
                "caller_identity": "omega_science_agent",
            },
            timeout=20, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[STRING-Fehler: HTTP {resp.status_code}]"
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[STRING-Verbindungsfehler: {exc}]"

    if not isinstance(data, list) or not data:
        return f"[STRING: Keine Interaktionspartner für '{gene}' (Spezies {species}) gefunden]"

    lines = [f"STRING Interaktionspartner für '{gene}': {len(data)} Partner\n"]
    for i, partner in enumerate(data, 1):
        name = partner.get("preferredName_B", "?")
        score = partner.get("score", 0)
        # Evidenz-Kanäle (0..1)
        exp = partner.get("escore", 0)
        db = partner.get("dscore", 0)
        text = partner.get("tscore", 0)
        lines.append(
            f"[{i}] {name} — Konfidenz: {float(score):.3f}\n"
            f"    Evidenz: Experiment={float(exp):.2f} | Datenbank={float(db):.2f} | Text-Mining={float(text):.2f}\n"
        )

    lines.append(
        f"\nNetzwerk-Bild: {_BASE}/image/network?identifiers={gene}&species={species}"
    )
    return "\n".join(lines)
