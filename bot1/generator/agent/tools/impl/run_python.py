"""Tool: Python-Code in einem isolierten Subprozess ausführen (Sandbox)."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"code": "print(40 + 2)"}
DEFINITION = {
    "name": "run_python",
    "description": "Führt ein kurzes Python-Skript in einem isolierten Subprozess aus und gibt die Ausgabe zurück.",
    "input_schema": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Auszuführender Python-Code"}},
        "required": ["code"],
    },
}


def run_python(code: str) -> str:
    """Führt Python-Code in einem isolierten Subprozess mit Timeout aus."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return "[Fehler: Zeitüberschreitung nach 15s]"
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"[Exit {proc.returncode}]\n{out}\n{err}".strip()
        return out or "[kein stdout]"
