"""Deterministische Gates: Syntax, Import, Smoke-Test, Tool-Test.

Jedes Gate gibt ein ``GateResult`` zurück. Die teureren Gates (Import/Smoke/Tool)
laufen in einem Subprozess gegen eine temp-Kopie des Pakets (siehe sandbox.py).
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

from . import sandbox
from .mock_llm import MOCK_LLM_PLAIN_SOURCE, MOCK_LLM_TOOL_SOURCE

_MAX_ERR = 4000


def _trunc(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= _MAX_ERR else text[-_MAX_ERR:]


@dataclass
class GateResult:
    ok: bool
    error: str = ""
    gate: str = ""


def syntax_gate(source: str, *, label: str = "") -> GateResult:
    """In-process ast.parse — schnell, sicher (kein Code wird ausgeführt)."""
    try:
        ast.parse(source)
        return GateResult(True, gate="syntax")
    except SyntaxError as exc:
        loc = f"Zeile {exc.lineno}, Spalte {exc.offset}"
        return GateResult(
            False,
            error=f"SyntaxError in {label or 'Quelle'} ({loc}): {exc.msg}",
            gate="syntax",
        )


def import_gate(project_dir: Path, module: str, timeout: float) -> GateResult:
    """Importiert das Modul in einem Subprozess (cwd=project_dir)."""
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        f"import {module}\n"
        "print('IMPORT_OK')"
    )
    res = sandbox.run_inline(project_dir, code, timeout)
    if res.ok and "IMPORT_OK" in res.stdout:
        return GateResult(True, gate="import")
    return GateResult(False, error=_trunc(res.output), gate="import")


def smoke_gate(project_dir: Path, timeout: float) -> GateResult:
    """Instanziiert den Bot mit gemocktem LLM und prüft respond() -> nicht-leerer str."""
    driver = (
        "import sys, traceback\n"
        "sys.path.insert(0, '.')\n"
        f"{MOCK_LLM_PLAIN_SOURCE}\n"
        "try:\n"
        "    from bot.config import BotConfig\n"
        "    from bot.runner import BotRunner\n"
        "    bot = BotRunner(config=BotConfig(), llm_client=MockLLM())\n"
        "    out = bot.respond('Hallo, funktionierst du?')\n"
        "    assert isinstance(out, str) and out.strip(), 'respond() lieferte keinen nicht-leeren String'\n"
        "    print('SMOKE_OK')\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )
    res = sandbox.run_driver(project_dir, driver, timeout)
    if res.ok and "SMOKE_OK" in res.stdout:
        return GateResult(True, gate="smoke")
    return GateResult(False, error=_trunc(res.output), gate="smoke")


def tool_loop_gate(project_dir: Path, tool_name: str, tool_args: dict, timeout: float) -> GateResult:
    """Erzwingt über den Mock einen Tool-Aufruf und prüft, dass respond() durchläuft."""
    driver = (
        "import sys, traceback\n"
        "sys.path.insert(0, '.')\n"
        f"{MOCK_LLM_TOOL_SOURCE}\n"
        "try:\n"
        "    from bot.config import BotConfig\n"
        "    from bot.runner import BotRunner\n"
        f"    mock = MockLLM({tool_name!r}, {json.dumps(tool_args)})\n"
        "    bot = BotRunner(config=BotConfig(), llm_client=mock)\n"
        "    out = bot.respond('Bitte nutze ein Tool.')\n"
        "    assert isinstance(out, str) and out.strip(), 'respond() lieferte keinen String'\n"
        "    assert mock.calls >= 2, 'Tool-Schleife hat das Modell nicht erneut befragt'\n"
        "    print('TOOLLOOP_OK')\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )
    res = sandbox.run_driver(project_dir, driver, timeout)
    if res.ok and "TOOLLOOP_OK" in res.stdout:
        return GateResult(True, gate="tool_loop")
    return GateResult(False, error=_trunc(res.output), gate="tool_loop")


def tool_gate(project_dir: Path, tool_name: str, sample_input: dict, timeout: float) -> GateResult:
    """Ruft die Tool-Funktion DIREKT mit Beispiel-Input auf.

    Direkt (nicht über dispatch), damit ein echter Absturz (z.B. NameError) als
    Traceback durchschlägt. Das Ergebnis muss NICHT str sein — dispatch wrappt zur
    Laufzeit ohnehin mit str(); entscheidend ist nur: die Funktion wirft nicht und
    das Ergebnis ist stringifizierbar. Ein sauber abgefangenes "[Fehler: ...]" gilt
    als Erfolg.
    """
    driver = (
        "import sys, traceback\n"
        "sys.path.insert(0, '.')\n"
        "try:\n"
        "    from bot.tools import _TOOL_FUNCS\n"
        f"    fn = _TOOL_FUNCS.get({tool_name!r})\n"
        f"    assert fn is not None, 'Tool nicht registriert: ' + {tool_name!r}\n"
        f"    out = fn(**{json.dumps(sample_input)})\n"
        "    _ = str(out)  # muss stringifizierbar sein (dispatch wrappt mit str())\n"
        "    print('TOOL_OK')\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )
    res = sandbox.run_driver(project_dir, driver, timeout)
    if res.ok and "TOOL_OK" in res.stdout:
        return GateResult(True, gate="tool")
    return GateResult(False, error=_trunc(res.output), gate="tool")
