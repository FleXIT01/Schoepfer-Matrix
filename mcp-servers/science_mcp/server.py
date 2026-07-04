"""science-mcp — Bio-Wissenschafts-Tools als MCP-Server.

Das Alleinstellungsmerkmal der Schöpfer-Matrix: 11 kostenlose wissenschaftliche
REST-APIs (kein API-Key nötig), die OpenClaw NICHT nativ hat. Macht die
bereits getesteten Tools aus bot1/generator/agent/tools/impl über das
Model-Context-Protocol für OpenClaw (und jeden MCP-Client) verfügbar.

Start (stdio):   python server.py
Registrieren in OpenClaw via mcporter / mcp.json (siehe openclaw-workspace/mcp.json).
"""
from __future__ import annotations

import sys
from pathlib import Path

# bot1 auf den Pfad legen (dort liegen die getesteten Tool-Implementierungen)
_BOT1 = Path(__file__).resolve().parents[2] / "bot1"
if str(_BOT1) not in sys.path:
    sys.path.insert(0, str(_BOT1))

from mcp.server.fastmcp import FastMCP

from generator.agent.tools.impl.arxiv_search import arxiv_search as _arxiv
from generator.agent.tools.impl.openalex_search import openalex_search as _openalex
from generator.agent.tools.impl.pubmed_search import pubmed_search as _pubmed
from generator.agent.tools.impl.europepmc_search import europepmc_search as _europepmc
from generator.agent.tools.impl.alphafold_fetch import alphafold_fetch as _alphafold
from generator.agent.tools.impl.rcsb_pdb import rcsb_pdb as _rcsb
from generator.agent.tools.impl.chembl_search import chembl_search as _chembl
from generator.agent.tools.impl.string_db import string_db as _string
from generator.agent.tools.impl.ensembl_lookup import ensembl_lookup as _ensembl
from generator.agent.tools.impl.reactome_search import reactome_search as _reactome
from generator.agent.tools.impl.openfda_search import openfda_search as _openfda

mcp = FastMCP("science-mcp")


@mcp.tool()
def arxiv_search(query: str, max_results: int = 5, category: str = "") -> str:
    """Wissenschaftliche Paper auf arXiv suchen (KI, Physik, Biologie, Mathematik).
    Für: Preprints, neueste Methoden, technische Grundlagen."""
    return _arxiv(query, max_results=max_results, category=category)


@mcp.tool()
def openalex_search(query: str, max_results: int = 5, filter_year: int = 0) -> str:
    """250M+ wissenschaftliche Werke in OpenAlex durchsuchen (alle Disziplinen),
    mit Zitationszahlen. Für: breite Literatur-Übersicht, Impact-Einschätzung."""
    return _openalex(query, max_results=max_results, filter_year=filter_year)


@mcp.tool()
def pubmed_search(query: str, max_results: int = 5, filter: str = "") -> str:
    """35M+ medizinische/biologische Paper in PubMed/NCBI mit Abstracts.
    Für: klinische Forschung, Medizin, Molekularbiologie."""
    return _pubmed(query, max_results=max_results, filter=filter)


@mcp.tool()
def europepmc_search(query: str, max_results: int = 5, preprints_only: bool = False) -> str:
    """Biomedizinische Literatur UND Preprints (bioRxiv/medRxiv) über Europe PMC.
    Für: allerneueste, teils unveröffentlichte Forschung."""
    return _europepmc(query, max_results=max_results, preprints_only=preprints_only)


@mcp.tool()
def alphafold_fetch(uniprot_id: str, include_pdb_url: bool = True) -> str:
    """Vorhergesagte 3D-Proteinstruktur aus AlphaFold per UniProt-ID (z.B. P00533=EGFR).
    Für: Proteinform, Domänen, Strukturbiologie."""
    return _alphafold(uniprot_id, include_pdb_url=include_pdb_url)


@mcp.tool()
def rcsb_pdb(query: str, max_results: int = 5) -> str:
    """Experimentell bestimmte 3D-Strukturen (Röntgen/Kryo-EM/NMR) in der RCSB PDB.
    Für: reale Kristallstrukturen, Protein-Liganden-Komplexe."""
    return _rcsb(query, max_results=max_results)


@mcp.tool()
def chembl_search(query: str, search_type: str = "compound", max_results: int = 5) -> str:
    """Moleküle, Targets und Bioaktivität in ChEMBL (search_type: compound|target|activity).
    Für: Wirkstoffe, Inhibitoren, Drug-Discovery, klinische Phasen."""
    return _chembl(query, search_type=search_type, max_results=max_results)


@mcp.tool()
def string_db(gene: str, species: int = 9606, max_partners: int = 10) -> str:
    """Protein-Protein-Interaktionspartner eines Gens über STRING (9606=Mensch).
    Für: Signalnetzwerke, funktionale Assoziationen, Target-Kontext."""
    return _string(gene, species=species, max_partners=max_partners)


@mcp.tool()
def ensembl_lookup(symbol: str, species: str = "homo_sapiens") -> str:
    """Gen-Annotation per Symbol ODER Varianten-Bedeutung per rsID (z.B. 'rs699') über Ensembl.
    Für: Genom-Koordinaten, Biotyp, SNP/Varianten-Konsequenzen (dbSNP/ClinVar)."""
    return _ensembl(symbol, species=species)


@mcp.tool()
def reactome_search(query: str, species: str = "Homo sapiens", max_results: int = 5) -> str:
    """Biologische Signal-/Stoffwechselwege (Pathways) in Reactome suchen.
    Für: Mechanismen, Signalkaskaden, Krankheitswege, Systembiologie."""
    return _reactome(query, species=species, max_results=max_results)


@mcp.tool()
def openfda_search(drug: str, data_type: str = "label", max_results: int = 3) -> str:
    """Offizielle FDA-Arzneimitteldaten: data_type 'label' (Indikation/Warnungen) oder
    'event' (gemeldete Nebenwirkungen). Für: Medikamenten-Sicherheit, Pharmakovigilanz."""
    return _openfda(drug, data_type=data_type, max_results=max_results)


if __name__ == "__main__":
    mcp.run()
