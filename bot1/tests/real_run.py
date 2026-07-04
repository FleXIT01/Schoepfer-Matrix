"""Echter End-to-End-Lauf gegen ein lokales Ollama-Modell.

Baut nicht-interaktiv eine BotSpec und lässt den Orchestrator den Bot bauen,
verifizieren und final gegen das echte Modell laufen.

Start:  python tests/real_run.py [modell]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.agent.orchestrator import Orchestrator
from generator.llm.ollama_adapter import OllamaAdapter
from generator.models.bot_spec import (
    BotSpec, BotType, LLMProviderSpec, MemoryStrategy, ToolSpec,
)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"


def main() -> int:
    llm = OllamaAdapter(model=MODEL, base_url="http://localhost:11434")

    spec = BotSpec(
        name="DateiHelfer",
        description="Ein Assistent, der lokale Dateien liest, Python-Code ausführt und Wörter in Texten zählt.",
        system_prompt=(
            "Du bist DateiHelfer, ein hilfreicher Assistent für Datei- und Code-Aufgaben. "
            "Du antwortest knapp auf Deutsch und nutzt Tools, wenn sie helfen."
        ),
        bot_type=BotType.CODING_ASSISTANT,
        llm=LLMProviderSpec(provider="ollama", model=MODEL),
        memory_strategy=MemoryStrategy.IN_SESSION,
        use_cases=["Dateien lesen", "Code ausführen", "Wörter zählen"],
        tools=[
            ToolSpec(name="read_file", description="Liest den Inhalt einer Datei"),
            ToolSpec(name="run_python", description="Führt Python-Code aus"),
            ToolSpec(name="woerter_zaehlen", description="Zählt die Wörter in einem Text"),
        ],
        generated_at="real-run",
    )

    print(f"=== Agent-Build mit Modell '{MODEL}' ===\n")
    orch = Orchestrator(llm, real_run=True)
    out = Path(tempfile.mkdtemp(prefix="real_run_"))
    result = orch.build(spec, out, progress=lambda m: print("  ·", m))

    print("\n=== Verifikations-Schritte ===")
    for s in result.steps:
        print(f"  [{s.status}] {s.step} (att={s.attempts}) {s.detail}")

    print(f"\n=== Gesamtstatus: {'OK' if result.ok else 'mit Einschränkungen'} ===")
    print(f"=== Finaler echter Lauf ok: {result.final_run_ok} ===")
    print("--- Beispiel-Antwort des Bots ---")
    print((result.final_run_output or "").strip()[:1500])

    print(f"\n=== Paket geschrieben nach: {out} ===")
    tools_py = (out / "bot" / "tools.py").read_text(encoding="utf-8")
    # Prüfe alle tatsächlich generierten Tool-Namen (unabhängig vom Modell-Naming)
    import re
    found_tools = re.findall(r"def (\w+)\(", tools_py)
    dispatch_keys = re.findall(r'"(\w+)":', tools_py)
    print(f"Tools im Code ({len(found_tools)}):", found_tools)
    print("Dispatch-Einträge:", [k for k in dict.fromkeys(dispatch_keys) if k != "k"])

    # Mindest-Anforderung: mindestens 1 Library-Tool und 1 echte Implementierung
    has_lib = any(t in tools_py for t in ("def read_file", "def run_python", "def web_fetch"))
    print("Bibliotheks-Tool eingebettet:", has_lib)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
