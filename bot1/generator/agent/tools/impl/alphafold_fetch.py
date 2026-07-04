"""Tool: Protein-Strukturdaten via EBI AlphaFold API abrufen.

AlphaFold (DeepMind/EBI) hat 200M+ Protein-Strukturen berechnet.
Die API ist kostenlos und benötigt keinen API-Key.
https://alphafold.ebi.ac.uk/api-docs
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"uniprot_id": "P00533"}  # EGFR (Epidermal Growth Factor Receptor)
DEFINITION = {
    "name": "alphafold_fetch",
    "description": (
        "Ruft Protein-Strukturdaten aus der AlphaFold-Datenbank ab (200M+ Strukturen). "
        "Benötigt eine UniProt-ID (z.B. 'P00533' für EGFR). "
        "Gibt Konfidenz-Score, 3D-Struktur-URL und funktionelle Annotation zurück."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "uniprot_id": {"type": "string", "description": "UniProt Accession ID (z.B. 'P00533')"},
            "include_pdb_url": {"type": "boolean", "description": "PDB-Download-URL einschließen (Standard: True)"},
        },
        "required": ["uniprot_id"],
    },
}

_AF_BASE = "https://alphafold.ebi.ac.uk/api"
_UNIPROT_BASE = "https://rest.uniprot.org/uniprotkb"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)", "Accept": "application/json"}


def alphafold_fetch(uniprot_id: str, include_pdb_url: bool = True) -> str:
    """Ruft AlphaFold-Strukturdaten und UniProt-Annotation für ein Protein ab."""
    import httpx

    uid = uniprot_id.strip().upper()

    # 1) AlphaFold API: Struktur-Metadaten
    af_result = _fetch_alphafold(uid, httpx)

    # 2) UniProt REST API: funktionelle Annotation
    uniprot_result = _fetch_uniprot(uid, httpx)

    lines = [f"Protein-Analyse: UniProt-ID {uid}\n"]
    lines.append(af_result)
    lines.append(uniprot_result)
    return "\n".join(lines)


def _fetch_alphafold(uid: str, httpx) -> str:
    """AlphaFold Struktur-Metadaten."""
    try:
        resp = httpx.get(
            f"{_AF_BASE}/prediction/{uid}",
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code == 404:
            return f"[AlphaFold: Kein Strukturmodell für {uid} gefunden]"
        if resp.status_code != 200:
            return f"[AlphaFold-Fehler: HTTP {resp.status_code}]"

        data = resp.json()
        if not data:
            return "[AlphaFold: Leere Antwort]"

        entry = data[0] if isinstance(data, list) else data
        lines = ["== AlphaFold Strukturmodell =="]
        lines.append(f"Modell-ID: {entry.get('entryId', '?')}")
        lines.append(f"Organismus: {entry.get('organismScientificName', '?')}")
        lines.append(f"Gen: {entry.get('gene', '?')}")
        lines.append(f"Protein-Name: {entry.get('uniprotDescription', '?')}")
        lines.append(f"Sequenzlänge: {entry.get('sequenceLength', '?')} Aminosäuren")
        lines.append(f"Modell-Konfidenz (pLDDT): {entry.get('confidenceAvgLocalScore', '?')}")
        lines.append(f"Modell-URL (CIF): {entry.get('cifUrl', '?')}")
        lines.append(f"Modell-URL (PDB): {entry.get('pdbUrl', '?')}")
        lines.append(f"3D-Viewer: https://alphafold.ebi.ac.uk/entry/{uid}")
        return "\n".join(lines)

    except Exception as exc:
        return f"[AlphaFold-Verbindungsfehler: {exc}]"


def _fetch_uniprot(uid: str, httpx) -> str:
    """UniProt funktionelle Annotation."""
    try:
        resp = httpx.get(
            f"{_UNIPROT_BASE}/{uid}",
            params={"format": "json"},
            timeout=15, headers=_HEADERS,
        )
        if resp.status_code != 200:
            return f"[UniProt: HTTP {resp.status_code} für {uid}]"

        data = resp.json()
        lines = ["\n== UniProt Funktionelle Annotation =="]

        # Protein-Name
        prot = data.get("proteinDescription", {})
        rec = prot.get("recommendedName", {})
        full_name = rec.get("fullName", {}).get("value", "?")
        lines.append(f"Name: {full_name}")

        # Organismus
        org = data.get("organism", {})
        lines.append(f"Organismus: {org.get('scientificName', '?')} ({org.get('commonName', '')})")

        # Funktion
        comments = data.get("comments", [])
        for comment in comments:
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    func_text = texts[0].get("value", "")
                    lines.append(f"Funktion: {func_text[:400]}{'…' if len(func_text) > 400 else ''}")
                    break

        # Krankheits-Assoziationen
        diseases = [c for c in comments if c.get("commentType") == "DISEASE"]
        if diseases:
            lines.append(f"Assoziierte Krankheiten ({len(diseases)}):")
            for d in diseases[:3]:
                disease = d.get("disease", {})
                lines.append(f"  • {disease.get('diseaseId', '?')}: {disease.get('description', '')[:200]}")

        # Gene
        genes = data.get("genes", [])
        gene_names = [g.get("geneName", {}).get("value", "") for g in genes if g.get("geneName")]
        if gene_names:
            lines.append(f"Gene: {', '.join(gene_names)}")

        lines.append(f"UniProt-Link: https://www.uniprot.org/uniprotkb/{uid}")
        return "\n".join(lines)

    except Exception as exc:
        return f"[UniProt-Verbindungsfehler: {exc}]"
