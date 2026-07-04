"""Tool: Textinhalt einer Datei lesen."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"path": "__sample_nonexistent__.txt"}
DEFINITION = {
    "name": "read_file",
    "description": "Liest den Textinhalt einer lokalen Datei und gibt ihn zurück.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Pfad zur Datei"}},
        "required": ["path"],
    },
}


def read_file(path: str) -> str:
    """Liest den Textinhalt einer lokalen Datei."""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return f"[Fehler: Datei nicht gefunden: {path}]"
    if not p.is_file():
        return f"[Fehler: kein regulärer Dateipfad: {path}]"
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"[Fehler beim Lesen von {path}: {exc}]"
    if len(text) > 20000:
        return text[:20000] + f"\n[... gekürzt, {len(text)} Zeichen gesamt]"
    return text
