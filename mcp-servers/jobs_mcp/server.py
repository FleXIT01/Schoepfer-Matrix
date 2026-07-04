"""jobs-mcp — asynchrone Job-Queue für Langläufer der Schöpfer-Matrix (N7).

Langläufer (deep-research, build-bot, factory) können als Hintergrund-Jobs
eingereicht werden. Der Chat-Kanal blockiert nicht mehr.

Tools:
  job_submit(description, priority)  — Job einreihen, Job-ID zurück
  job_start(job_id)                  — Job als "laufend" markieren (vom Agent)
  job_complete(job_id, result)       — Ergebnis speichern + (optional) Telegram-Alarm
  job_fail(job_id, reason)           — Job als fehlgeschlagen markieren
  job_status(job_id)                 — Einzelner Job-Status
  job_list(state)                    — Jobs nach Status auflisten
  job_cancel(job_id)                 — Job abbrechen (nur pending/running)

SQLite-DB: jobs_mcp/jobs.db  (gleiche Konvention wie costs.db, pending.db)

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import check_freeze  # noqa: E402  (NOT-AUS Phase A)

mcp = FastMCP("jobs-mcp")

_DB = Path(__file__).parent / "jobs.db"

# Telegram (optional) — aus Env, wie in mail-mcp
_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")


# ─── DB ─────────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    with sqlite3.connect(_DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                priority    INTEGER NOT NULL DEFAULT 5,
                state       TEXT NOT NULL DEFAULT 'pending',
                result      TEXT,
                created_at  TEXT NOT NULL,
                started_at  TEXT,
                finished_at TEXT
            )
        """)
        con.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_job(con: sqlite3.Connection, job_id: str) -> dict | None:
    row = con.execute(
        "SELECT id, description, priority, state, result, created_at, started_at, finished_at "
        "FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    if not row:
        return None
    return dict(zip(["id", "description", "priority", "state", "result",
                     "created_at", "started_at", "finished_at"], row))


def _fmt_job(j: dict) -> str:
    dur = ""
    if j["started_at"] and j["finished_at"]:
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            s = datetime.strptime(j["started_at"], fmt)
            e = datetime.strptime(j["finished_at"], fmt)
            secs = int((e - s).total_seconds())
            dur = f"  Dauer: {secs}s"
        except Exception:
            pass
    state_icon = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌",
                  "cancelled": "🚫"}.get(j["state"], "?")
    lines = [
        f"{state_icon} [{j['id'][:8]}] {j['description']}",
        f"   Status: {j['state']}  |  Priorität: {j['priority']}  |  Erstellt: {j['created_at']}{dur}",
    ]
    if j["started_at"]:
        lines.append(f"   Gestartet: {j['started_at']}")
    if j["finished_at"]:
        lines.append(f"   Abgeschlossen: {j['finished_at']}")
    if j["result"]:
        preview = j["result"][:300].replace("\n", " ")
        lines.append(f"   Ergebnis: {preview}{'…' if len(j['result']) > 300 else ''}")
    return "\n".join(lines)


def _telegram_notify(text: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        import urllib.request, urllib.parse, json as _json
        payload = _json.dumps({"chat_id": int(_TG_CHAT), "text": text,
                               "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ─── MCP Tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
def job_submit(description: str, priority: int = 5) -> str:
    """Reicht einen neuen Hintergrund-Job ein (gibt sofort eine Job-ID zurück).

    Für: Langläufer die den Chat nicht blockieren sollen (deep-research,
    build-bot, factory). Der eigentliche Auftrag wird später als eigenständiger
    Agent-Turn gestartet.

    description: Was soll getan werden? (klarer Auftrag, 1-3 Sätze)
    priority:    1 = höchste, 10 = niedrigste (Standard: 5)

    Returns: Job-ID + Hinweis wie der Job verfolgt werden kann."""
    _init_db()
    job_id = str(uuid.uuid4())
    with sqlite3.connect(_DB) as con:
        con.execute(
            "INSERT INTO jobs (id, description, priority, state, created_at) VALUES (?,?,?,?,?)",
            (job_id, description.strip(), max(1, min(10, priority)), "pending", _now()),
        )
        con.commit()
    short = job_id[:8]
    return (f"Job eingereicht (ID: {job_id})\n"
            f"  Beschreibung: {description.strip()}\n"
            f"  Priorität: {priority}  |  Status: pending\n"
            f"  Verfolgen: job_status('{short}...') oder job_list()")


@mcp.tool()
def job_start(job_id: str) -> str:
    """Markiert einen Job als 'running' (aufgerufen vom Agent, der ihn bearbeitet).

    job_id: vollständige Job-ID oder eindeutiger Anfang (mind. 4 Zeichen)"""
    check_freeze()  # NOT-AUS: kein neuer Job waehrend Freeze
    _init_db()
    with sqlite3.connect(_DB) as con:
        j = _resolve_job(con, job_id)
        if isinstance(j, str):
            return j
        if j["state"] != "pending":
            return f"[jobs-mcp] Job ist bereits '{j['state']}', nicht 'pending'."
        con.execute("UPDATE jobs SET state='running', started_at=? WHERE id=?",
                    (_now(), j["id"]))
        con.commit()
    return f"Job [{j['id'][:8]}] gestartet."


@mcp.tool()
def job_complete(job_id: str, result: str) -> str:
    """Speichert das Ergebnis eines Jobs und markiert ihn als 'done'.
    Sendet optional eine Telegram-Benachrichtigung.

    job_id: vollständige Job-ID oder eindeutiger Anfang
    result: Ergebnis-Text (Zusammenfassung, Pfad, URL, ...)"""
    _init_db()
    with sqlite3.connect(_DB) as con:
        j = _resolve_job(con, job_id)
        if isinstance(j, str):
            return j
        if j["state"] not in ("pending", "running"):
            return f"[jobs-mcp] Job ist bereits '{j['state']}' — kann nicht als done markiert werden."
        now = _now()
        con.execute(
            "UPDATE jobs SET state='done', result=?, finished_at=? WHERE id=?",
            (result, now, j["id"])
        )
        con.commit()
    # Telegram-Alarm
    short_desc = j["description"][:80]
    _telegram_notify(
        f"✅ *Job abgeschlossen*\n`{j['id'][:8]}`  {short_desc}\n\n{result[:500]}"
    )
    return f"Job [{j['id'][:8]}] abgeschlossen. Ergebnis gespeichert ({len(result)} Zeichen)."


@mcp.tool()
def job_fail(job_id: str, reason: str) -> str:
    """Markiert einen Job als fehlgeschlagen und speichert den Grund.

    job_id: vollständige Job-ID oder eindeutiger Anfang
    reason: Fehlerbeschreibung"""
    _init_db()
    with sqlite3.connect(_DB) as con:
        j = _resolve_job(con, job_id)
        if isinstance(j, str):
            return j
        if j["state"] not in ("pending", "running"):
            return f"[jobs-mcp] Job ist bereits '{j['state']}'."
        con.execute(
            "UPDATE jobs SET state='failed', result=?, finished_at=? WHERE id=?",
            (f"FEHLER: {reason}", _now(), j["id"])
        )
        con.commit()
    short_desc = j["description"][:80]
    _telegram_notify(
        f"❌ *Job fehlgeschlagen*\n`{j['id'][:8]}`  {short_desc}\n\n{reason[:300]}"
    )
    return f"Job [{j['id'][:8]}] als 'failed' markiert."


@mcp.tool()
def job_cancel(job_id: str) -> str:
    """Bricht einen pending oder running Job ab.

    job_id: vollständige Job-ID oder eindeutiger Anfang"""
    _init_db()
    with sqlite3.connect(_DB) as con:
        j = _resolve_job(con, job_id)
        if isinstance(j, str):
            return j
        if j["state"] not in ("pending", "running"):
            return f"[jobs-mcp] Job '{j['state']}' kann nicht abgebrochen werden (nur pending/running)."
        con.execute(
            "UPDATE jobs SET state='cancelled', result='Manuell abgebrochen.', finished_at=? WHERE id=?",
            (_now(), j["id"])
        )
        con.commit()
    return f"Job [{j['id'][:8]}] abgebrochen."


@mcp.tool()
def job_status(job_id: str) -> str:
    """Status und Ergebnis eines einzelnen Jobs.

    job_id: vollständige Job-ID oder eindeutiger Anfang (mind. 4 Zeichen)"""
    _init_db()
    with sqlite3.connect(_DB) as con:
        j = _resolve_job(con, job_id)
    if isinstance(j, str):
        return j
    return _fmt_job(j)


@mcp.tool()
def job_list(state: str = "active") -> str:
    """Listet Jobs nach Status auf.

    state: 'active' (pending+running, Standard) | 'pending' | 'running' |
           'done' | 'failed' | 'cancelled' | 'all'

    Für: Überblick über laufende und wartende Aufgaben."""
    _init_db()
    valid = {"active", "pending", "running", "done", "failed", "cancelled", "all"}
    if state not in valid:
        return f"[jobs-mcp] Unbekannter state '{state}'. Erlaubt: {', '.join(sorted(valid))}"

    if state == "active":
        where = "WHERE state IN ('pending','running')"
    elif state == "all":
        where = ""
    else:
        where = f"WHERE state='{state}'"

    with sqlite3.connect(_DB) as con:
        rows = con.execute(
            f"SELECT id, description, priority, state, result, created_at, started_at, finished_at "
            f"FROM jobs {where} ORDER BY priority ASC, created_at ASC"
        ).fetchall()

    if not rows:
        label = "aktive" if state == "active" else state
        return f"Keine {label} Jobs."

    jobs = [dict(zip(["id", "description", "priority", "state", "result",
                      "created_at", "started_at", "finished_at"], r)) for r in rows]
    lines = [f"JOBS ({state.upper()}) — {len(jobs)} Einträge\n"]
    for j in jobs:
        lines.append(_fmt_job(j))
        lines.append("")
    return "\n".join(lines).strip()


# ─── Interne Hilfsfunktion (nicht als Tool) ──────────────────────────────────────

def _resolve_job(con: sqlite3.Connection, job_id: str) -> dict | str:
    """Sucht Job per exakter ID oder Präfix. Gibt Job-dict oder Fehlermeldung zurück."""
    job_id = job_id.strip()
    if len(job_id) < 4:
        return "[jobs-mcp] job_id zu kurz (mind. 4 Zeichen)."
    # Exakte Suche
    j = _get_job(con, job_id)
    if j:
        return j
    # Präfix-Suche
    rows = con.execute(
        "SELECT id, description, priority, state, result, created_at, started_at, finished_at "
        "FROM jobs WHERE id LIKE ?", (f"{job_id}%",)
    ).fetchall()
    if not rows:
        return f"[jobs-mcp] Kein Job mit ID (Präfix) '{job_id}' gefunden."
    if len(rows) > 1:
        ids = ", ".join(r[0][:8] for r in rows)
        return f"[jobs-mcp] Mehrdeutig — mehrere Jobs passen zu '{job_id}': {ids}"
    return dict(zip(["id", "description", "priority", "state", "result",
                     "created_at", "started_at", "finished_at"], rows[0]))


@mcp.tool()
def auto_research_quota() -> str:
    """I4 Neugier-Schleife: Tages-Kontingent für automatische Hintergrundrecherchen.

    Schützt vor Endlosschleifen: maximal 3 Auto-Jobs pro Tag.
    Auto-Jobs sind Jobs, deren Beschreibung mit '[AUTO]' beginnt.

    Prüfe dieses Kontingent VOR jedem job_submit('[AUTO] ...') —
    nur wenn 'Kapazität frei' zurückkommt, Job einreichen.

    Gibt zurück: Verbrauch heute, Limit, ob weiterer Job erlaubt ist."""
    _init_db()
    today = _now()[:10]  # YYYY-MM-DD
    with sqlite3.connect(_DB) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE description LIKE '[AUTO]%' AND created_at LIKE ?",
            (f"{today}%",)
        ).fetchone()[0]

    limit = 3
    remaining = max(0, limit - count)
    can = remaining > 0

    status = "✅ Kapazität frei" if can else "🚫 Limit erreicht — kein Auto-Research heute mehr"
    tip = (f"→ job_submit('[AUTO] deep_research: <query>') ist erlaubt."
           if can else "→ Nutzer informieren oder bis morgen warten.")

    return (
        f"AUTO-RESEARCH KONTINGENT ({today}):\n"
        f"  Verbraucht: {count}/{limit}  |  Verbleibend: {remaining}\n"
        f"  {status}\n"
        f"  {tip}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
