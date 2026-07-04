"""
hook_mcp — Outgoing Webhook / n8n-Trigger (N4)
FastMCP-Server: n8n_trigger, webhook_call
Sendet HTTP-Requests an externe Webhooks (n8n, Make, Zapier, eigene APIs).
V6: Webhook-Calls an externe Dienste sind unkritisch wenn der Nutzer URL steuert.
    AGENTS.md: Bei sensiblen Payloads (PII, Credentials) GO einholen.
"""
from mcp.server.fastmcp import FastMCP
import os, json
import hashlib as _hl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import idempotent  # noqa: E402  (R3: Flows nie doppelt anstoßen)

mcp = FastMCP("hook")

def _httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


@mcp.tool()
@idempotent(lambda webhook_url, payload_json="{}", timeout=15:
            f"n8n:{webhook_url}:{_hl.sha256(payload_json.encode()).hexdigest()[:12]}")
def n8n_trigger(webhook_url: str, payload_json: str = "{}", timeout: int = 15) -> str:
    """Sendet einen HTTP-POST an einen n8n/Make/Zapier-Webhook.

    Args:
        webhook_url: Vollständige Webhook-URL (https://...)
        payload_json: JSON-String mit dem Payload (Default: {})
        timeout: Timeout in Sekunden (Default: 15)

    Returns:
        HTTP-Status + Response-Body (gekürzt auf 500 Zeichen).
    """
    httpx = _httpx()
    if httpx is None:
        return "[hook] Fehler: httpx nicht installiert. pip install httpx"

    try:
        payload = json.loads(payload_json) if payload_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"[hook] Ungültiges JSON in payload_json: {e}"

    if not webhook_url.startswith("http"):
        return "[hook] Fehler: webhook_url muss mit http:// oder https:// beginnen."

    try:
        r = httpx.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Schoepfer-Matrix/1.0"},
            timeout=timeout,
        )
        body = r.text[:500] if r.text else "(leer)"
        return f"[n8n_trigger] HTTP {r.status_code}\n{body}"
    except Exception as e:
        return f"[n8n_trigger] Fehler: {e}"


@mcp.tool()
def webhook_call(
    url: str,
    method: str = "POST",
    payload_json: str = "{}",
    headers_json: str = "{}",
    timeout: int = 15,
) -> str:
    """Generischer HTTP-Aufruf (GET/POST/PUT) an einen Webhook oder REST-Endpoint.

    Args:
        url: Ziel-URL
        method: HTTP-Methode (GET, POST, PUT, PATCH) — Default POST
        payload_json: Request-Body als JSON-String (für POST/PUT)
        headers_json: Zusätzliche HTTP-Header als JSON-String
        timeout: Timeout in Sekunden

    Returns:
        HTTP-Status + Response-Body.
    """
    httpx = _httpx()
    if httpx is None:
        return "[hook] Fehler: httpx nicht installiert. pip install httpx"

    method = method.upper().strip()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return f"[hook] Unbekannte Methode: {method}"

    try:
        payload = json.loads(payload_json) if payload_json.strip() else {}
        extra_headers = json.loads(headers_json) if headers_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"[hook] Ungültiges JSON: {e}"

    headers = {"Content-Type": "application/json", "User-Agent": "Schoepfer-Matrix/1.0"}
    headers.update(extra_headers)

    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                r = client.get(url, headers=headers)
            elif method == "DELETE":
                r = client.delete(url, headers=headers)
            else:
                r = client.request(method, url, json=payload, headers=headers)
        body = r.text[:500] if r.text else "(leer)"
        return f"[webhook_call] {method} {url} → HTTP {r.status_code}\n{body}"
    except Exception as e:
        return f"[webhook_call] Fehler: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
