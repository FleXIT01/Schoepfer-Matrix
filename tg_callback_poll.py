"""tg_callback_poll.py — Telegram Inline-Button-Handler für PENDING-Aktionen (G1).

Polled Telegram auf callback_query-Updates (Tippen auf GO/NO-Buttons) und führt
bestätigte PENDING-Aktionen automatisch aus. Läuft alle 1 Minute via Scheduled Task.

Voraussetzung: TELEGRAM_BOT_TOKEN + TELEGRAM_DEFAULT_CHAT_ID in der Umgebung
(werden durch tg_callback_poll.cmd aus secrets.env geladen).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "tg_callback_state.json"

# mail_mcp-Modul für DB-Zugriff und Ausführungslogik einbinden
_MAIL_MCP = ROOT / "mcp-servers" / "mail_mcp"
sys.path.insert(0, str(_MAIL_MCP))
sys.path.insert(0, str(_MAIL_MCP.parent))  # für resilience.py


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"offset": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _answer_callback(token: str, callback_query_id: str, text: str = "") -> None:
    """Beantwortet callback_query (entfernt Loading-Spinner auf dem Button)."""
    try:
        payload = json.dumps({
            "callback_query_id": callback_query_id,
            "text": text[:200],
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[warn] answerCallbackQuery: {e}", file=sys.stderr)


def _tg_send(token: str, chat_id: str, text: str) -> None:
    """Einfache Bestätigungsnachricht an den Nutzer."""
    try:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text[:4096],
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[tg_callback_poll] TELEGRAM_BOT_TOKEN nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    state = _load_state()
    offset = state.get("offset", 0)

    # Telegram-Updates holen (nur callback_query = Button-Presses)
    try:
        params = urllib.parse.urlencode({
            "offset": offset,
            "limit": 100,
            "allowed_updates": '["callback_query"]',
            "timeout": 0,
        })
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getUpdates?{params}"
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[tg_callback_poll] getUpdates-Fehler: {e}", file=sys.stderr)
        return

    if not data.get("ok"):
        print(f"[tg_callback_poll] Telegram-Fehler: {data}", file=sys.stderr)
        return

    updates = data.get("result", [])
    if not updates:
        return

    # mail_mcp-Funktionen importieren
    try:
        from server import (_get_pending, _set_status,  # noqa: PLC0415
                            _do_email_send, _do_telegram_send,
                            _do_telegram_send_voice)
    except ImportError as e:
        print(f"[tg_callback_poll] mail_mcp Import-Fehler: {e}", file=sys.stderr)
        sys.exit(1)

    processed = 0
    for update in updates:
        update_id = update.get("update_id", 0)
        offset = max(offset, update_id + 1)

        cq = update.get("callback_query")
        if not cq:
            continue

        callback_id = cq.get("id", "")
        callback_data = cq.get("data", "")
        msg = cq.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))

        if callback_data.startswith("confirm_"):
            pid = callback_data[len("confirm_"):]
            rec = _get_pending(pid)
            if not rec:
                _answer_callback(token, callback_id, "Ticket nicht gefunden oder abgelaufen.")
                continue
            if rec["status"] != "pending":
                _answer_callback(token, callback_id,
                                 f"Ticket bereits '{rec['status']}' — nichts zu tun.")
                continue

            _answer_callback(token, callback_id, "Wird ausgeführt…")
            _set_status(pid, "done")

            payload = json.loads(rec["payload"])
            action = rec["action"]
            try:
                if action == "email":
                    result = _do_email_send(
                        payload["to"], payload["subject"],
                        payload["body"], payload.get("attachment_path", ""))
                elif action == "telegram":
                    result = _do_telegram_send(
                        payload["file_path"], payload.get("caption", ""),
                        payload["chat_id"])
                elif action == "telegram_voice":
                    result = _do_telegram_send_voice(
                        payload["file_path"], payload.get("caption", ""),
                        payload["chat_id"])
                else:
                    result = f"[Unbekannte Aktion '{action}']"
            except Exception as ex:  # noqa: BLE001
                result = f"[Ausführungsfehler: {ex}]"
                _set_status(pid, "failed")

            _tg_send(token, chat_id, f"✅ {result}")
            print(f"[tg_callback_poll] confirm {pid}: {str(result)[:100]}")
            processed += 1

        elif callback_data.startswith("cancel_"):
            pid = callback_data[len("cancel_"):]
            rec = _get_pending(pid)
            if not rec or rec["status"] != "pending":
                _answer_callback(token, callback_id,
                                 "Ticket nicht gefunden oder bereits erledigt.")
                continue
            _set_status(pid, "cancelled")
            _answer_callback(token, callback_id, "Abgebrochen.")
            _tg_send(token, chat_id,
                     f"🚫 Ticket {pid} abgebrochen: {rec['description'][:100]}")
            print(f"[tg_callback_poll] cancel {pid}")
            processed += 1

    state["offset"] = offset
    _save_state(state)
    print(f"[tg_callback_poll] {processed}/{len(updates)} Update(s) verarbeitet. Offset: {offset}")


if __name__ == "__main__":
    main()
