"""resilience.py — Immunsystem der Schöpfer-Matrix (V3, Säule A: R1–R4).

EIN abhängigkeitsfreies Modul (nur Stdlib), das als Dekorator-Schicht über die
Tool-Funktionen aller FastMCP-Server gelegt wird. Geteilte SQLite-DB:
mcp-servers/resilience.db (gleiche Konvention wie costs.db / pending.db / jobs.db).

Dekoratoren:
  @with_fallback(capability)   R1 — Fähigkeits-Leiter: probiert Provider der Reihe
                                    nach ab, loggt jeden Abstieg + Grund.
  @breaker(name)               R2 — Circuit Breaker: 3 Fehlschläge in Folge →
                                    5 min offen (sofortige Klarmeldung statt Hänger),
                                    danach half-open Probe-Call.       [D15]
  @idempotent(key_fn)          R3 — Idempotenz-Ledger: Außen-Aktionen (Mail, PR,
                                    Telegram) werden NIE doppelt ausgeführt, auch
                                    nicht nach Crash+Restart.
  checkpoint(job_id, ...)      R4 — Schritt-State für Langläufer: Neustart macht
                                    ab letztem GUTEN Schritt weiter, nicht von vorn.

Abbruch-Klassifikation (R1, kritisch):
  OOM / Timeout / Verweigerung  → lösen Fallback aus.
  Inhaltlicher Fehler           → KEIN Fallback (sonst maskiert man echte Bugs).

Einbau-Beispiel (FastMCP-Server):
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from resilience import breaker, idempotent, checkpoint, with_fallback

    @mcp.tool()
    @breaker("weknora")
    def kb_search(query: str) -> str: ...

    @mcp.tool()
    @idempotent(lambda to, subject, body: f"mail:{to}:{subject}")
    def email_send(to: str, subject: str, body: str) -> str: ...

Selbsttest:  python resilience.py
"""
from __future__ import annotations

import functools
import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_DB = Path(__file__).parent / "resilience.db"
_LOCK = threading.Lock()

# ─── D15: Circuit-Breaker-Parameter ─────────────────────────────────────────────
BREAKER_FAIL_THRESHOLD = 3      # Fehlschläge in Folge bis "open"
BREAKER_COOLDOWN_SEC = 300      # 5 Minuten


# ════════════════════════════════════════════════════════════════════════════════
#  Geteilte SQLite
# ════════════════════════════════════════════════════════════════════════════════

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_DB, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _init_db() -> None:
    with _LOCK, _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS breaker_state (
                name        TEXT PRIMARY KEY,
                state       TEXT NOT NULL DEFAULT 'closed',  -- closed|open|half_open
                fail_count  INTEGER NOT NULL DEFAULT 0,
                opened_at   REAL,                            -- time.time()
                last_error  TEXT,
                updated_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS action_ledger (
                key         TEXT PRIMARY KEY,
                tool        TEXT NOT NULL,
                args_hash   TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending', -- pending|done|failed
                result      TEXT,
                created_at  TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                job_id      TEXT NOT NULL,
                step        INTEGER NOT NULL,
                state_json  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (job_id, step)
            );
            CREATE TABLE IF NOT EXISTS fallback_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                capability  TEXT NOT NULL,
                rung        TEXT NOT NULL,        -- welcher Provider/Stufe
                outcome     TEXT NOT NULL,        -- ok|oom|timeout|refusal|error
                detail      TEXT,
                ts          TEXT NOT NULL
            );
        """)
        con.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ════════════════════════════════════════════════════════════════════════════════
#  R1 — Fähigkeits-Leiter (@with_fallback)
# ════════════════════════════════════════════════════════════════════════════════

class FallbackTrigger(Exception):
    """Basisklasse: Fehler, die einen Abstieg auf der Leiter auslösen DÜRFEN."""
    kind = "error"


class OOMError(FallbackTrigger):
    """GPU/RAM voll — nächste Sprosse probieren."""
    kind = "oom"


class ProviderTimeout(FallbackTrigger):
    """Provider antwortet nicht — nächste Sprosse probieren."""
    kind = "timeout"


class ModelRefusal(FallbackTrigger):
    """Modell verweigert die Aufgabe — nächste Sprosse probieren."""
    kind = "refusal"


class BudgetBlocked(FallbackTrigger):
    """V9-Tageslimit erreicht — laut Masterplan auf kleineres lokales Modell."""
    kind = "budget"


# Heuristik: bekannte Fehlertexte → Trigger-Klasse. Inhaltliche Fehler bleiben
# unklassifiziert und lösen KEINEN Fallback aus.
_ERROR_PATTERNS: list[tuple[tuple[str, ...], type[FallbackTrigger]]] = [
    (("out of memory", "oom", "cuda", "vram", "insufficient memory"), OOMError),
    (("timeout", "timed out", "zeitüberschreitung", "deadline",
      "nicht erreichbar", "not reachable", "connect", "connection refused",
      "connection error", "läuft die ollama"), ProviderTimeout),
    (("i cannot", "i can't", "ich kann nicht", "refuse", "verweiger",
      "as an ai", "not able to assist"), ModelRefusal),
    (("budget-limit", "budget-sperre", "blocked_budget"), BudgetBlocked),
]


def classify_error(exc_or_text: Exception | str) -> type[FallbackTrigger] | None:
    """Ordnet einen Fehler einer Fallback-Klasse zu — oder None (= echter Bug,
    kein Fallback)."""
    text = str(exc_or_text).lower()
    for needles, cls in _ERROR_PATTERNS:
        if any(n in text for n in needles):
            return cls
    return None


def _log_fallback(capability: str, rung: str, outcome: str, detail: str = "") -> None:
    _init_db()
    with _LOCK, _conn() as con:
        con.execute(
            "INSERT INTO fallback_log (capability, rung, outcome, detail, ts) VALUES (?,?,?,?,?)",
            (capability, rung, outcome, detail[:500], _now()),
        )
        con.commit()


def run_capability(capability: str, ladder: list[tuple[str, Callable[[], str]]]) -> str:
    """R1-Kern: probiert die Leiter (Name, Callable) der Reihe nach ab.

    - Erfolg auf Sprosse 1: Ergebnis unverändert zurück.
    - Erfolg auf tieferer Sprosse: Ergebnis + Vermerk, auf welcher Sprosse
      gelandet wurde (Transparenz-Pflicht aus dem Masterplan).
    - Nur OOM/Timeout/Verweigerung lösen den Abstieg aus; ein inhaltlicher
      Fehler wird sofort durchgereicht (kein Maskieren echter Bugs).
    - Alle Sprossen erschöpft: ehrliches "konnte nicht" mit dem Pfad.
    """
    descents: list[str] = []
    for i, (rung_name, fn) in enumerate(ladder):
        try:
            result = fn()
            # Funktions-Konvention der Matrix: Fehler kommen oft als
            # "[Fehler: ...]"- oder "[Budget-...]"-String zurück statt als Exception.
            if isinstance(result, str) and result.lstrip().startswith(("[Fehler", "[Budget")):
                cls = classify_error(result)
                if cls is None:
                    _log_fallback(capability, rung_name, "error", result)
                    return result  # inhaltlicher Fehler → durchreichen
                _log_fallback(capability, rung_name, cls.kind, result)
                descents.append(f"{rung_name} ({cls.kind})")
                continue
            _log_fallback(capability, rung_name, "ok")
            if i == 0:
                return result
            note = " -> ".join(descents)
            return (f"{result}\n\n[Hinweis: Primärweg ausgefallen ({note}); "
                    f"erledigt über '{rung_name}'.]")
        except FallbackTrigger as e:
            _log_fallback(capability, rung_name, e.kind, str(e))
            descents.append(f"{rung_name} ({e.kind})")
            continue
        except Exception as e:  # noqa: BLE001
            cls = classify_error(e)
            if cls is None:
                _log_fallback(capability, rung_name, "error", str(e))
                raise  # echter Bug → nicht maskieren
            _log_fallback(capability, rung_name, cls.kind, str(e))
            descents.append(f"{rung_name} ({cls.kind})")
            continue
    path = " -> ".join(descents) if descents else "(leer)"
    return (f"[Fähigkeit '{capability}' konnte nicht erfüllt werden. "
            f"Alle Stufen erschöpft: {path}. Letzter Stand siehe fallback_log.]")


def with_fallback(capability: str, fallbacks: list[tuple[str, Callable[..., str]]]):
    """Dekorator-Variante von run_capability: die dekorierte Funktion ist
    Sprosse 1, `fallbacks` sind die weiteren Sprossen (bekommen dieselben Args)."""
    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            ladder = [(fn.__name__, lambda: fn(*args, **kwargs))]
            for name, fb in fallbacks:
                ladder.append((name, functools.partial(fb, *args, **kwargs)))
            return run_capability(capability, ladder)
        return wrapper
    return deco


# ════════════════════════════════════════════════════════════════════════════════
#  R2 — Circuit Breaker (@breaker)
# ════════════════════════════════════════════════════════════════════════════════

def _breaker_get(name: str) -> dict:
    _init_db()
    with _LOCK, _conn() as con:
        row = con.execute(
            "SELECT state, fail_count, opened_at, last_error FROM breaker_state WHERE name=?",
            (name,),
        ).fetchone()
    if not row:
        return {"state": "closed", "fail_count": 0, "opened_at": None, "last_error": None}
    return dict(zip(["state", "fail_count", "opened_at", "last_error"], row))


def _breaker_set(name: str, **fields: Any) -> None:
    _init_db()
    cur = _breaker_get(name)
    cur.update(fields)
    with _LOCK, _conn() as con:
        con.execute(
            "INSERT INTO breaker_state (name, state, fail_count, opened_at, last_error, updated_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET state=excluded.state, "
            "fail_count=excluded.fail_count, opened_at=excluded.opened_at, "
            "last_error=excluded.last_error, updated_at=excluded.updated_at",
            (name, cur["state"], cur["fail_count"], cur["opened_at"],
             cur["last_error"], _now()),
        )
        con.commit()


def breaker_status(name: str | None = None) -> str:
    """Menschlich lesbarer Breaker-Status (für status-mcp / Debugging)."""
    _init_db()
    with _LOCK, _conn() as con:
        if name:
            rows = con.execute(
                "SELECT name, state, fail_count, opened_at, last_error FROM breaker_state WHERE name=?",
                (name,)).fetchall()
        else:
            rows = con.execute(
                "SELECT name, state, fail_count, opened_at, last_error FROM breaker_state").fetchall()
    if not rows:
        return "Keine Breaker-Einträge."
    lines = []
    for n, st, fc, op, err in rows:
        rest = ""
        if st == "open" and op:
            remain = max(0, int(BREAKER_COOLDOWN_SEC - (time.time() - op)))
            rest = f"  (wieder testbar in {remain}s)"
        icon = {"closed": "✅", "open": "🔴", "half_open": "🟡"}.get(st, "?")
        lines.append(f"{icon} {n}: {st}, fails={fc}{rest}"
                     + (f"  letzter Fehler: {str(err)[:120]}" if err and st != "closed" else ""))
    return "\n".join(lines)


def breaker(name: str,
            fail_threshold: int = BREAKER_FAIL_THRESHOLD,
            cooldown_sec: float = BREAKER_COOLDOWN_SEC,
            is_failure: Callable[[Any], bool] | None = None):
    """Circuit Breaker als Dekorator.

    Zustände: closed → (N Fails in Folge) → open → (Cooldown) → half_open
              half_open: 1 Probe-Call. Erfolg → closed, Fehler → wieder open.

    is_failure: optionale Prüfung des RÜCKGABEWERTS (Matrix-Konvention:
                Fehler kommen oft als "[Fehler ...]"-String). Default: genau das.
    """
    if is_failure is None:
        is_failure = lambda r: isinstance(r, str) and r.lstrip().startswith("[Fehler")

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            st = _breaker_get(name)

            if st["state"] == "open":
                elapsed = time.time() - (st["opened_at"] or 0)
                if elapsed < cooldown_sec:
                    remain = int(cooldown_sec - elapsed)
                    return (f"[Breaker '{name}' OFFEN — Komponente vor {int(elapsed)}s "
                            f"deaktiviert nach {st['fail_count']} Fehlschlägen. "
                            f"Nächster Versuch in {remain}s. "
                            f"Letzter Fehler: {str(st['last_error'])[:150]}]")
                # Cooldown vorbei → half-open: genau dieser Call ist die Probe
                _breaker_set(name, state="half_open")

            try:
                result = fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                _register_failure(name, str(e), fail_threshold)
                raise

            if is_failure(result):
                _register_failure(name, str(result), fail_threshold)
            else:
                _breaker_set(name, state="closed", fail_count=0,
                             opened_at=None, last_error=None)
            return result
        return wrapper
    return deco


def _register_failure(name: str, error: str, threshold: int) -> None:
    st = _breaker_get(name)
    fails = st["fail_count"] + 1
    if st["state"] == "half_open" or fails >= threshold:
        _breaker_set(name, state="open", fail_count=fails,
                     opened_at=time.time(), last_error=error)
    else:
        _breaker_set(name, state="closed", fail_count=fails, last_error=error)


# ════════════════════════════════════════════════════════════════════════════════
#  R3 — Idempotenz-Ledger (@idempotent)
# ════════════════════════════════════════════════════════════════════════════════

def _hash_args(args: tuple, kwargs: dict) -> str:
    try:
        blob = json.dumps([args, kwargs], sort_keys=True, default=str)
    except Exception:
        blob = repr((args, kwargs))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def idempotent(key_fn: Callable[..., str] | None = None,
               window: str = "daily"):
    """Idempotenz für Außen-Aktionen (Mail, Telegram, PR, Webhook).

    key_fn: baut aus den Args den Idempotenz-Key (z.B. lambda to, subj, body:
            f"mail:{to}:{subj}"). Default: Funktionsname + Args-Hash.
    window: 'daily' hängt das Datum an den Key (gleiche Mail morgen wieder
            erlaubt), 'forever' nicht.

    Crash-fest: der Key wird VOR der Ausführung als 'pending' geschrieben.
    - Key schon 'done'   → alten Beleg zurückgeben, NICHT erneut senden.
    - Key noch 'pending' → vorheriger Lauf ist mittendrin gecrasht; wir führen
      EINMAL erneut aus (at-least-once kontrolliert, mit Warnvermerk).
    """
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _init_db()
            if key_fn is not None:
                raw_key = key_fn(*args, **kwargs)
            else:
                raw_key = f"{fn.__name__}:{_hash_args(args, kwargs)}"
            if window == "daily":
                raw_key += ":" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]
            args_hash = _hash_args(args, kwargs)

            with _LOCK, _conn() as con:
                row = con.execute(
                    "SELECT status, result, created_at FROM action_ledger WHERE key=?",
                    (key,),
                ).fetchone()
                was_pending = False
                if row:
                    status, prev_result, created = row
                    if status == "done":
                        return (f"[Idempotenz: Aktion wurde bereits am {created} "
                                f"ausgeführt — NICHT erneut gesendet. "
                                f"Damaliges Ergebnis:]\n{prev_result}")
                    was_pending = (status == "pending")
                    # pending/failed → erneuter Versuch erlaubt
                    con.execute(
                        "UPDATE action_ledger SET status='pending', created_at=? WHERE key=?",
                        (_now(), key))
                else:
                    con.execute(
                        "INSERT INTO action_ledger (key, tool, args_hash, status, created_at) "
                        "VALUES (?,?,?,'pending',?)",
                        (key, fn.__name__, args_hash, _now()))
                con.commit()

            try:
                result = fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                with _LOCK, _conn() as con:
                    con.execute(
                        "UPDATE action_ledger SET status='failed', result=?, finished_at=? WHERE key=?",
                        (str(e)[:500], _now(), key))
                    con.commit()
                raise

            failed = isinstance(result, str) and result.lstrip().startswith("[Fehler")
            with _LOCK, _conn() as con:
                con.execute(
                    "UPDATE action_ledger SET status=?, result=?, finished_at=? WHERE key=?",
                    ("failed" if failed else "done",
                     str(result)[:2000], _now(), key))
                con.commit()
            if was_pending and not failed:
                result = (f"{result}\n[Hinweis: vorheriger Versuch dieser Aktion war "
                          f"unvollständig (Crash?); dieser Lauf hat sie abgeschlossen.]")
            return result
        return wrapper
    return deco


# ════════════════════════════════════════════════════════════════════════════════
#  R4 — Checkpoint & Resume
# ════════════════════════════════════════════════════════════════════════════════

def checkpoint(job_id: str, step: int, state: dict) -> None:
    """Schreibt den Zustand NACH einem erfolgreich abgeschlossenen Schritt.
    Konvention: step ist 1-basiert und monoton steigend."""
    _init_db()
    with _LOCK, _conn() as con:
        con.execute(
            "INSERT INTO checkpoints (job_id, step, state_json, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(job_id, step) DO UPDATE SET state_json=excluded.state_json, "
            "created_at=excluded.created_at",
            (job_id, step, json.dumps(state, default=str), _now()),
        )
        con.commit()


def resume_point(job_id: str) -> tuple[int, dict] | None:
    """Letzter GUTER Schritt + dessen State, oder None (Job nie gestartet).
    Aufrufer macht bei Schritt `step + 1` weiter."""
    _init_db()
    with _LOCK, _conn() as con:
        row = con.execute(
            "SELECT step, state_json FROM checkpoints WHERE job_id=? "
            "ORDER BY step DESC LIMIT 1", (job_id,),
        ).fetchone()
    if not row:
        return None
    return int(row[0]), json.loads(row[1])


def clear_checkpoints(job_id: str) -> int:
    """Nach erfolgreichem Job-Abschluss aufräumen. Gibt Anzahl gelöschter Zeilen."""
    _init_db()
    with _LOCK, _conn() as con:
        cur = con.execute("DELETE FROM checkpoints WHERE job_id=?", (job_id,))
        con.commit()
        return cur.rowcount


def run_steps(job_id: str, steps: list[tuple[str, Callable[[dict], dict]]],
              initial_state: dict | None = None) -> dict:
    """R4-Komfort: führt eine Schritt-Liste crash-fest aus.

    Jeder Schritt: (name, fn) mit fn(state) -> neuer state.
    Bei Neustart wird automatisch ab dem letzten guten Schritt fortgesetzt.
    Wirft die Original-Exception des fehlschlagenden Schritts weiter
    (der Checkpoint davor bleibt erhalten)."""
    rp = resume_point(job_id)
    if rp:
        start_idx, state = rp[0], rp[1]
    else:
        start_idx, state = 0, dict(initial_state or {})
    for i in range(start_idx, len(steps)):
        name, fn = steps[i]
        state = fn(state)
        state["_last_step"] = name
        checkpoint(job_id, i + 1, state)
    clear_checkpoints(job_id)
    return state


# ════════════════════════════════════════════════════════════════════════════════
#  NOT-AUS / Kill-Switch (Phase A — D3)
# ════════════════════════════════════════════════════════════════════════════════

_FREEZE_FLAG = Path(r"n:\allinall\openclaw-workspace\state\freeze.flag")


def is_frozen() -> bool:
    """True wenn NOT-AUS aktiv (freeze.flag existiert)."""
    return _FREEZE_FLAG.exists()


def set_freeze(on: bool, reason: str = "") -> None:
    """NOT-AUS setzen (on=True) oder aufheben (on=False)."""
    if on:
        _FREEZE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        _FREEZE_FLAG.write_text(f"{_now()}: {reason or 'NOT-AUS'}", encoding="utf-8")
    else:
        _FREEZE_FLAG.unlink(missing_ok=True)


def check_freeze() -> None:
    """Wirft RuntimeError wenn NOT-AUS aktiv. Vor jedem Langlaeufer-Schritt aufrufen."""
    if _FREEZE_FLAG.exists():
        try:
            msg = _FREEZE_FLAG.read_text(encoding="utf-8").strip()
        except OSError:
            msg = "?"
        raise RuntimeError(
            f"[NOT-AUS AKTIV: {msg}] Alle Agent-Aktionen eingefroren. "
            "notaus_clear.cmd oder set_freeze(False) zum Entsperren."
        )


# ════════════════════════════════════════════════════════════════════════════════
#  Audit-Log (Phase A — V8: Klartext-Args fuer gefaehrliche Calls)
# ════════════════════════════════════════════════════════════════════════════════

_AUDIT_LOG = Path(r"n:\allinall\openclaw-workspace\state\audit.log")


def audit_log(tool: str, args_summary: str, outcome: str = "PENDING") -> None:
    """Klartext-Eintrag fuer jeden gefaehrlichen Call (V8)."""
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = f"[{_now()}] {outcome.upper():12s} | {tool:30s} | {args_summary[:500]}\n"
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass  # Audit-Fehler darf nie den eigentlichen Call zerstoeren


# ════════════════════════════════════════════════════════════════════════════════
#  Selbsttest
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    import tempfile

    # Test-DB statt Produktions-DB
    _DB = Path(tempfile.gettempdir()) / "resilience_test.db"
    if _DB.exists():
        os.unlink(_DB)
    print(f"Selbsttest gegen {_DB}\n")

    # ── R1: Fallback-Leiter ──────────────────────────────────────────────────
    print("R1 — Fallback-Leiter:")
    calls = []

    def primary():
        calls.append("primary")
        raise ProviderTimeout("ollama tot")

    def secondary():
        calls.append("secondary")
        return "Antwort von cloud_cheap"

    r = run_capability("reason", [("ollama", primary), ("cloud_cheap", secondary)])
    assert "Antwort von cloud_cheap" in r and "Primärweg ausgefallen" in r, r
    assert calls == ["primary", "secondary"]
    print("  ok: Abstieg ollama->cloud_cheap, Vermerk in Antwort")

    # Inhaltlicher Fehler darf NICHT fallbacken
    def content_bug():
        return "[Fehler: owner_repo muss 'owner/repo' sein]"

    def never():
        raise AssertionError("darf nie aufgerufen werden")

    r = run_capability("github", [("api", content_bug), ("fallback", never)])
    assert "owner/repo" in r
    print("  ok: inhaltlicher Fehler wird durchgereicht, kein Fallback")

    # ── R2: Circuit Breaker ──────────────────────────────────────────────────
    print("R2 — Circuit Breaker:")
    n_calls = {"n": 0}

    @breaker("testsvc", fail_threshold=3, cooldown_sec=1.0)
    def flaky() -> str:
        n_calls["n"] += 1
        return "[Fehler: service down]"

    for _ in range(3):
        flaky()
    blocked = flaky()                      # 4. Call: Breaker offen
    assert "OFFEN" in blocked, blocked
    assert n_calls["n"] == 3               # 4. Call hat Funktion NICHT erreicht
    print("  ok: nach 3 Fails offen, 4. Call sofort abgewiesen")
    time.sleep(1.1)

    @breaker("testsvc", fail_threshold=3, cooldown_sec=1.0)
    def healthy() -> str:
        return "alles gut"

    r = healthy()                          # half-open Probe → Erfolg → closed
    assert r == "alles gut"
    assert _breaker_get("testsvc")["state"] == "closed"
    print("  ok: nach Cooldown half-open Probe, Erfolg -> closed")

    # ── R3: Idempotenz ───────────────────────────────────────────────────────
    print("R3 — Idempotenz-Ledger:")
    sent = []

    @idempotent(lambda to, body: f"tg:{to}:{body}")
    def send_msg(to: str, body: str) -> str:
        sent.append((to, body))
        return f"gesendet an {to}"

    r1 = send_msg("felix", "hallo")
    r2 = send_msg("felix", "hallo")        # exakt gleiche Aktion
    assert len(sent) == 1, sent            # nur EINMAL wirklich gesendet
    assert "bereits" in r2 and "NICHT erneut" in r2
    r3 = send_msg("felix", "andere nachricht")
    assert len(sent) == 2
    print("  ok: Doppel-Send verhindert, neue Nachricht geht durch")

    # Crash-Szenario: pending-Key überlebt, Wiederholung schließt ab
    @idempotent(lambda x: f"crash:{x}")
    def crashy(x: str) -> str:
        if not getattr(crashy, "second", False):
            crashy.second = True
            raise RuntimeError("crash mitten im Senden")
        return "doch noch gesendet"

    try:
        crashy("a")
    except RuntimeError:
        pass
    r = crashy("a")                        # Retry nach Crash
    assert "doch noch gesendet" in r
    print("  ok: Crash mitten im Senden -> Retry erlaubt und protokolliert")

    # ── R4: Checkpoint & Resume ──────────────────────────────────────────────
    print("R4 — Checkpoint & Resume:")
    executed = []

    def make_step(name, fail=False):
        def step(state):
            if fail:
                raise RuntimeError(f"{name} crasht")
            executed.append(name)
            state[name] = "done"
            return state
        return (name, step)

    steps_crash = [make_step("s1"), make_step("s2"),
                   make_step("s3", fail=True), make_step("s4")]
    try:
        run_steps("job-42", steps_crash)
    except RuntimeError:
        pass
    assert executed == ["s1", "s2"]
    rp = resume_point("job-42")
    assert rp and rp[0] == 2               # letzter guter Schritt = 2
    print("  ok: Crash bei Schritt 3, Checkpoint steht bei 2")

    steps_fixed = [make_step("s1"), make_step("s2"),
                   make_step("s3"), make_step("s4")]
    final = run_steps("job-42", steps_fixed)   # Resume
    assert executed == ["s1", "s2", "s3", "s4"]  # s1/s2 NICHT wiederholt
    assert resume_point("job-42") is None        # aufgeräumt
    print("  ok: Resume ab Schritt 3, s1/s2 nicht wiederholt, Checkpoints geleert")

    print("\nALLE TESTS GRÜN — resilience.py einsatzbereit.")
