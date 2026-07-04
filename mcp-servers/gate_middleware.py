"""gate_middleware.py — geteilte Approval-Gate-Bibliothek (V6, Phase A).

Verwendung in MCP-Servern:
    from gate_middleware import gate_hold, gate_approve, gate_cancel, gate_list,
                                pending_message

Ablauf (normale Klasse):
    1. Gefaehrliches Tool aufgerufen -> gate_hold(tool, preview) -> gibt gate_id zurueck
    2. Antwort an Agent: f"PENDING {gate_id} -- GO {gate_id} zum Ausfuehren"
    3. User schreibt "GO abc123" -> Agent ruft gate_approve("abc123") auf
    4. True zurueck -> Tool fuehrt die eigentliche Aktion aus

Ablauf (scharfe Klasse — sharp=True):
    1. gate_hold(tool, preview, sharp=True) -> gate_id
    2. Antwort: "PENDING {id} [SCHARF] -- GO {id} <TOTP-Code> zum Ausfuehren"
       (falls kein TOTP eingerichtet: normales GO reicht)
    3. gate_approve(gid, totp_code="123456") -> prueft Code, dann True

Scharfe Klasse: Mail an unbekannte Empfaenger, Shell ausserhalb Workspace,
                Git-Push, PR-Erstellung.

Alle Aktionen werden in audit.log protokolliert (V8).
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(os.environ.get("MATRIX_ROOT", str(Path(__file__).parent.parent)))
_DB = _ROOT / "openclaw-workspace" / "state" / "pending_gates.db"
_EXPIRE_MINUTES = 30
_MCP_ROOT = Path(__file__).parent


def _init() -> None:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS gates (
            id          TEXT PRIMARY KEY,
            tool        TEXT NOT NULL,
            preview     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            sharp       INTEGER NOT NULL DEFAULT 0
        )""")
        # Migration: sharp-Spalte fuer aeltere DB-Versionen
        try:
            c.execute("ALTER TABLE gates ADD COLUMN sharp INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass


def _audit(tool: str, summary: str, outcome: str) -> None:
    try:
        sys.path.insert(0, str(_MCP_ROOT))
        from resilience import audit_log
        audit_log(tool, summary, outcome)
    except Exception:
        pass


def _totp_ready() -> bool:
    sys.path.insert(0, str(_MCP_ROOT))
    try:
        from totp import is_ready
        return bool(is_ready())
    except ImportError:
        return False


def _tg_notify_gate(gid: str, tool: str, preview: str, sharp: bool) -> None:
    """G1: Freigabe per Ein-Tipp-Button aufs Handy. Reply-Keyboard: der Tap sendet
    den Button-Text ("GO <id>") als normale Nutzer-Nachricht durch den Gateway-Fluss
    (kein zweiter getUpdates-Poller moeglich — das Gateway belegt den Kanal).
    Scharfe Gates mit TOTP bekommen KEINEN GO-Button: der Code muss angehaengt werden."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    if not token or not chat:
        return
    try:
        import httpx as _hx
        needs_totp = sharp and _totp_ready()
        if needs_totp:
            text = (f"🔒 PENDING {gid} [SCHARF]\nTool: {tool}\n{preview[:400]}\n\n"
                    f"Freigabe nur mit 2FA: 'GO {gid} <TOTP-Code>' senden — "
                    f"oder unten abbrechen.")
            keyboard = [[{"text": f"NEIN {gid}"}]]
        else:
            text = (f"⏳ PENDING {gid}\nTool: {tool}\n{preview[:400]}\n\n"
                    f"Antippen zum Bestätigen oder Abbrechen:")
            keyboard = [[{"text": f"GO {gid}"}, {"text": f"NEIN {gid}"}]]
        _hx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": text,
                "reply_markup": {
                    "keyboard": keyboard,
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            },
            timeout=10,
        )
    except Exception:
        pass  # Benachrichtigung ist optional — nie den Hauptfluss blockieren


def gate_hold(tool: str, preview: str, sharp: bool = False) -> str:
    """Legt einen Pending-Eintrag an und gibt die 6-stellige Gate-ID zurueck."""
    _init()
    gid = secrets.token_hex(3)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=_EXPIRE_MINUTES)
    with sqlite3.connect(_DB) as c:
        c.execute(
            "INSERT INTO gates (id, tool, preview, created_at, expires_at, sharp) "
            "VALUES (?,?,?,?,?,?)",
            (gid, tool, preview, now.isoformat(), expires.isoformat(), 1 if sharp else 0),
        )
    _audit(tool, preview[:300], "PENDING+TOTP" if sharp else "PENDING")
    _tg_notify_gate(gid, tool, preview, sharp)
    return gid


def gate_approve(gid: str, totp_code: str | None = None) -> bool | str:
    """Genehmigt ein offenes Gate.

    Normale Gates:  gate_approve("abc123")         -> True / False
    Scharfe Gates:  gate_approve("abc123", "123456") -> True / False / str(Fehler)

    Rueckgabe:
      True  = genehmigt
      False = nicht gefunden oder abgelaufen
      str   = TOTP-Fehler (Code fehlt oder falsch)
    """
    _init()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(_DB) as c:
        row = c.execute(
            "SELECT id, tool, preview, sharp FROM gates "
            "WHERE id=? AND status='pending' AND expires_at > ?",
            (gid, now),
        ).fetchone()
        if not row:
            return False
        _, tool, preview, sharp = row

        if sharp:
            sys.path.insert(0, str(_MCP_ROOT))
            try:
                from totp import verify as _verify, is_ready as _ready
                if _ready():
                    if not totp_code:
                        return (f"[TOTP erforderlich: GO {gid} <6-stelliger-Code>. "
                                f"Code aus deiner Authenticator-App eingeben.]")
                    if not _verify(totp_code):
                        return "[TOTP-Code falsch oder abgelaufen. Erneut versuchen.]"
            except ImportError:
                pass  # pyotp nicht installiert -> normales Gate als Fallback

        c.execute("UPDATE gates SET status='approved' WHERE id=?", (gid,))

    _audit(tool, preview[:300], "APPROVED")
    return True


def gate_cancel(gid: str) -> bool:
    """Bricht ein offenes Gate ab. True = erfolgreich abgebrochen."""
    _init()
    with sqlite3.connect(_DB) as c:
        row = c.execute(
            "SELECT tool, preview FROM gates WHERE id=? AND status='pending'", (gid,)
        ).fetchone()
        if row:
            _audit(row[0], row[1][:200], "CANCELLED")
        c.execute(
            "UPDATE gates SET status='cancelled' WHERE id=? AND status='pending'",
            (gid,),
        )
        changed = c.execute("SELECT changes()").fetchone()[0]
    return changed > 0


def gate_list() -> list[dict]:
    """Listet alle noch nicht abgelaufenen Pending-Gates aller MCP-Server."""
    _init()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(_DB) as c:
        rows = c.execute(
            "SELECT id, tool, preview, created_at, expires_at, sharp FROM gates "
            "WHERE status='pending' AND expires_at > ? ORDER BY created_at DESC",
            (now,),
        ).fetchall()
    return [
        {"id": r[0], "tool": r[1], "preview": r[2],
         "created_at": r[3], "expires_at": r[4], "sharp": bool(r[5])}
        for r in rows
    ]


def pending_message(tool: str, preview: str, sharp: bool = False) -> tuple[str, str]:
    """Shortcut: Gate anlegen + Antwort-String bauen. Gibt (gate_id, message) zurueck."""
    gid = gate_hold(tool, preview, sharp=sharp)
    if sharp:
        sys.path.insert(0, str(_MCP_ROOT))
        needs_totp = False
        try:
            from totp import is_ready
            needs_totp = is_ready()
        except ImportError:
            pass
        if needs_totp:
            msg = (f"PENDING {gid} [SCHARF] -- GO {gid} <TOTP-Code> zum Ausfuehren.\n"
                   f"Zweiter Faktor erforderlich (6-stelliger Code aus Authenticator-App).\n\n"
                   f"Tool: {tool}\n{preview}")
        else:
            msg = (f"PENDING {gid} [SCHARF] -- GO {gid} zum Ausfuehren.\n"
                   f"(TOTP noch nicht eingerichtet — totp_setup() ausfuehren fuer echten 2FA)\n\n"
                   f"Tool: {tool}\n{preview}")
    else:
        msg = f"PENDING {gid} -- GO {gid} zum Ausfuehren.\n\nTool: {tool}\n{preview}"
    return gid, msg
