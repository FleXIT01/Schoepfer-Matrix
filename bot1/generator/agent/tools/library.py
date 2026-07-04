"""Registry der geprüften Tool-Implementierungen.

Jeder Eintrag liefert den Funktions-Quelltext (per inspect.getsource), die
Tool-Definition fürs Provider-Format, Beispiel-Input und benötigte Imports.
Die impl/-Module sind die einzige Quelle der Wahrheit.
"""
from __future__ import annotations

import inspect
import textwrap
from dataclasses import dataclass, field

from .impl import (
    http_request as _http_request,
    read_file as _read_file,
    run_python as _run_python,
    sqlite_store as _sqlite_store,
    web_fetch as _web_fetch,
    write_file as _write_file,
    # Wissenschaft & Daten (externe REST-APIs, kein Key nötig)
    arxiv_search as _arxiv_search,
    openalex_search as _openalex_search,
    pubmed_search as _pubmed_search,
    europepmc_search as _europepmc_search,
    alphafold_fetch as _alphafold_fetch,
    rcsb_pdb as _rcsb_pdb,
    chembl_search as _chembl_search,
    string_db as _string_db,
    ensembl_lookup as _ensembl_lookup,
    reactome_search as _reactome_search,
    openfda_search as _openfda_search,
    # Welt-Interaktion
    generate_image as _generate_image,
)


@dataclass
class ToolEntry:
    name: str
    func_source: str            # der vollständige `def ...():` Block
    sample_input: dict
    definition: dict            # {"name","description","input_schema"}
    imports: list[str] = field(default_factory=list)


def _entry_from_module(module, func_name: str) -> ToolEntry:
    func = getattr(module, func_name)
    src = textwrap.dedent(inspect.getsource(func)).strip("\n")
    return ToolEntry(
        name=func_name,
        func_source=src,
        sample_input=dict(getattr(module, "SAMPLE_INPUT", {})),
        definition=dict(getattr(module, "DEFINITION", {})),
        imports=list(getattr(module, "REQUIRED_IMPORTS", [])),
    )


# capability-key → ToolEntry
LIBRARY: dict[str, ToolEntry] = {
    "read_file": _entry_from_module(_read_file, "read_file"),
    "write_file": _entry_from_module(_write_file, "write_file"),
    "run_python": _entry_from_module(_run_python, "run_python"),
    "web_fetch": _entry_from_module(_web_fetch, "web_fetch"),
    "http_request": _entry_from_module(_http_request, "http_request"),
    "sqlite_store": _entry_from_module(_sqlite_store, "sqlite_store"),
    # Wissenschaft & Daten (für generierte Bots der Software Factory)
    "arxiv_search": _entry_from_module(_arxiv_search, "arxiv_search"),
    "openalex_search": _entry_from_module(_openalex_search, "openalex_search"),
    "pubmed_search": _entry_from_module(_pubmed_search, "pubmed_search"),
    "europepmc_search": _entry_from_module(_europepmc_search, "europepmc_search"),
    "alphafold_fetch": _entry_from_module(_alphafold_fetch, "alphafold_fetch"),
    "rcsb_pdb": _entry_from_module(_rcsb_pdb, "rcsb_pdb"),
    "chembl_search": _entry_from_module(_chembl_search, "chembl_search"),
    "string_db": _entry_from_module(_string_db, "string_db"),
    "ensembl_lookup": _entry_from_module(_ensembl_lookup, "ensembl_lookup"),
    "reactome_search": _entry_from_module(_reactome_search, "reactome_search"),
    "openfda_search": _entry_from_module(_openfda_search, "openfda_search"),
    # Welt-Interaktion
    "generate_image": _entry_from_module(_generate_image, "generate_image"),
}


def available_capabilities() -> list[str]:
    return sorted(LIBRARY.keys())


def get(capability: str) -> ToolEntry | None:
    return LIBRARY.get(capability)


def capability_catalog() -> str:
    """Kurzkatalog für den ArchitectAgent-Prompt: 'key — Beschreibung'."""
    lines = []
    for key, entry in sorted(LIBRARY.items()):
        desc = entry.definition.get("description", "")
        lines.append(f"- {key} — {desc}")
    return "\n".join(lines)
