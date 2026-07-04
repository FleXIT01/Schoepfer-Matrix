"""Deterministische Checks für das Agent-Build-System (kein echtes Modell nötig).

Start:  python tests/run_checks.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ausgabe robust gegen Windows-cp1252-Konsole machen
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# Projekt-Root auf den Pfad
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.agent import package_builder
from generator.agent.orchestrator import Orchestrator
from generator.agent.package_builder import build_package, resolve_skeleton_tools
from generator.agent.verify import gates, sandbox
from generator.llm.mock_adapter import MockAdapter
from generator.models.bot_spec import (
    BotSpec, BotType, LLMProviderSpec, MemoryStrategy, ToolSpec,
)

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [OK]   {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}  {detail}")


CODE_FENCE = "```"


def _fence(code: str) -> str:
    return f"{CODE_FENCE}python\n{code}\n{CODE_FENCE}"


# ---------------------------------------------------------------------------
# 1. Gates gegen gutes/schlechtes Modul
# ---------------------------------------------------------------------------

def test_gates_basic():
    print("\n== Gates: Syntax/Import/Smoke ==")
    spec = BotSpec(
        name="GateBot", description="x", system_prompt="Du bist GateBot.",
        llm=LLMProviderSpec(provider="ollama", model="llama3.1"),
        memory_strategy=MemoryStrategy.IN_SESSION, tools=[],
    )
    files = build_package(spec, resolve_skeleton_tools(spec))

    # alle .py syntaktisch ok
    all_ok = all(gates.syntax_gate(c, label=p).ok for p, c in files.items() if p.endswith(".py"))
    check("Skeleton: alle Dateien syntaktisch korrekt", all_ok)

    # kaputte Syntax wird erkannt
    bad = gates.syntax_gate("def x(:\n  pass", label="bad")
    check("Syntax-Gate erkennt kaputten Code", not bad.ok and "SyntaxError" in bad.error)

    with sandbox.materialized(files) as d:
        check("Import-Gate: bot.runner importierbar", gates.import_gate(d, "bot.runner", 30).ok)
        check("Smoke-Gate: respond() liefert String", gates.smoke_gate(d, 30).ok)

    # Import-Gate erkennt kaputtes Modul
    broken_files = dict(files)
    broken_files["bot/runner.py"] = "import does_not_exist_xyz\n"
    with sandbox.materialized(broken_files) as d:
        check("Import-Gate erkennt fehlerhaftes Modul", not gates.import_gate(d, "bot.runner", 30).ok)


# ---------------------------------------------------------------------------
# 2. tool_gate unterscheidet Absturz von sauberem Fehler-String
# ---------------------------------------------------------------------------

def test_tool_gate_semantics():
    print("\n== tool_gate: Absturz vs. sauberer Fehler ==")
    spec = BotSpec(
        name="ToolBot", description="x", system_prompt="Du bist ToolBot.",
        llm=LLMProviderSpec(provider="ollama", model="llama3.1"),
        memory_strategy=MemoryStrategy.IN_SESSION,
        tools=[ToolSpec(name="read_file", description="liest")],
    )
    tools = resolve_skeleton_tools(spec)
    files = build_package(spec, tools)
    with sandbox.materialized(files) as d:
        # read_file mit nicht-existentem Pfad -> sauberer Fehler-String -> PASS
        r = gates.tool_gate(d, "read_file", {"path": "nope.txt"}, 30)
        check("tool_gate: sauberer Fehler-String besteht", r.ok, r.error)

    # ein abstürzendes Tool muss durchfallen
    crash = package_builder.ResolvedTool(
        name="crasher",
        func_source="def crasher(x: int) -> str:\n    return str(x * undefined_name)",
        definition={"name": "crasher", "description": "x",
                    "input_schema": {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]}},
        sample_input={"x": 2},
    )
    files2 = build_package(spec, tools + [crash])
    with sandbox.materialized(files2) as d:
        r = gates.tool_gate(d, "crasher", {"x": 2}, 30)
        check("tool_gate: Absturz (NameError) fällt durch", not r.ok and "NameError" in r.error, r.error)


# ---------------------------------------------------------------------------
# 3. Voller Orchestrator-Lauf: broken tool -> Fixer -> grün
# ---------------------------------------------------------------------------

def test_orchestrator_fix_loop():
    print("\n== Orchestrator: Architect -> Coder(broken) -> Fixer ==")
    arch = json.dumps({"tools": [
        {"name": "read_file", "description": "liest", "capability": "read_file", "needs_generation": False},
        {"name": "verdopple", "description": "verdoppelt eine Zahl", "capability": None,
         "needs_generation": True, "signature": "def verdopple(zahl: int) -> str", "sample_input": {"zahl": 21}},
    ]})
    broken = _fence("def verdopple(zahl: int) -> str:\n    return str(zahl * faktor)")
    fixed = _fence(
        "def verdopple(zahl: int) -> str:\n"
        "    try:\n"
        "        return str(int(zahl) * 2)\n"
        "    except Exception as e:\n"
        "        return '[Fehler: ' + str(e) + ']'"
    )
    mock = MockAdapter([arch, broken, fixed])
    spec = BotSpec(
        name="RechenBot", description="Rechnet und liest Dateien.",
        system_prompt="Du bist RechenBot.", bot_type=BotType.CODING_ASSISTANT,
        llm=LLMProviderSpec(provider="ollama", model="llama3.1"),
        memory_strategy=MemoryStrategy.IN_SESSION,
        tools=[ToolSpec(name="read_file", description="liest"),
               ToolSpec(name="verdopple", description="verdoppelt")],
    )
    orch = Orchestrator(mock, real_run=False)
    out = Path(tempfile.mkdtemp(prefix="orch_check_"))
    res = orch.build(spec, out)

    steps = {s.step: s for s in res.steps}
    verd = steps.get("tool:verdopple")
    check("Orchestrator: Gesamtergebnis ok", res.ok,
          " / ".join(f"{s.step}:{s.status}" for s in res.steps))
    check("verdopple wurde durch Fixer repariert (status=fixed)",
          verd is not None and verd.status == "fixed",
          verd.detail if verd else "Step fehlt")

    tools_py = (out / "bot" / "tools.py").read_text(encoding="utf-8")
    check("tools.py enthält reparierten Code", "int(zahl) * 2" in tools_py)
    check("tools.py enthält NICHT mehr den Bug", "* faktor" not in tools_py)
    check("read_file aus Bibliothek eingebettet", "def read_file(" in tools_py)
    check("BUILD_REPORT.md geschrieben", (out / "BUILD_REPORT.md").exists())


# ---------------------------------------------------------------------------
# 4. Tool, das nie reparierbar ist -> degradiert zu Stub, Bot bleibt lauffähig
# ---------------------------------------------------------------------------

def test_orchestrator_degrade_to_stub():
    print("\n== Orchestrator: unreparierbar -> Stub, Bot bleibt grün ==")
    arch = json.dumps({"tools": [
        {"name": "kaputt", "description": "geht nie", "capability": None,
         "needs_generation": True, "signature": "def kaputt(x: int) -> str", "sample_input": {"x": 1}},
    ]})
    broken = _fence("def kaputt(x: int) -> str:\n    return str(x * nicht_da)")
    # Fixer liefert immer denselben kaputten Code -> nie grün -> Stub
    mock = MockAdapter([arch, broken, broken])
    spec = BotSpec(
        name="StubBot", description="x", system_prompt="Du bist StubBot.",
        llm=LLMProviderSpec(provider="ollama", model="llama3.1"),
        memory_strategy=MemoryStrategy.IN_SESSION,
        tools=[ToolSpec(name="kaputt", description="geht nie")],
    )
    orch = Orchestrator(mock, real_run=False)
    out = Path(tempfile.mkdtemp(prefix="orch_stub_"))
    res = orch.build(spec, out)
    steps = {s.step: s for s in res.steps}
    k = steps.get("tool:kaputt")
    check("kaputt degradiert zu Stub", k is not None and k.status == "degraded", k.detail if k else "fehlt")
    # Trotzdem muss das Paket smoke-grün sein
    proj = steps.get("projekt:import+smoke")
    check("Projekt bleibt trotz Degradierung grün",
          proj is not None and proj.status in ("ok", "fixed"), proj.detail if proj else "fehlt")
    with sandbox.materialized(res.files) as d:
        check("Finales Paket: Smoke-Test grün", gates.smoke_gate(d, 30).ok)


def main() -> int:
    test_gates_basic()
    test_tool_gate_semantics()
    test_orchestrator_fix_loop()
    test_orchestrator_degrade_to_stub()
    print(f"\n=== {_passed} bestanden, {_failed} fehlgeschlagen ===")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
