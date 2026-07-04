"""Tool: Autonome Browser-Steuerung (der 'browser_subagent' der Matrix).

Stellt einem Agenten echte Augen und Hände im Web zur Verfügung — auf Basis von
Playwright (Chromium). Eine prozess-globale Browser-Session bleibt über mehrere
Tool-Aufrufe hinweg bestehen, sodass der ReAct-Loop navigieren → klicken →
auslesen → Screenshot in einer Sitzung verketten kann.

Voraussetzung (einmalig):
    pip install playwright
    python -m playwright install chromium

Fehlt Playwright, geben die Tools eine klare Installationsanweisung zurück,
statt zu crashen.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_IMPORTS: list[str] = ["playwright"]

# ── Prozess-globale Browser-Session (über Tool-Aufrufe hinweg persistent) ──────
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"playwright": None, "browser": None, "page": None, "headless": True}

_INSTALL_HINT = (
    "[Browser nicht verfügbar — Playwright fehlt.\n"
    " Installieren mit:\n"
    "   pip install playwright\n"
    "   python -m playwright install chromium]"
)


def _ensure_page(headless: bool = True):
    """Stellt sicher, dass eine Browser-Seite existiert. Gibt (page, None) oder (None, fehler)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, _INSTALL_HINT

    if _STATE["page"] is not None:
        return _STATE["page"], None

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        _STATE.update({"playwright": pw, "browser": browser, "page": page, "headless": headless})
        logger.info("Browser-Session gestartet (headless=%s)", headless)
        return page, None
    except Exception as exc:  # noqa: BLE001
        return None, f"[Browser-Start fehlgeschlagen: {exc}]"


def browser_open(url: str, headless: bool = True) -> str:
    """Öffnet eine URL im (geteilten) Browser und gibt Titel + Kurz-Text zurück."""
    with _LOCK:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if _STATE["page"] is None:
            _STATE["headless"] = headless
        page, err = _ensure_page(headless)
        if err:
            return err
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            text = page.inner_text("body")[:500]
            return f"✓ Geöffnet: {url}\nTitel: {title}\n\nVorschau:\n{text}"
        except Exception as exc:  # noqa: BLE001
            return f"[Navigation fehlgeschlagen ({url}): {exc}]"


def browser_click(selector: str) -> str:
    """Klickt auf ein Element (CSS-Selektor oder sichtbarer Text via text=...)."""
    with _LOCK:
        page = _STATE["page"]
        if page is None:
            return "[Kein Browser offen — zuerst browser_open(url) aufrufen]"
        try:
            page.click(selector, timeout=10000)
            return f"✓ Geklickt: {selector}\nAktuelle URL: {page.url}\nTitel: {page.title()}"
        except Exception as exc:  # noqa: BLE001
            return f"[Klick auf '{selector}' fehlgeschlagen: {exc}]"


def browser_extract_text(selector: str = "body", max_chars: int = 3000) -> str:
    """Liest sichtbaren Text aus der aktuellen Seite (optional nur aus einem Selektor)."""
    with _LOCK:
        page = _STATE["page"]
        if page is None:
            return "[Kein Browser offen — zuerst browser_open(url) aufrufen]"
        try:
            text = page.inner_text(selector)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n[… {len(text)} Zeichen gesamt]"
            return f"Text aus '{selector}' ({page.url}):\n\n{text}"
        except Exception as exc:  # noqa: BLE001
            return f"[Textextraktion aus '{selector}' fehlgeschlagen: {exc}]"


def browser_screenshot(path: str = "", full_page: bool = True) -> str:
    """Macht einen Screenshot der aktuellen Seite und speichert ihn als PNG."""
    with _LOCK:
        page = _STATE["page"]
        if page is None:
            return "[Kein Browser offen — zuerst browser_open(url) aufrufen]"
        if not path:
            import time
            path = f"C:/Users/Farnberger/Downloads/screenshot_{int(time.time())}.png"
        try:
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=path, full_page=full_page)
            return f"✓ Screenshot gespeichert: {path}"
        except Exception as exc:  # noqa: BLE001
            return f"[Screenshot fehlgeschlagen: {exc}]"


def browser_close() -> str:
    """Schließt die Browser-Session und gibt Ressourcen frei."""
    with _LOCK:
        try:
            if _STATE["browser"]:
                _STATE["browser"].close()
            if _STATE["playwright"]:
                _STATE["playwright"].stop()
        except Exception:  # noqa: BLE001
            pass
        finally:
            _STATE.update({"playwright": None, "browser": None, "page": None})
        return "✓ Browser geschlossen."
