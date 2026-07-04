"""Tool: Text in eine Datei schreiben."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"path": "__sample_out__.txt", "content": "hallo"}
DEFINITION = {
    "name": "write_file",
    "description": "Schreibt Text in eine lokale Datei (überschreibt vorhandenen Inhalt).",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Zielpfad"},
            "content": {"type": "string", "description": "Zu schreibender Text"},
        },
        "required": ["path", "content"],
    },
}


def write_file(path: str, content: str) -> str:
    """Schreibt Text in eine lokale Datei."""
    from pathlib import Path

    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"[Fehler beim Schreiben von {path}: {exc}]"
    return f"[OK: {len(content)} Zeichen nach {path} geschrieben]"
