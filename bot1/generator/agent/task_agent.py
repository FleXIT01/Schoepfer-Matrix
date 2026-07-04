"""TaskAgent: Führt beliebige Aufgaben mit einem ReAct-Loop aus.

Arbeitsweise (Denken → Handeln → Beobachten):
  1. LLM überlegt, was der nächste Schritt ist.
  2. LLM ruft ein Tool per JSON-Format auf.
  3. Ergebnis kommt zurück als Beobachtung.
  4. Schleife, bis DONE oder max_steps erreicht.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

from .tools.impl.web_fetch import web_fetch
from .tools.impl.write_file import write_file
from .tools.impl.read_file import read_file
from .tools.impl.run_python import run_python
from .tools.impl.web_search import web_search
from .tools.impl.arxiv_search import arxiv_search
from .tools.impl.openalex_search import openalex_search
from .tools.impl.pubmed_search import pubmed_search
from .tools.impl.alphafold_fetch import alphafold_fetch
from .tools.impl.chembl_search import chembl_search
from .tools.impl.rcsb_pdb import rcsb_pdb
from .tools.impl.string_db import string_db
from .tools.impl.europepmc_search import europepmc_search
from .tools.impl.ensembl_lookup import ensembl_lookup
from .tools.impl.openfda_search import openfda_search
from .tools.impl.reactome_search import reactome_search
from .tools.impl.browser_control import (
    browser_open, browser_click, browser_extract_text, browser_screenshot,
)
from .tools.impl.generate_image import generate_image

TOOLS: dict[str, Callable] = {
    "web_search": web_search,
    "web_fetch": web_fetch,
    "write_file": write_file,
    "read_file": read_file,
    "run_python": run_python,
    "arxiv_search": arxiv_search,
    "openalex_search": openalex_search,
    "pubmed_search": pubmed_search,
    "alphafold_fetch": alphafold_fetch,
    "chembl_search": chembl_search,
    "rcsb_pdb": rcsb_pdb,
    "string_db": string_db,
    "europepmc_search": europepmc_search,
    "ensembl_lookup": ensembl_lookup,
    "openfda_search": openfda_search,
    "reactome_search": reactome_search,
    "browser_open": browser_open,
    "browser_click": browser_click,
    "browser_extract_text": browser_extract_text,
    "browser_screenshot": browser_screenshot,
    "generate_image": generate_image,
}

_SYSTEM = """\
Du bist ein autonomer Task-Ausführungsagent. Du löst Aufgaben Schritt für Schritt \
mithilfe von Tools.

VERFÜGBARE TOOLS:

Web & Tech:
• web_search(query)              — GitHub-Dokumentation abrufen (README, CHANGELOG, Releases).
                                   Für: Bibliotheken, APIs, Modell-Infos, Tech-Dokumentation.
• web_fetch(url)                 — Beliebige URL direkt laden (GitHub Raw, JSON-APIs).
• run_python(code)               — Python-Code ausführen (15s Timeout), stdout zurück.
                                    ⚠️ KEIN input() verwenden — der Subprozess hat kein Terminal!
                                    ⚠️ Wenn ein Code 3x den gleichen Fehler wirft: anderen Ansatz wählen.

Dateien:
• write_file(path, content)      — Text in Datei schreiben (Ordner werden erstellt).
• read_file(path)                — Lokale Datei lesen.

Wissenschaft — Literatur (kostenlos, kein API-Key):
• arxiv_search(query, max_results=5, category="")
                                 — Wissenschaftliche Paper auf ArXiv (KI, Physik, Biologie...).
• openalex_search(query, max_results=5, filter_year=0)
                                 — 250M+ Werke in OpenAlex (Medizin, Biologie, Chemie...).
• pubmed_search(query, max_results=5, filter="")
                                 — 35M+ medizinische Paper in PubMed/NCBI.
• europepmc_search(query, max_results=5, preprints_only=False)
                                 — Literatur + bioRxiv/medRxiv-Preprints (neueste Forschung).

Wissenschaft — Molekül/Gen/Protein:
• alphafold_fetch(uniprot_id)    — Vorhergesagte Protein-3D-Struktur (z.B. uniprot_id="P00533").
• rcsb_pdb(query, max_results=5) — Experimentelle 3D-Strukturen (PDB: Röntgen/Kryo-EM).
• chembl_search(query, search_type="compound", max_results=5)
                                 — Moleküle/Targets in ChEMBL (search_type: compound|target|activity).
• string_db(gene, species=9606, max_partners=10)
                                 — Protein-Protein-Interaktionspartner (Signalnetzwerke).
• ensembl_lookup(symbol, species="homo_sapiens")
                                 — Gen-Annotation (Symbol) ODER Varianten-Bedeutung (rsID, z.B. "rs699").
• reactome_search(query, species="Homo sapiens", max_results=5)
                                 — Biologische Pathways/Signalwege.
• openfda_search(drug, data_type="label", max_results=3)
                                 — FDA-Arzneimitteldaten (data_type: label|event = Nebenwirkungen).

Welt-Interaktion (Browser & Bild):
• browser_open(url, headless=True) — Webseite im echten Browser öffnen, Titel + Text zurück.
• browser_click(selector)        — Element klicken (CSS-Selektor oder text=...).
• browser_extract_text(selector="body", max_chars=3000) — Sichtbaren Text auslesen.
• browser_screenshot(path="")    — Screenshot als PNG speichern.
• generate_image(prompt, width=768, height=768) — Bild/UI-Mockup via ComfyUI erzeugen.

ANTWORTFORMAT — wähle immer genau eines der zwei Formate:

Wenn du einen Tool-Aufruf machen willst:
THOUGHT: <eine Zeile: was du tust und warum>
ACTION: {"tool": "tool_name", "params": {"param1": "wert1", "param2": "wert2"}}

Wenn die Aufgabe vollständig erledigt ist:
DONE: <ein Satz: was wurde getan>

REGELN:
- Antworte AUSSCHLIESSLICH in diesem Format, kein Freitext davor oder danach.
- Behaupte NIE, etwas getan zu haben, ohne das Tool wirklich aufzurufen.
  Eine Datei gilt erst als gespeichert, wenn du write_file AUFGERUFEN hast.
- Wenn du recherchierte Infos speichern sollst: erst mit web_search/web_fetch suchen,
  dann den TATSÄCHLICHEN, AUSFÜHRLICHEN Inhalt (mehrere Absätze aus den Funden) per
  write_file schreiben — kein kurzer Platzhalter, kein leeres JSON.
- Für mehrzeiligen Inhalt in write_file: \\n in JSON-Strings nutzen.
- Für wissenschaftliche Fragen: arxiv_search, pubmed_search oder openalex_search nutzen.
- Für Protein-Infos: erst alphafold_fetch (braucht UniProt-ID), ggf. vorher chembl_search für die ID.
"""

_MAX_OBS = 4000


class TaskAgent:
    """ReAct-Agent der Aufgaben durch direkten Tool-Aufruf löst."""

    def __init__(self, llm, max_steps: int = 14) -> None:
        self._llm = llm
        self._max_steps = max_steps

    def run(self, task: str, progress: Callable[[str], None] | None = None) -> str:
        """Führt die Aufgabe aus. Gibt eine kurze Zusammenfassung zurück."""
        from ..llm.base import LLMMessage

        say = progress or (lambda _m: None)
        messages: list[LLMMessage] = [
            LLMMessage(role="user", content=f"Aufgabe: {task}")
        ]
        observation = ""
        tools_used: set[str] = set()
        gate_corrections = 0
        last_fail: tuple[str, str] = ("", "")
        fail_count = 0

        for step in range(1, self._max_steps + 1):
            try:
                raw = self._llm.chat(
                    messages=messages,
                    system=_SYSTEM,
                    temperature=0.1,
                    max_tokens=1024,
                ).strip()
            except Exception as exc:
                return f"[LLM-Fehler: {exc}]"

            # THOUGHT / ACTION / DONE parsen (DONE auch nach THOUGHT erkennen)
            thought_m = re.search(
                r"(?i)THOUGHT\s*:\s*(.+?)(?=\n\s*ACTION|\n\s*DONE|\Z)", raw, re.DOTALL
            )
            action_m = re.search(
                r"(?i)ACTION\s*:\s*(\{.+\})", raw, re.DOTALL
            )
            done_m = re.search(
                r"(?i)(?:^|\n)\s*DONE\s*:\s*(.+)", raw, re.DOTALL
            )

            if thought_m:
                say(f"💭 {thought_m.group(1).strip()[:120]}")

            # ACTION hat Vorrang: erst handeln, erst wenn keine Aktion mehr → DONE.
            if not action_m:
                if done_m:
                    result = done_m.group(1).strip()
                    # Completion-Gate: hat das Modell wirklich getan, was es behauptet?
                    gate = _completion_gate(task, tools_used)
                    if gate and gate_corrections < 2:
                        gate_corrections += 1
                        say(f"⛔ {gate[:100]}")
                        messages.append(LLMMessage(role="assistant", content=raw))
                        messages.append(LLMMessage(role="user", content=gate))
                        continue
                    say(f"✅ {result}")
                    return result

                # Weder ACTION noch DONE → Format-Erinnerung
                messages.append(LLMMessage(role="assistant", content=raw))
                messages.append(LLMMessage(
                    role="user",
                    content=(
                        "Halte dich bitte strikt an das Format:\n"
                        "THOUGHT: ...\nACTION: {\"tool\": \"...\", \"params\": {...}}\n"
                        "oder: DONE: ..."
                    ),
                ))
                continue

            # JSON parsen
            try:
                action = json.loads(action_m.group(1))
                tool_name: str = action.get("tool", "")
                params: dict = action.get("params", {})
            except json.JSONDecodeError as exc:
                observation = f"[JSON-Fehler: {exc}]"
                say(f"❌ {observation}")
                messages.append(LLMMessage(role="assistant", content=raw))
                messages.append(LLMMessage(role="user", content=f"OBSERVATION: {observation}"))
                continue

            if tool_name not in TOOLS:
                observation = (
                    f"[Unbekanntes Tool '{tool_name}'. "
                    f"Verfügbar: {', '.join(TOOLS)}]"
                )
                say(f"❌ {observation}")
            else:
                preview = ", ".join(
                    f"{k}={repr(v)[:40]}" for k, v in params.items()
                )
                say(f"🔧 {tool_name}({preview})")
                call_ok = True
                try:
                    raw_obs: str = TOOLS[tool_name](**params)
                except TypeError as exc:
                    raw_obs = f"[Parameter-Fehler: {exc}]"
                    call_ok = False
                except Exception as exc:  # noqa: BLE001
                    raw_obs = f"[Tool-Fehler: {exc}]"
                    call_ok = False

                # Tool-Aufruf vermerken (für das Completion-Gate), sofern kein Fehler.
                # Achtung: write_file liefert "[OK: … geschrieben]" — das ist KEIN Fehler.
                if call_ok and not raw_obs.lstrip().startswith(_ERROR_PREFIXES):
                    tools_used.add(tool_name)

                if len(raw_obs) > _MAX_OBS:
                    observation = (
                        raw_obs[:_MAX_OBS]
                        + f"\n[... {len(raw_obs)} Zeichen gesamt, Inhalt gekürzt]"
                    )
                else:
                    observation = raw_obs

                first = observation.split("\n")[0][:120]
                say(f"   → {first}{'…' if len(observation) > 120 else ''}")

                # Loop-Detection: gleicher Tool+Fehler 3x → abbrechen
                fail_sig = (tool_name, observation[:80])
                if not call_ok or observation.startswith(_ERROR_PREFIXES):
                    if fail_sig == last_fail:
                        fail_count += 1
                        if fail_count >= 3:
                            observation += (
                                "\n\n⚠️ Derselbe Fehler 3x. Das ist eine Endlos-Schleife. "
                                "Wähle einen ANDEREN Ansatz oder breche mit DONE ab."
                            )
                    else:
                        last_fail = fail_sig
                        fail_count = 1

            messages.append(LLMMessage(role="assistant", content=raw))
            messages.append(LLMMessage(role="user", content=f"OBSERVATION: {observation}"))

        say(f"⚠️ Maximale Schritte ({self._max_steps}) erreicht.")
        return f"[Abgebrochen nach {self._max_steps} Schritten]"


# ── Completion-Gate ───────────────────────────────────────────────────────────

# Präfixe, an denen eine Tool-Antwort als Fehler erkannt wird.
_ERROR_PREFIXES = (
    "[Fehler", "[Tool-Fehler", "[Parameter-Fehler", "[JSON-Fehler",
    "[Unbekanntes",
)
# Wörter, die eindeutig ein Speichern/Schreiben einer Datei verlangen.
_FILE_INTENT = (
    "speicher", "speichere", "save", "schreib", "datei", "file",
    ".txt", ".md", ".json", ".csv", ".html", "downloads", "ordner",
)
# Wörter, die eindeutig eine Recherche/Suche verlangen.
_SEARCH_INTENT = ("such", "find", "recherch", "infos über", "informationen über", "google")


def _detect_path(task: str) -> str | None:
    """Extrahiert einen Ziel-Dateipfad aus der Aufgabe (oder None)."""
    # Windows (C:/… oder C:\…) oder POSIX-Pfad mit Dateiendung
    m = re.search(r"([A-Za-z]:[\\/][^\s\"'<>|]+\.[A-Za-z0-9]{1,5})", task)
    if m:
        return m.group(1).replace("\\", "/")
    m = re.search(r"(/[^\s\"'<>|]+\.[A-Za-z0-9]{1,5})", task)
    return m.group(1) if m else None


def _completion_gate(task: str, tools_used: set[str]) -> str:
    """Prüft, ob das Modell die geforderten Seiteneffekte wirklich erzeugt hat.

    Verhindert die häufigste Halluzination kleiner Modelle: 'Datei gespeichert',
    obwohl write_file nie aufgerufen wurde. Wenn ein konkreter Pfad genannt ist,
    wird die ECHTE Existenz der Datei auf der Platte geprüft (Gold-Standard).
    Gibt eine Korrekturanweisung zurück (oder '' wenn alles erfüllt ist).
    """
    import os

    low = task.lower()

    wants_file = any(k in low for k in _FILE_INTENT)
    if wants_file:
        path = _detect_path(task)
        if path is not None:
            if os.path.exists(path):
                return ""  # Datei existiert wirklich → erfüllt
            return (
                f"STOP — die Datei '{path}' existiert noch NICHT auf der Platte. "
                "Erfinde KEINE Erfolgsmeldung. Rufe JETZT ACTION mit write_file auf — "
                "mit GENAU diesem Pfad und dem vollständigen, ausführlichen Inhalt."
            )
        if "write_file" not in tools_used:
            return (
                "STOP — du hast NICHT fertig. write_file wurde nie aufgerufen, "
                "die Datei existiert also noch NICHT. Erfinde KEINE Erfolgsmeldung. "
                "Rufe JETZT ACTION mit write_file auf — mit Pfad und vollständigem Inhalt."
            )

    wants_search = any(k in low for k in _SEARCH_INTENT)
    research_tools = {"web_search", "web_fetch", "arxiv_search", "pubmed_search",
                      "openalex_search", "europepmc_search", "chembl_search"}
    if wants_search and not (tools_used & research_tools):
        return (
            "STOP — du sollst recherchieren, hast aber kein Such-Tool benutzt. "
            "Rufe JETZT ACTION mit web_search (oder einem passenden Such-Tool) auf, "
            "bevor du DONE meldest."
        )

    return ""
