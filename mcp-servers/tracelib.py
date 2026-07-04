"""tracelib — schlanker Pro-Schritt-Tracer für die Schöpfer-Matrix (V14).

Schreibt Pipeline-Schritte (Latenz/Kosten je Stufe) DIREKT in die gemeinsame
trace.db, ohne den Umweg über das trace-mcp-Tool. So können beliebige MCP-Server
(kb, llm, …) ihre Stufen automatisch protokollieren, statt darauf zu hoffen, dass
das Modell `log_step` aufruft.

Design-Regeln:
  - BEST EFFORT: ein Trace-Fehler darf NIE einen echten Turn kaputtmachen
    (alles in try/except, Timeout-arm, eigene Verbindung pro Schreibvorgang).
  - Gleiche Tabelle/Spalten wie trace_mcp/server.py (steps).

Nutzung:
    from tracelib import step_timer, log_step

    with step_timer("retrieval", detail="qdrant hybrid"):
        ... # gemessener Block

    # oder manuell:
    log_step("reranker", latency_ms=2800, detail="BGE-v2 20->5")
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).parent / "trace_mcp" / "trace.db"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS steps (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    NOT NULL,
            turn_id   INTEGER NOT NULL DEFAULT 0,
            step      TEXT    NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            cost_usd  REAL    NOT NULL DEFAULT 0.0,
            tokens    INTEGER NOT NULL DEFAULT 0,
            status    TEXT    NOT NULL DEFAULT 'ok',
            detail    TEXT    NOT NULL DEFAULT ''
        )"""
    )


def log_step(
    step: str,
    latency_ms: int = 0,
    *,
    turn_id: int = 0,
    cost_usd: float = 0.0,
    tokens: int = 0,
    status: str = "ok",
    detail: str = "",
) -> None:
    """Schreibt einen Schritt in trace.db. Schlägt NIE fehl (best effort)."""
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # timeout klein halten: lieber Trace verlieren als den Turn blockieren
        with sqlite3.connect(_DB_PATH, timeout=2.0) as c:
            _ensure_table(c)
            c.execute(
                "INSERT INTO steps (ts,turn_id,step,latency_ms,cost_usd,tokens,status,detail) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ts, int(turn_id), str(step)[:60], int(latency_ms), float(cost_usd),
                 int(tokens), str(status), str(detail)[:300]),
            )
            c.commit()
    except Exception:  # noqa: BLE001 — Tracing darf den Turn nie crashen
        pass


@contextmanager
def step_timer(step: str, *, turn_id: int = 0, detail: str = "", cost_usd: float = 0.0):
    """Kontextmanager: misst die Dauer des Blocks und loggt ihn als Schritt.
    Bei einer Exception im Block wird der Schritt mit status='error' geloggt
    und die Exception normal weitergereicht."""
    t0 = time.monotonic()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log_step(step, latency_ms=elapsed_ms, turn_id=turn_id,
                 cost_usd=cost_usd, status=status, detail=detail)
