"""
webhook_server.py — HTTP-Eingang fuer die Schoepfer-Matrix (N4)
FastAPI-Server, Port 7890, Bearer-Token-Auth.

Endpoints:
  GET  /health          → {"status":"ok"}
  POST /run             → startet matrix.cmd-Agent-Turn, gibt JSON zurueck
  POST /run/async       → startet Turn im Hintergrund, gibt job_id zurueck (future)

Nutzung aus n8n:
  HTTP-Request-Node → POST http://<PC-IP>:7890/run
  Headers: Authorization: Bearer <token>
  Body: {"prompt": "Fasse EGFR-Inhibitoren als PDF zusammen und schick es"}

Token: aus MATRIX_WEBHOOK_TOKEN (secrets.env) oder Default-Token.
"""
import os
import subprocess
import time
import sys

_FASTAPI_OK = False
try:
    from fastapi import FastAPI, HTTPException, Depends, Request
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from pydantic import BaseModel
    import uvicorn
    _FASTAPI_OK = True
except ImportError:
    pass


TOKEN = os.environ.get("MATRIX_WEBHOOK_TOKEN", "schoepfer-matrix-webhook-2026")
MATRIX_CMD = os.environ.get("MATRIX_CMD", r"n:\allinall\matrix.cmd")
OPENCLAW_STATE_DIR = os.environ.get("OPENCLAW_STATE_DIR", "n:/allinall/openclaw-workspace/state")
PORT = int(os.environ.get("WEBHOOK_PORT", "7890"))

if not _FASTAPI_OK:
    print("[webhook_server] FEHLER: FastAPI/uvicorn nicht installiert.")
    print("  Bitte ausfuehren: pip install fastapi uvicorn")
    sys.exit(1)

app = FastAPI(title="Schoepfer-Matrix Webhook", version="1.0", docs_url=None, redoc_url=None)
bearer = HTTPBearer(auto_error=False)


def _check_token(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if TOKEN and (creds is None or creds.credentials != TOKEN):
        raise HTTPException(status_code=401, detail="Ungültiger oder fehlender Bearer-Token")
    return creds.credentials if creds else ""


class RunRequest(BaseModel):
    prompt: str
    session_id: str = ""
    timeout: int = 120


@app.get("/health")
def health():
    return {"status": "ok", "service": "schoepfer-matrix-webhook", "port": PORT}


@app.post("/run")
def run_turn(body: RunRequest, _: str = Depends(_check_token)):
    """Startet einen Agent-Turn via matrix.cmd und gibt das Ergebnis als JSON zurück."""
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="'prompt' darf nicht leer sein")

    # Sicherheitsbereinigung: keine CMD-Injection durch Anführungszeichen im Prompt
    prompt_safe = prompt.replace('"', "'").replace('\r', ' ')

    env = {**os.environ, "OPENCLAW_STATE_DIR": OPENCLAW_STATE_DIR}
    t0 = time.time()
    try:
        result = subprocess.run(
            ["cmd", "/c", MATRIX_CMD, prompt_safe],
            capture_output=True,
            text=True,
            timeout=body.timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
            stdin=subprocess.DEVNULL,
        )
        elapsed = round(time.time() - t0, 1)
        return {
            "ok": result.returncode == 0,
            "result": result.stdout.strip(),
            "elapsed_s": elapsed,
            "exit_code": result.returncode,
            "stderr": result.stderr.strip()[:300] if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Agent-Turn Timeout ({body.timeout}s)")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"matrix.cmd nicht gefunden: {MATRIX_CMD}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print(f"[webhook_server] Starte auf http://127.0.0.1:{PORT}")
    print(f"[webhook_server] Token: {TOKEN[:8]}..." if len(TOKEN) > 8 else f"[webhook_server] Token: {TOKEN}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
