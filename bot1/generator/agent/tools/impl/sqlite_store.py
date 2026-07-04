"""Tool: Persistenter Key-Value-Speicher auf Basis von SQLite."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"action": "set", "key": "k", "value": "v"}
DEFINITION = {
    "name": "sqlite_store",
    "description": "Persistenter Key-Value-Speicher (SQLite). action: 'set' speichert key/value, 'get' liest key.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "'set' oder 'get'"},
            "key": {"type": "string", "description": "Schlüssel"},
            "value": {"type": "string", "description": "Wert (nur bei 'set')"},
        },
        "required": ["action", "key"],
    },
}


def sqlite_store(action: str, key: str, value: str = "") -> str:
    """Persistenter Key-Value-Speicher auf Basis von SQLite."""
    import sqlite3
    from pathlib import Path

    db = Path("bot_kv_store.sqlite3")
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
        action = (action or "").lower()
        if action == "set":
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()
            return f"[OK: '{key}' gespeichert]"
        if action == "get":
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return row[0] if row else f"[kein Wert für '{key}']"
        return f"[Fehler: unbekannte action '{action}' (erwartet 'set' oder 'get')]"
    finally:
        conn.close()
