"""Webhook-Listener: Empfängt eingehende Messenger-Nachrichten.

Ein leichtgewichtiger FastAPI-Server (Port 9999), der:
  1. Webhooks von LangBot/CowAgent empfängt
  2. Nachrichten als Tasks in eine Queue schreibt
  3. Vom World-Loop über _check_incoming_messages() ausgelesen wird

Start via: python -m generator.agent.services.webhook_listener
Oder automatisch durch: start.py --mode server
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Globale In-Process Queue — World-Loop liest hier aus
_MESSAGE_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)

# Persistente Queue-Datei (überlebt Neustarts)
_QUEUE_FILE = Path.home() / "AppData" / "Local" / "omega" / "message_queue.json"


def get_pending_messages(max_count: int = 10) -> list[dict[str, Any]]:
    """Holt ausstehende Nachrichten aus der Queue. Non-blocking."""
    messages = []
    try:
        while len(messages) < max_count:
            msg = _MESSAGE_QUEUE.get_nowait()
            messages.append(msg)
    except queue.Empty:
        pass

    # Auch persistente Datei prüfen
    messages.extend(_load_persisted_messages())
    return messages


def push_message(platform: str, sender: str, text: str,
                 *, metadata: dict | None = None) -> bool:
    """Schiebt eine neue Nachricht in die Queue (thread-safe)."""
    msg = {
        "platform": platform,
        "sender": sender,
        "text": text,
        "received_at": datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    try:
        _MESSAGE_QUEUE.put_nowait(msg)
        _persist_message(msg)
        logger.info("Nachricht empfangen von %s/%s: %s…", platform, sender, text[:60])
        return True
    except queue.Full:
        logger.warning("Message-Queue voll — Nachricht verworfen")
        return False


def start_server(host: str = "0.0.0.0", port: int = 9999,
                 *, blocking: bool = True) -> threading.Thread | None:
    """Startet den FastAPI Webhook-Server.

    Args:
        host: Bind-Adresse (Standard: alle Interfaces)
        port: Port (Standard: 9999)
        blocking: True = blockiert den aufrufenden Thread (für main-Modus)
                  False = startet im Hintergrund-Thread

    Returns:
        Thread-Objekt wenn blocking=False, sonst None.
    """
    try:
        import uvicorn
        from fastapi import FastAPI, HTTPException, Request
        from pydantic import BaseModel
    except ImportError as exc:
        logger.error(
            "Webhook-Server benötigt: pip install fastapi uvicorn pydantic\n%s", exc
        )
        return None

    app = FastAPI(title="Omega Webhook Receiver", version="1.0")

    class IncomingMessage(BaseModel):
        platform: str
        sender: str
        text: str
        metadata: dict = {}

    @app.get("/health")
    def health():
        return {"status": "ok", "queue_size": _MESSAGE_QUEUE.qsize()}

    @app.post("/webhook/message")
    def receive_message(msg: IncomingMessage):
        """Hauptendpunkt: empfängt Nachrichten von LangBot/CowAgent."""
        ok = push_message(msg.platform, msg.sender, msg.text, metadata=msg.metadata)
        if not ok:
            raise HTTPException(status_code=503, detail="Queue voll")
        return {"status": "queued"}

    @app.post("/webhook/langbot")
    async def langbot_webhook(request: Request):
        """LangBot-spezifischer Webhook (eigenes Payload-Format)."""
        try:
            body = await request.json()
            # LangBot-Format: {"session_id": ..., "message": {"type": "plain", "text": "..."}}
            text = (
                body.get("message", {}).get("text")
                or body.get("text")
                or str(body)
            )
            sender = body.get("sender_id") or body.get("session_id") or "langbot"
            push_message("langbot", sender, text, metadata=body)
            return {"status": "ok"}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webhook/cowagent")
    async def cowagent_webhook(request: Request):
        """CowAgent/WeCom-spezifischer Webhook."""
        try:
            body = await request.json()
            text = body.get("content") or body.get("text") or str(body)
            sender = body.get("fromUser") or body.get("sender") or "cowagent"
            push_message("cowagent", sender, text, metadata=body)
            return {"status": "ok"}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/queue/peek")
    def peek_queue():
        """Debug: Zeigt die Queue ohne zu konsumieren."""
        return {
            "queue_size": _MESSAGE_QUEUE.qsize(),
            "persisted": _load_persisted_messages()[:5],
        }

    logger.info("Webhook-Server startet auf %s:%d", host, port)

    if blocking:
        uvicorn.run(app, host=host, port=port, log_level="warning")
        return None
    else:
        t = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={"host": host, "port": port, "log_level": "warning"},
            daemon=True,
            name="webhook-listener",
        )
        t.start()
        return t


# ── Persistenz ───────────────────────────────────────────────────────────────

def _persist_message(msg: dict) -> None:
    """Schreibt eine Nachricht in die persistente Queue-Datei."""
    try:
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if _QUEUE_FILE.exists():
            try:
                existing = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append(msg)
        # Maximal 50 Nachrichten speichern
        _QUEUE_FILE.write_text(
            json.dumps(existing[-50:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("Persistenz fehlgeschlagen: %s", exc)


def _load_persisted_messages() -> list[dict]:
    """Liest und löscht Nachrichten aus der persistenten Datei."""
    if not _QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
        if data:
            _QUEUE_FILE.write_text("[]", encoding="utf-8")
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ── Standalone-Modus ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Omega Webhook-Listener startet auf Port 9999…")
    print("Endpunkte:")
    print("  POST /webhook/message   — Allgemein")
    print("  POST /webhook/langbot   — LangBot-Format")
    print("  POST /webhook/cowagent  — CowAgent/WeCom-Format")
    print("  GET  /health            — Status")
    start_server(blocking=True)
