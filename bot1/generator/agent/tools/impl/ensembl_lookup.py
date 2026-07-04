"""Tool: Gen-, Transkript- und Varianten-Daten via Ensembl REST-API.

Ensembl (EMBL-EBI) liefert annotierte Genome: Gen-Koordinaten, Biotyp,
Beschreibung, Transkripte und (für Varianten) klinische Bedeutung.
Die REST-API ist kostenlos und benötigt keinen API-Key.
  https://rest.ensembl.org/
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"symbol": "BRCA2", "species": "homo_sapiens"}
DEFINITION = {
    "name": "ensembl_lookup",
    "description": (
        "Schlägt ein Gen (per Symbol) oder eine Variante (rsID) in Ensembl nach. "
        "Liefert Gen-ID, Lokus, Biotyp, Beschreibung bzw. klinische Variant-Konsequenzen. "
        "Ideal für: Genom-Koordinaten, Gen-Annotation, SNP/Varianten-Bedeutung (dbSNP/ClinVar)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Gen-Symbol (z.B. 'BRCA2') ODER rsID einer Variante (z.B. 'rs699')"},
            "species": {"type": "string", "description": "Spezies (Standard: 'homo_sapiens')"},
        },
        "required": ["symbol"],
    },
}

_BASE = "https://rest.ensembl.org"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def ensembl_lookup(symbol: str, species: str = "homo_sapiens") -> str:
    """Sucht Gen- oder Varianten-Informationen in Ensembl."""
    import httpx

    sym = symbol.strip()
    # rsID → Varianten-Endpunkt
    if sym.lower().startswith("rs") and sym[2:].isdigit():
        return _lookup_variant(sym, species, httpx)
    return _lookup_gene(sym, species, httpx)


def _lookup_gene(symbol: str, species: str, httpx) -> str:
    try:
        resp = httpx.get(
            f"{_BASE}/lookup/symbol/{species}/{symbol}",
            params={"expand": 1},
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code == 400:
            return f"[Ensembl: Gen '{symbol}' in '{species}' nicht gefunden]"
        if resp.status_code != 200:
            return f"[Ensembl-Fehler: HTTP {resp.status_code}]"
        d = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[Ensembl-Verbindungsfehler: {exc}]"

    gene_id = d.get("id", "?")
    transcripts = d.get("Transcript", []) or []
    lines = [
        f"Ensembl Gen '{symbol}' ({species}):",
        f"  Ensembl-ID:    {gene_id}",
        f"  Beschreibung:  {d.get('description', '?')}",
        f"  Biotyp:        {d.get('biotype', '?')}",
        f"  Lokus:         Chr {d.get('seq_region_name', '?')}:"
        f"{d.get('start', '?')}-{d.get('end', '?')} (Strang {d.get('strand', '?')})",
        f"  Transkripte:   {len(transcripts)}",
        f"  Browser:       https://www.ensembl.org/{species}/Gene/Summary?g={gene_id}",
    ]
    if transcripts:
        canonical = [t for t in transcripts if t.get("is_canonical")]
        t = (canonical or transcripts)[0]
        lines.append(
            f"  Haupttranskript: {t.get('id', '?')} ({t.get('biotype', '?')})"
        )
    return "\n".join(lines)


def _lookup_variant(rsid: str, species: str, httpx) -> str:
    try:
        resp = httpx.get(
            f"{_BASE}/variation/{species}/{rsid}",
            params={"content-type": "application/json"},
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[Ensembl-Variant-Fehler: HTTP {resp.status_code} für {rsid}]"
        d = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"[Ensembl-Verbindungsfehler: {exc}]"

    mappings = d.get("mappings", []) or []
    clin = d.get("clinical_significance", []) or []
    synonyms = d.get("synonyms", []) or []
    lines = [
        f"Ensembl Variante '{rsid}' ({species}):",
        f"  Konsequenz:           {d.get('most_severe_consequence', '?')}",
        f"  Klinische Bedeutung:  {', '.join(clin) if clin else 'keine Angabe'}",
        f"  MAF (Minor Allele):   {d.get('MAF', '?')} ({d.get('minor_allele', '?')})",
        f"  Allele/Ambiguity:     {d.get('ambiguity', '?')}",
    ]
    if mappings:
        m = mappings[0]
        lines.append(f"  Position:             {m.get('location', '?')} ({m.get('allele_string', '?')})")
    if synonyms:
        lines.append(f"  Synonyme:             {', '.join(synonyms[:5])}")
    lines.append(f"  dbSNP:                https://www.ncbi.nlm.nih.gov/snp/{rsid}")
    return "\n".join(lines)
