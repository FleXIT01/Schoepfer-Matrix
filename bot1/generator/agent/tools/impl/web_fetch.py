"""Tool: Inhalt einer URL abrufen (HTTP GET)."""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"url": "https://example.com"}
DEFINITION = {
    "name": "web_fetch",
    "description": "Ruft den Textinhalt einer URL per HTTP GET ab.",
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Abzurufende URL"}},
        "required": ["url"],
    },
}


_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bot)"}


def web_fetch(url: str) -> str:
    """Ruft den Textinhalt einer URL per HTTP GET ab."""
    import httpx

    if not url.lower().startswith(("http://", "https://")):
        return f"[Fehler: ungültige URL: {url}]"
    try:
        resp = httpx.get(url, timeout=20.0, follow_redirects=True, headers=_HEADERS)
    except Exception as exc:  # noqa: BLE001
        return f"[Fehler beim Abruf von {url}: {exc}]"
    if not (200 <= resp.status_code < 300):
        return f"[HTTP {resp.status_code} von {url}]"
    text = resp.text
    if len(text) > 20000:
        return text[:20000] + f"\n[... gekürzt, {len(text)} Zeichen gesamt]"
    return text
