"""OpenClaw Bridge: Python-Implementation des OpenClaw-Gateways.

Läuft auf Port 18789 und bietet die gleiche API wie das TypeScript-OpenClaw:
  GET  /health              → 200 OK
  POST /v1/chat/completions → OpenAI-kompatibel (Proxy zu Ollama)
  POST /classify            → Intent-Klassifikation

Wird automatisch vom OmegaAgent genutzt wenn OpenClaw läuft.
Kann später durch das echte TypeScript-OpenClaw ersetzt werden.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Intent-Klassifikation ────────────────────────────────────────────────

_INTENT_SYSTEM = (
    "Du bist der zentrale Intent-Router. Klassifiziere die Nutzeranfrage.\n"
    "Mögliche Intents: research, science, build, task, review, deploy\n\n"
    "Regeln:\n"
    "- research: Wissensfragen, Recherche, Erklärungen\n"
    "- science: Biochemie, Medizin, Genetik, Proteine, Moleküle\n"
    "- build: Code/App/Bot/Website erstellen\n"
    "- task: Konkrete Aktion (Datei speichern, Web scrapen, Berechnung)\n"
    "- review: Code prüfen (nur nach build)\n"
    "- deploy: Docker, Firebase, Android (nur nach build+review)\n\n"
    "Antworte NUR als JSON, kein Text davor/danach:\n"
    '{"intent":"research","complexity":1,"suggested_agents":["research"],'
    '"plan_hint":"Kurze Strategie"}'
)


class OpenClawBridge:
    """Leichtgewichtiger OpenClaw-kompatibler HTTP-Server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18789,
                 ollama_url: str = "http://localhost:11434",
                 model: str = "llama3.1:8b") -> None:
        self.host = host
        self.port = port
        self.ollama_url = ollama_url
        self.model = model

    def start(self, blocking: bool = True) -> Any:
        """Startet den HTTP-Server."""
        try:
            from fastapi import FastAPI, Request
            from fastapi.responses import JSONResponse
            import uvicorn
            import httpx
        except ImportError:
            logger.error("OpenClaw-Bridge braucht: pip install fastapi uvicorn httpx")
            return None

        app = FastAPI(title="OpenClaw Bridge", version="1.0.0")
        ollama = self.ollama_url
        model = self.model

        @app.get("/health")
        @app.get("/healthz")
        async def health():
            return {"ok": True, "status": "live"}

        @app.get("/ready")
        async def ready():
            return {"ready": True}

        @app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            body = await request.json()
            messages = body.get("messages", [])
            system_msg = ""
            user_msgs = []

            for m in messages:
                if m.get("role") == "system":
                    system_msg = m.get("content", "")
                else:
                    user_msgs.append(m)

            # System-Prompt als separate Nachricht einfügen
            ollama_messages = []
            if system_msg:
                ollama_messages.append({"role": "system", "content": system_msg})
            for m in user_msgs:
                ollama_messages.append({"role": m["role"], "content": m["content"]})

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{ollama}/api/chat",
                    json={
                        "model": model,
                        "messages": ollama_messages,
                        "stream": False,
                        "options": {
                            "temperature": body.get("temperature", 0.3),
                            "num_predict": body.get("max_tokens", 2048),
                        },
                    },
                )
                data = resp.json()
                content = data.get("message", {}).get("content", "")

            return JSONResponse({
                "id": "openclaw-bridge",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
            })

        @app.post("/classify")
        async def classify(request: Request):
            """Klassifiziert eine Nutzeranfrage per LLM."""
            body = await request.json()
            message = body.get("message", "")

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ollama}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _INTENT_SYSTEM},
                            {"role": "user", "content": message},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 200},
                    },
                )
                data = resp.json()
                raw = data.get("message", {}).get("content", "{}")

            # JSON parsen
            try:
                # Code-Fences entfernen
                import re
                raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = {"intent": "research", "complexity": 1,
                          "suggested_agents": ["research"], "plan_hint": ""}

            return JSONResponse(result)

        @app.post("/chat")
        async def chat(request: Request):
            """Einfacher Chat-Endpunkt (non-streaming)."""
            body = await request.json()
            messages = body.get("messages", [])
            system = body.get("system", "")

            ollama_msgs = []
            if system:
                ollama_msgs.append({"role": "system", "content": system})
            ollama_msgs.extend(messages)

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{ollama}/api/chat",
                    json={
                        "model": model,
                        "messages": ollama_msgs,
                        "stream": False,
                        "options": {
                            "temperature": body.get("temperature", 0.3),
                            "num_predict": body.get("max_tokens", 2048),
                        },
                    },
                )
                data = resp.json()
            return JSONResponse(data.get("message", {}))

        @app.get("/")
        async def root():
            return {"openclaw_bridge": "running", "model": model}

        logger.info("OpenClaw-Bridge startet auf http://%s:%d (Modell: %s)", self.host, self.port, model)

        if blocking:
            uvicorn.run(app, host=self.host, port=self.port, log_level="warning")
        else:
            import threading
            t = threading.Thread(
                target=uvicorn.run,
                args=(app,),
                kwargs={"host": self.host, "port": self.port, "log_level": "warning"},
                daemon=True,
            )
            t.start()
            return t


# ── Standalone-Start ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw Bridge")
    parser.add_argument("--port", type=int, default=18789)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ollama", default="http://localhost:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    bridge = OpenClawBridge(
        host=args.host, port=args.port,
        ollama_url=args.ollama, model=args.model,
    )
    bridge.start(blocking=True)
