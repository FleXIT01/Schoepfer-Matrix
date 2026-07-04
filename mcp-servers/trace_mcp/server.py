"""trace-mcp — Turn-Protokollierung der Schöpfer-Matrix.

V3 TRACE LOG: Jeder Agent-Turn wird hier protokolliert (Zeit, Kanal, Modell,
aufgerufene Tools, Tokens, Kosten, Status). Gespeichert in SQLite trace.db.

Tools:
  - log_turn(channel, model, tools, summary, status, tokens_in, tokens_out, cost_usd)
  - view_trace(n=20)  → letzte N Turns als Tabelle
  - trace_stats(days=7) → Aggregat-Statistiken

Start (stdio):  python server.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("trace-mcp")

_DB_PATH = Path(__file__).parent / "trace.db"


# ─── DB ───────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    with sqlite3.connect(_DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS turns (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT    NOT NULL,
            channel  TEXT    NOT NULL DEFAULT 'unknown',
            model    TEXT    NOT NULL DEFAULT 'unknown',
            tools    TEXT    NOT NULL DEFAULT '',
            summary  TEXT    NOT NULL DEFAULT '',
            status   TEXT    NOT NULL DEFAULT 'ok',
            tokens_in  INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd   REAL    NOT NULL DEFAULT 0.0
        )""")
        # V14: Pro-Schritt-Trace (Latenz/Kosten je Pipeline-Stufe) — beantwortet
        # "wo geht die Zeit hin?" (Routing/Retrieval/Reranker/Sub-Agent/Modell).
        c.execute("""CREATE TABLE IF NOT EXISTS steps (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    NOT NULL,
            turn_id   INTEGER NOT NULL DEFAULT 0,
            step      TEXT    NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            cost_usd  REAL    NOT NULL DEFAULT 0.0,
            tokens    INTEGER NOT NULL DEFAULT 0,
            status    TEXT    NOT NULL DEFAULT 'ok',
            detail    TEXT    NOT NULL DEFAULT ''
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_steps_ts ON steps(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_steps_step ON steps(step)")
        c.commit()

_init_db()


def _db_conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


# ─── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def log_turn(
    channel: str = "unknown",
    model: str = "gpt-oss-32k",
    tools: str = "",
    summary: str = "",
    status: str = "ok",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> str:
    """Protokolliert einen Agent-Turn in der Trace-Datenbank.
    Aufruf AM ENDE jeder Hauptinteraktion (Frage beantwortet, Aufgabe erledigt, Fehler).
    channel   = Herkunfts-Kanal (telegram/cli/discord/…)
    model     = genutztes Modell (z.B. gpt-oss-32k, claude-sonnet-4.6)
    tools     = kommagetrennte Liste der aufgerufenen Tool-Namen (leer = keine)
    summary   = 1-2-Satz-Zusammenfassung was passiert ist
    status    = ok | error | partial
    tokens_in/out = Tokens (0 wenn unbekannt)
    cost_usd  = Kosten in USD (0.0 wenn lokal/gratis)"""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db_conn() as c:
        c.execute(
            "INSERT INTO turns (ts,channel,model,tools,summary,status,tokens_in,tokens_out,cost_usd) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, channel.strip(), model.strip(), tools.strip(),
             summary[:500], status.strip(), int(tokens_in), int(tokens_out), float(cost_usd)),
        )
        row_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.commit()
    cost_note = f" | ${cost_usd:.4f}" if cost_usd > 0 else ""
    return f"Turn #{row_id} protokolliert ({ts}){cost_note}."


@mcp.tool()
def view_trace(n: int = 20) -> str:
    """Zeigt die letzten N Agent-Turns (Standard: 20) als kompakte Tabelle.
    Für: Überblick was der Agent zuletzt gemacht hat, Fehler-Diagnose."""
    n = max(1, min(int(n), 200))
    with _db_conn() as c:
        rows = c.execute(
            "SELECT id, ts, channel, model, tools, summary, status, tokens_in, tokens_out, cost_usd "
            "FROM turns ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    if not rows:
        return "Keine Turns protokolliert."

    lines = [f"Letzte {len(rows)} Turns (neueste zuerst):\n"]
    lines.append(f"{'#':>5}  {'Zeit':19}  {'Kanal':10}  {'Modell':18}  {'Status':7}  {'Kosten':8}  Tools / Summary")
    lines.append("-" * 100)
    for r in rows:
        ts_short = r["ts"][:19].replace("T", " ")
        model_short = r["model"][:18]
        tools_short = (r["tools"] or "—")[:30]
        summary_short = (r["summary"] or "—")[:45]
        cost_str = f"${r['cost_usd']:.4f}" if r["cost_usd"] > 0 else "gratis"
        lines.append(
            f"{r['id']:>5}  {ts_short}  {r['channel']:10}  {model_short:18}  "
            f"{r['status']:7}  {cost_str:8}  {tools_short} | {summary_short}"
        )
    total_cost = sum(r["cost_usd"] for r in rows)
    if total_cost > 0:
        lines.append(f"\n  Kosten (letzte {len(rows)} Turns): ${total_cost:.4f}")
    return "\n".join(lines)


@mcp.tool()
def log_step(
    step: str,
    latency_ms: int = 0,
    turn_id: int = 0,
    cost_usd: float = 0.0,
    tokens: int = 0,
    status: str = "ok",
    detail: str = "",
) -> str:
    """Protokolliert EINEN Pipeline-Schritt mit Latenz/Kosten (V14, Engpass-Analyse).
    Aufruf nach jeder messbaren Stufe eines Turns, damit man sieht WO die Zeit hingeht.
    step       = Stufenname, z.B. 'routing' | 'retrieval' | 'reranker' | 'llm_local' |
                 'llm_cloud' | 'subagent_merge' | 'web_fetch' | 'tool:<name>'
    latency_ms = Dauer dieses Schritts in Millisekunden
    turn_id    = optional zugehöriger Turn (aus log_turn), 0 = unzugeordnet
    cost_usd   = Kosten dieses Schritts (0 wenn lokal/gratis)
    tokens     = verarbeitete Tokens (optional)
    status     = ok | error | slow
    detail     = kurze Notiz (z.B. Modellname, Trefferzahl)"""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db_conn() as c:
        c.execute(
            "INSERT INTO steps (ts,turn_id,step,latency_ms,cost_usd,tokens,status,detail) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ts, int(turn_id), step.strip()[:60], int(latency_ms), float(cost_usd),
             int(tokens), status.strip(), detail[:300]),
        )
        row_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.commit()
    return f"Step #{row_id} '{step.strip()}' protokolliert ({latency_ms} ms)."


def _percentile(sorted_vals: list[int], pct: float) -> int:
    """Einfaches Perzentil (nearest-rank) für eine sortierte Liste."""
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round(pct / 100.0 * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


@mcp.tool()
def step_stats(days: int = 7) -> str:
    """ENGPASS-ANALYSE (V14): aggregiert Pro-Schritt-Latenz/Kosten der letzten N Tage.
    Zeigt je Stufe: Anzahl, Gesamt-/Durchschnitts-/p50-/p95-Latenz, Anteil an der
    Gesamtzeit und Kosten — damit man gezielt optimiert ('90% geht in den Reranker')
    statt zu raten. Standard: 7 Tage."""
    days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _db_conn() as c:
        rows = c.execute(
            "SELECT step, latency_ms, cost_usd FROM steps WHERE ts >= ?", (since,)
        ).fetchall()
    if not rows:
        return (f"Keine Schritte in den letzten {days} Tagen protokolliert.\n"
                "Tipp: log_step('routing'|'retrieval'|'reranker'|…, latency_ms=…) aufrufen.")

    by_step: dict[str, list[int]] = {}
    cost_by_step: dict[str, float] = {}
    for r in rows:
        by_step.setdefault(r["step"], []).append(int(r["latency_ms"]))
        cost_by_step[r["step"]] = cost_by_step.get(r["step"], 0.0) + float(r["cost_usd"])

    grand_total_ms = sum(sum(v) for v in by_step.values())
    grand_total_ms = grand_total_ms or 1  # Division schützen

    # Nach Gesamtzeit absteigend (der größte Zeitfresser zuerst)
    ordered = sorted(by_step.items(), key=lambda kv: -sum(kv[1]))

    lines = [f"ENGPASS-ANALYSE — Pro-Schritt (letzte {days} Tage)\n"]
    lines.append(f"{'Schritt':22} {'n':>4} {'Σ ms':>9} {'%Zeit':>6} {'⌀ ms':>7} {'p50':>6} {'p95':>7} {'$':>8}")
    lines.append("-" * 78)
    for step, vals in ordered:
        vals_sorted = sorted(vals)
        total = sum(vals)
        share = total / grand_total_ms * 100
        avg = total / len(vals)
        cost = cost_by_step.get(step, 0.0)
        cost_str = f"${cost:.4f}" if cost > 0 else "—"
        lines.append(
            f"{step[:22]:22} {len(vals):>4} {total:>9} {share:>5.1f}% "
            f"{avg:>7.0f} {_percentile(vals_sorted, 50):>6} {_percentile(vals_sorted, 95):>7} {cost_str:>8}"
        )
    lines.append("-" * 78)
    lines.append(f"  Gesamtzeit aller Schritte: {grand_total_ms/1000:.1f} s über {sum(len(v) for v in by_step.values())} Schritte")
    top_step, top_vals = ordered[0]
    lines.append(f"  → Größter Zeitfresser: '{top_step}' "
                 f"({sum(top_vals)/grand_total_ms*100:.0f}% der Zeit) — hier zuerst optimieren.")
    return "\n".join(lines)


@mcp.tool()
def trace_stats(days: int = 7) -> str:
    """Aggregat-Statistiken der letzten N Tage (Standard: 7).
    Zeigt: Turns pro Kanal/Modell, Fehlerrate, Gesamt-Kosten, Top-Tools."""
    days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _db_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM turns WHERE ts >= ?", (since,)).fetchone()[0]
        if total == 0:
            return f"Keine Turns in den letzten {days} Tagen."

        total_cost = c.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM turns WHERE ts >= ?", (since,)).fetchone()[0]
        errors = c.execute(
            "SELECT COUNT(*) FROM turns WHERE ts >= ? AND status != 'ok'", (since,)).fetchone()[0]

        by_channel = c.execute(
            "SELECT channel, COUNT(*) n FROM turns WHERE ts >= ? GROUP BY channel ORDER BY n DESC",
            (since,)).fetchall()
        by_model = c.execute(
            "SELECT model, COUNT(*) n, COALESCE(SUM(cost_usd),0) cost FROM turns "
            "WHERE ts >= ? GROUP BY model ORDER BY n DESC",
            (since,)).fetchall()
        by_status = c.execute(
            "SELECT status, COUNT(*) n FROM turns WHERE ts >= ? GROUP BY status ORDER BY n DESC",
            (since,)).fetchall()

        # Häufigste Tools
        tool_rows = c.execute(
            "SELECT tools FROM turns WHERE ts >= ? AND tools != ''", (since,)).fetchall()

    tool_counts: dict[str, int] = {}
    for row in tool_rows:
        for t in (row[0] or "").split(","):
            t = t.strip()
            if t:
                tool_counts[t] = tool_counts.get(t, 0) + 1
    top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:10]

    lines = [f"TRACE-STATISTIKEN (letzte {days} Tage)\n"]
    lines.append(f"  Gesamt-Turns : {total}")
    lines.append(f"  Fehler       : {errors} ({errors/total*100:.1f}%)")
    lines.append(f"  Gesamt-Kosten: ${total_cost:.4f}")

    lines.append("\n  Nach Kanal:")
    for r in by_channel:
        lines.append(f"    {r[0]:15} {r[1]:>5} Turns")

    lines.append("\n  Nach Modell:")
    for r in by_model:
        cost_str = f"  ${r[2]:.4f}" if r[2] > 0 else ""
        lines.append(f"    {r[0]:25} {r[1]:>5} Turns{cost_str}")

    lines.append("\n  Nach Status:")
    for r in by_status:
        lines.append(f"    {r[0]:10} {r[1]:>5}")

    if top_tools:
        lines.append("\n  Top-Tools:")
        for name, cnt in top_tools:
            lines.append(f"    {name:35} {cnt:>4}×")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
