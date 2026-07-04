"""Tool: Allgemeiner HTTP-Request (GET/POST/...)."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"method": "GET", "url": "https://example.com"}
DEFINITION = {
    "name": "http_request",
    "description": "Führt einen HTTP-Request (GET/POST/PUT/DELETE) aus und gibt Status + Body zurück.",
    "input_schema": {
        "type": "object",
        "properties": {
            "method": {"type": "string", "description": "HTTP-Methode"},
            "url": {"type": "string", "description": "Ziel-URL"},
            "body": {"type": "string", "description": "Optionaler Request-Body (JSON-Text)"},
        },
        "required": ["method", "url"],
    },
}


def http_request(method: str, url: str, body: str = "") -> str:
    """Führt einen HTTP-Request aus und gibt Status + Body zurück."""
    import httpx

    if not url.lower().startswith(("http://", "https://")):
        return f"[Fehler: ungültige URL: {url}]"
    method = (method or "GET").upper()
    kwargs: dict = {"timeout": 20.0, "follow_redirects": True}
    if body:
        kwargs["content"] = body
        kwargs["headers"] = {"Content-Type": "application/json"}
    try:
        resp = httpx.request(method, url, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return f"[Fehler beim {method} {url}: {exc}]"
    text = resp.text
    if len(text) > 15000:
        text = text[:15000] + "\n[... gekürzt]"
    return f"[HTTP {resp.status_code}]\n{text}"
