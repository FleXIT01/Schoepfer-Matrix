"""mail-mcp — Zustellung (E-Mail via SMTP + Telegram-Datei) als MCP-Server.

V6 APPROVAL GATE: email_send und telegram_send legen zunächst einen PENDING-Eintrag
an und antworten mit "PENDING <id>: ... — GO <id> zum Ausführen". Erst wenn der Nutzer
"GO <id>" schickt und der Agent confirm_action("<id>") aufruft, wird wirklich gesendet.
So kann kein Versand „aus Versehen" passieren.

KONFIGURATION (zwei Wege, Datei gewinnt vor Env):
  1) Bequem & umschaltbar:  `mailcfg.cmd` ausführen -> schreibt mail_account.json
     (Provider Outlook/Gmail/… + Absender + App-Passwort). Jederzeit neu ausführen
     zum Umstellen. Danach Gateway neu starten.
  2) Env-Variablen: SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, SMTP_FROM,
     SMTP_STARTTLS (1).  Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_DEFAULT_CHAT_ID.

WICHTIG: Es gibt KEINEN Standard-Empfänger für E-Mail — die Zieladresse muss immer
angegeben werden (sonst beim Nutzer nachfragen).

Tools:
  - email_send(to, subject, body, attachment_path) -> PENDING <id>  (Approval Gate)
  - telegram_send(file_path, caption, chat_id)     -> PENDING <id>  (Approval Gate, nur Fremd-Chats)
  - confirm_action(id)                             -> führt PENDING-Aktion aus (nach GO <id>)
  - list_pending()                                 -> zeigt offene Tickets
  - cancel_action(id)                              -> bricht Ticket ab
  - delivery_status()                              -> was ist konfiguriert?

Start (stdio):  python server.py
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import smtplib
import sqlite3
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import idempotent, check_freeze  # noqa: E402  (R3 + NOT-AUS Phase A)

import hashlib as _hl


def _stable(text: str) -> str:
    """Prozess-stabiler Kurz-Hash (hash() ist pro Prozess randomisiert —
    würde die Crash-Restart-Idempotenz aushebeln)."""
    return _hl.sha256((text or "").encode()).hexdigest()[:12]

logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = FastMCP("mail-mcp")

_CFG_FILE = Path(os.environ.get(
    "MAIL_ACCOUNT_FILE", str(Path(__file__).parent / "mail_account.json")))
_DB_PATH = Path(__file__).parent / "pending.db"
_PENDING_MINUTES = 15


# ─── DB ───────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    with sqlite3.connect(_DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pending_actions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            action TEXT NOT NULL,
            description TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )""")
        c.commit()

_init_db()


def _tg_send_approval_buttons(pid: str, description: str) -> None:
    """G1: Sendet Telegram-Nachricht mit GO/NO Inline-Buttons für PENDING-Aktionen."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    if not token or not chat:
        return
    try:
        import httpx as _hx
        payload = {
            "chat_id": chat,
            "text": f"⏳ PENDING {pid}\n{description}\n\nAktion bestätigen?",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ GO", "callback_data": f"confirm_{pid}"},
                    {"text": "❌ NO", "callback_data": f"cancel_{pid}"},
                ]]
            },
        }
        _hx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload, timeout=10,
        )
    except Exception:  # noqa: BLE001
        pass  # Buttons sind optional — nie den Hauptfluss blockieren


def _new_pending(action: str, description: str, payload: dict) -> str:
    """Legt einen PENDING-Eintrag an, gibt die ID zurück und sendet Inline-Buttons (G1)."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=_PENDING_MINUTES)
    pid = secrets.token_hex(3)  # 6-stellig, z.B. "a3f9c1"
    with sqlite3.connect(_DB_PATH) as c:
        c.execute(
            "INSERT INTO pending_actions (id,created_at,expires_at,action,description,payload,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, now.isoformat(), expires.isoformat(), action,
             description, json.dumps(payload), "pending"))
        c.commit()
    _tg_send_approval_buttons(pid, description)
    return pid


def _get_pending(pid: str) -> dict | None:
    with sqlite3.connect(_DB_PATH) as c:
        row = c.execute(
            "SELECT id,created_at,expires_at,action,description,payload,status "
            "FROM pending_actions WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    return dict(zip(["id","created_at","expires_at","action","description","payload","status"], row))


def _set_status(pid: str, status: str) -> None:
    with sqlite3.connect(_DB_PATH) as c:
        c.execute("UPDATE pending_actions SET status=? WHERE id=?", (status, pid))
        c.commit()


# ─── SMTP / Telegram helpers ──────────────────────────────────────────────────

def _cfg() -> dict:
    c = {
        "host": os.environ.get("SMTP_HOST", "smtp-mail.outlook.com"),
        "port": int(os.environ.get("SMTP_PORT", "587") or "587"),
        "starttls": os.environ.get("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no"),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "from": os.environ.get("SMTP_FROM", ""),
        "provider": "env",
    }
    if _CFG_FILE.exists():
        try:
            data = json.loads(_CFG_FILE.read_text(encoding="utf-8"))
            for k in ("host", "port", "starttls", "user", "password", "from", "provider"):
                if k in data and data[k] not in (None, ""):
                    c[k] = data[k]
        except Exception:  # noqa: BLE001
            pass
    frm = (c["from"] or "").strip()
    if "@" not in frm:
        frm = c["user"]
    c["from"] = frm
    c["port"] = int(c["port"])
    return c


@idempotent(lambda to, subject, body, attachment_path:
            f"mail:{to}:{subject}:{_stable(body)}")
def _do_email_send(to: str, subject: str, body: str, attachment_path: str) -> str:
    """Führt den echten E-Mail-Versand aus. R3: identische Mail (Empfänger+
    Betreff+Body) wird am selben Tag nie zweimal gesendet, auch nicht nach Crash."""
    cfg = _cfg()
    if not cfg["user"] or not cfg["password"]:
        return ("[Fehler: E-Mail-Versand nicht eingerichtet. `mailcfg.cmd` ausführen.]")
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = to
    msg["Subject"] = subject or "(ohne Betreff)"
    msg.set_content(body or "")
    att_note = ""
    ap = (attachment_path or "").strip().strip('"')
    if ap:
        p = Path(ap)
        if not p.exists():
            return f"[Fehler: Anhang nicht gefunden: {p}]"
        ctype, _ = mimetypes.guess_type(str(p))
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        try:
            msg.add_attachment(p.read_bytes(), maintype=maintype,
                               subtype=subtype, filename=p.name)
        except Exception as e:  # noqa: BLE001
            return f"[Fehler beim Anhängen von {p.name}: {e}]"
        att_note = f" + Anhang '{p.name}'"
    ctx = ssl.create_default_context()
    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=60, context=ctx) as s:
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=60) as s:
                s.ehlo()
                if cfg["starttls"]:
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        return (f"[Fehler: SMTP-Login abgelehnt. App-Passwort prüfen. ({e})]")
    except (smtplib.SMTPException, OSError) as e:
        return f"[Fehler: {cfg['host']}:{cfg['port']}: {e}]"
    return f"E-Mail gesendet an {to} (Betreff: '{subject}'){att_note}."


@idempotent(lambda file_path, caption, chat_id:
            f"tgdoc:{chat_id}:{file_path}:{_stable(caption)}")
def _do_telegram_send(file_path: str, caption: str, chat_id: str) -> str:
    """Führt den echten Telegram-Upload aus. R3: gleiche Datei+Caption an
    denselben Chat wird am selben Tag nie doppelt gesendet."""
    import httpx
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = (chat_id or os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")).strip()
    if not token:
        return "[Fehler: TELEGRAM_BOT_TOKEN nicht gesetzt.]"
    if not chat:
        return "[Fehler: kein Chat-Ziel gesetzt.]"
    p = Path((file_path or "").strip().strip('"'))
    if not p.exists():
        return f"[Fehler: Datei nicht gefunden: {p}]"
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with p.open("rb") as fh:
            data = {"chat_id": chat}
            if caption:
                data["caption"] = caption[:1024]
            r = httpx.post(url, data=data, files={"document": (p.name, fh)}, timeout=120)
    except Exception as e:  # noqa: BLE001
        return f"[Fehler beim Telegram-Upload: {e}]"
    if r.status_code != 200 or not (r.json() or {}).get("ok"):
        return f"[Fehler: Telegram HTTP {r.status_code}: {r.text[:200]}]"
    return f"Datei '{p.name}' an Telegram-Chat {chat} gesendet."


def _wav_to_ogg(wav_path: Path) -> Path:
    """Konvertiert WAV → OGG/Opus (für Telegram sendVoice). Benötigt ffmpeg."""
    import subprocess
    ogg_path = wav_path.with_suffix(".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-c:a", "libopus", "-b:a", "32k", str(ogg_path)],
            check=True, capture_output=True, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg OGG-Konvertierung fehlgeschlagen: {e.stderr.decode()[:200]}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg nicht gefunden. Installation: winget install ffmpeg")
    return ogg_path


def _do_telegram_send_voice(file_path: str, caption: str, chat_id: str) -> str:
    """Schickt eine OGG/Opus-Datei als Telegram-Sprachnachricht (sendVoice)."""
    import httpx
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = (chat_id or os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")).strip()
    if not token:
        return "[Fehler: TELEGRAM_BOT_TOKEN nicht gesetzt.]"
    if not chat:
        return "[Fehler: kein Chat-Ziel gesetzt.]"

    src = Path((file_path or "").strip().strip('"'))
    if not src.exists():
        return f"[Fehler: Datei nicht gefunden: {src}]"

    # WAV automatisch konvertieren
    ogg = src
    if src.suffix.lower() != ".ogg":
        try:
            ogg = _wav_to_ogg(src)
        except RuntimeError as e:
            return f"[Fehler: {e}]"

    url = f"https://api.telegram.org/bot{token}/sendVoice"
    try:
        with ogg.open("rb") as fh:
            data = {"chat_id": chat}
            if caption:
                data["caption"] = caption[:1024]
            r = httpx.post(url, data=data, files={"voice": (ogg.name, fh, "audio/ogg")}, timeout=120)
    except Exception as e:  # noqa: BLE001
        return f"[Fehler beim Telegram-Voice-Upload: {e}]"
    if r.status_code != 200 or not (r.json() or {}).get("ok"):
        return f"[Fehler: Telegram HTTP {r.status_code}: {r.text[:200]}]"
    return f"Sprachnachricht '{ogg.name}' an Telegram-Chat {chat} gesendet."


# ─── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def email_send(to: str, subject: str, body: str, attachment_path: str = "") -> str:
    """Stellt eine E-Mail in die APPROVAL-WARTESCHLANGE.
    Gibt PENDING <id> zurück — der Nutzer muss 'GO <id>' bestätigen, erst dann wird
    gesendet. `to` = Empfänger (PFLICHT), `subject` = Betreff, `body` = Text,
    `attachment_path` = ABSOLUTER Pfad der Datei (z.B. erzeugtes PDF).
    KEIN Standard-Empfänger — fehlt 'to', beim Nutzer nachfragen."""
    to = (to or "").strip()
    if not to:
        return ("[Kein Empfänger angegeben. Es gibt keinen Standard-Empfänger — "
                "bitte den Nutzer nach der Ziel-E-Mail-Adresse fragen.]")
    att = (attachment_path or "").strip().strip('"')
    att_note = f", Anhang: {Path(att).name}" if att else ""
    desc = f"E-Mail an {to} | Betreff: '{subject}'{att_note}"
    pid = _new_pending("email", desc, {
        "to": to, "subject": subject, "body": body, "attachment_path": att})
    return (f"PENDING {pid}: {desc}\n"
            f"→ Antworte mit **GO {pid}** um wirklich zu senden "
            f"(Ticket läuft in {_PENDING_MINUTES} Min ab).")


@mcp.tool()
def telegram_send(file_path: str, caption: str = "", chat_id: str = "") -> str:
    """Schickt eine DATEI (z.B. PDF) via Telegram — gated für Fremd-Chats.
    An den eigenen (Standard-)Chat wird direkt gesendet.
    An fremde chat_id → PENDING <id>, Nutzer muss 'GO <id>' bestätigen.
    `file_path` = ABSOLUTER Pfad, `caption` = Begleittext, `chat_id` = Ziel (leer = Standard)."""
    default_chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    target = (chat_id or default_chat or "").strip()
    p_path = (file_path or "").strip().strip('"')

    # Eigener Chat → kein Gate, sofort senden
    if not chat_id or chat_id.strip() == default_chat:
        return _do_telegram_send(p_path, caption, target)

    # Fremder Chat → Gate
    fname = Path(p_path).name if p_path else "(unbekannt)"
    desc = f"Telegram-Datei '{fname}' an Chat {target}"
    pid = _new_pending("telegram", desc, {
        "file_path": p_path, "caption": caption, "chat_id": target})
    return (f"PENDING {pid}: {desc}\n"
            f"→ Antworte mit **GO {pid}** um wirklich zu senden "
            f"(Ticket läuft in {_PENDING_MINUTES} Min ab).")


@mcp.tool()
def telegram_send_voice(file_path: str, caption: str = "", chat_id: str = "") -> str:
    """Schickt eine Audiodatei als Telegram-SPRACHNACHRICHT (sendVoice, kein Gate für eigenen Chat).
    WAV-Dateien werden automatisch nach OGG/Opus konvertiert (benötigt ffmpeg).
    Für: Podcast-Ergebnis, TTS-Antwort, Audio-Bericht. Eigener Standard-Chat: sofort.
    `file_path` = ABSOLUTER Pfad zur WAV/OGG-Datei."""
    default_chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    target = (chat_id or "").strip() or default_chat
    if not target or target == default_chat:
        return _do_telegram_send_voice(file_path, caption, target)
    # Fremder Chat → Gate
    fname = Path(file_path).name if file_path else "(unbekannt)"
    desc = f"Telegram Sprachnachricht '{fname}' an Chat {target}"
    pid = _new_pending("telegram_voice", desc,
                       {"file_path": file_path, "caption": caption, "chat_id": target})
    return (f"PENDING {pid}: {desc}\n"
            f"→ Antworte mit **GO {pid}** um wirklich zu senden "
            f"(Ticket läuft in {_PENDING_MINUTES} Min ab).")


@mcp.tool()
def confirm_action(id: str) -> str:
    """Führt eine PENDING-Aktion aus (nachdem der Nutzer 'GO <id>' geschickt hat).
    `id` = die 6-stellige Ticket-ID aus dem PENDING-Ergebnis von email_send/telegram_send.
    Gibt Erfolg oder Fehlermeldung zurück."""
    pid = (id or "").strip().lower()
    rec = _get_pending(pid)
    if not rec:
        return f"[Ticket '{pid}' nicht gefunden — bereits abgelaufen oder unbekannt.]"
    if rec["status"] != "pending":
        return f"[Ticket '{pid}' ist bereits {rec['status']} und kann nicht mehr ausgeführt werden.]"
    # Ablauf prüfen
    exp = datetime.fromisoformat(rec["expires_at"])
    if datetime.now(timezone.utc) > exp:
        _set_status(pid, "expired")
        return f"[Ticket '{pid}' ist abgelaufen. Aktion bitte erneut aufrufen.]"

    check_freeze()  # NOT-AUS: kein Versand waehrend Freeze
    payload = json.loads(rec["payload"])
    _set_status(pid, "done")

    if rec["action"] == "email":
        return _do_email_send(
            payload["to"], payload["subject"],
            payload["body"], payload.get("attachment_path", ""))
    elif rec["action"] == "telegram":
        return _do_telegram_send(
            payload["file_path"], payload.get("caption", ""),
            payload["chat_id"])
    elif rec["action"] == "telegram_voice":
        return _do_telegram_send_voice(
            payload["file_path"], payload.get("caption", ""),
            payload["chat_id"])
    else:
        return f"[Unbekannte Aktion '{rec['action']}' in Ticket {pid}.]"


@mcp.tool()
def list_pending() -> str:
    """Zeigt alle offenen PENDING-Aktionen (Email/Telegram, noch nicht bestätigt/abgelaufen).
    Für: dem Nutzer zeigen, was noch auf Bestätigung wartet."""
    now = datetime.now(timezone.utc)
    with sqlite3.connect(_DB_PATH) as c:
        rows = c.execute(
            "SELECT id, action, description, expires_at FROM pending_actions "
            "WHERE status='pending' ORDER BY created_at DESC").fetchall()
    if not rows:
        return "Keine offenen PENDING-Aktionen."
    lines = ["Offene PENDING-Aktionen:"]
    for row in rows:
        pid, action, desc, exp_str = row
        exp = datetime.fromisoformat(exp_str)
        mins_left = max(0, int((exp - now).total_seconds() / 60))
        expired = " [ABGELAUFEN]" if now > exp else f" (noch {mins_left} Min)"
        lines.append(f"  {pid} [{action}] {desc}{expired}")
    lines.append("\nMit 'GO <id>' bestätigen oder 'CANCEL <id>' abbrechen.")
    return "\n".join(lines)


@mcp.tool()
def cancel_action(id: str) -> str:
    """Bricht eine PENDING-Aktion ab.
    `id` = die 6-stellige Ticket-ID. Gibt Bestätigung zurück."""
    pid = (id or "").strip().lower()
    rec = _get_pending(pid)
    if not rec:
        return f"[Ticket '{pid}' nicht gefunden.]"
    if rec["status"] != "pending":
        return f"[Ticket '{pid}' ist bereits {rec['status']}.]"
    _set_status(pid, "cancelled")
    return f"Ticket {pid} abgebrochen: {rec['description']}"


@mcp.tool()
def delivery_status() -> str:
    """Zeigt, welche Zustellwege eingerichtet sind (ohne Passwörter zu verraten).
    Für: prüfen, ob email_send / telegram_send funktionieren werden."""
    cfg = _cfg()
    mail_ok = bool(cfg["user"] and cfg["password"])
    tg_ok = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    src = "mail_account.json" if _CFG_FILE.exists() else "Env"
    with sqlite3.connect(_DB_PATH) as c:
        pending_count = c.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status='pending'").fetchone()[0]
    return (f"ZUSTELLUNG:\n"
            f"  E-Mail:   {'EINGERICHTET' if mail_ok else 'NICHT eingerichtet'} "
            f"(Quelle {src}; Provider={cfg.get('provider')}, {cfg['host']}:{cfg['port']}, "
            f"Absender={cfg['from'] or '—'})\n"
            f"  Telegram: {'EINGERICHTET' if tg_ok else 'NICHT eingerichtet'} "
            f"(Standard-Chat={os.environ.get('TELEGRAM_DEFAULT_CHAT_ID', '—')})\n"
            f"  Approval-Gate: AKTIV (offene Tickets: {pending_count})\n"
            f"  Hinweis: KEIN Standard-Empfänger für E-Mail — Adresse immer angeben.")


if __name__ == "__main__":
    mcp.run()
