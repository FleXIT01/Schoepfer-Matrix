"""screenshot-mcp — Bildschirmaufnahme + Vision-Pipeline fuer die Schoepfer-Matrix (Phase B/C, N3).

Ermoeglicht dem Agenten den Bildschirm zu sehen und zu beschreiben:
  1. screenshot_take()        — Desktop-Screenshot (PNG) speichern
  2. vision_pipeline()        — Screenshot + sofortige Beschreibung via llm.vision_describe

Voraussetzung fuer Phase C (Computer-Steuerung):
  "Erst SEHEN, dann HANDELN" — der Agent beobachtet zuerst den Bildschirm,
  schlaegt einen Plan vor, und erst nach GO wird gehandelt.

Abhaengigkeiten: mss (leichtgewichtig) oder Pillow als Fallback.
  pip install mss          (priorisiert)
  pip install pillow       (Fallback: PIL.ImageGrab, nur Windows)

Start (stdio):  python server.py
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import check_freeze  # noqa: E402  (NOT-AUS Phase A)

mcp = FastMCP("screenshot-mcp")

_OUTPUT_DIR = Path(os.environ.get(
    "SCREENSHOT_DIR",
    r"n:\allinall\openclaw-workspace\output\screenshots"
))
_LLM_MCP_SERVER = Path(__file__).parent.parent / "llm_mcp" / "server.py"

# Vision-Fallback-Leiter: qwen3-vl lokal -> cloud (google/gemini-flash)
_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_VISION_MODEL_LOCAL = "qwen3-vl:32b"
_VISION_MODEL_CLOUD = "google/gemini-flash-1.5"
_OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")


# ─── Screenshot-Backends ─────────────────────────────────────────────────────

def _take_with_mss(output_path: Path, region: dict | None) -> str:
    """mss-Backend (bevorzugt, plattformuebergreifend)."""
    try:
        import mss
        import mss.tools
    except ImportError:
        return ""
    with mss.MSS() as sct:
        if region:
            monitor = region
        else:
            monitor = sct.monitors[0]  # gesamter Desktop (alle Monitore)
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=str(output_path))
    return str(output_path)


def _take_with_pil(output_path: Path, region: tuple | None) -> str:
    """PIL/Pillow-Backend (Windows-Fallback via ImageGrab)."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return ""
    img = ImageGrab.grab(bbox=region, all_screens=True)
    img.save(str(output_path), "PNG")
    return str(output_path)


def _take_screenshot(output_path: Path, xywh: str = "") -> str:
    """Nimmt Screenshot auf — versucht mss, dann PIL, dann Fehler."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    region_mss: dict | None = None
    region_pil: tuple | None = None
    if xywh.strip():
        try:
            parts = [int(v.strip()) for v in xywh.split(",")]
            x, y, w, h = parts
            region_mss = {"left": x, "top": y, "width": w, "height": h}
            region_pil = (x, y, x + w, y + h)
        except ValueError:
            return f"[Fehler: region_xywh muss 'x,y,w,h' sein (z.B. '0,0,1920,1080'), bekam: '{xywh}']"

    result = _take_with_mss(output_path, region_mss)
    if result:
        return result
    result = _take_with_pil(output_path, region_pil)
    if result:
        return result
    return ("[Fehler: weder mss noch PIL (Pillow) gefunden.\n"
            "Installieren: pip install mss   oder   pip install pillow]")


# ─── Vision (lokal oder Cloud) ───────────────────────────────────────────────

def _vision_local(image_path: str, question: str) -> str:
    """Ruft qwen3-vl ueber Ollama auf (base64-Bild im payload)."""
    try:
        import httpx
    except ImportError:
        return "[Fehler: httpx nicht installiert]"
    p = Path(image_path)
    if not p.exists():
        return f"[Fehler: Bilddatei nicht gefunden: {image_path}]"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    messages = [{"role": "user", "content": question, "images": [b64]}]
    try:
        r = httpx.post(
            f"{_OLLAMA}/api/chat",
            json={"model": _VISION_MODEL_LOCAL, "messages": messages, "stream": False},
            timeout=420.0,
        )
    except httpx.ConnectError:
        return f"[Fehler: Ollama nicht erreichbar ({_OLLAMA})]"
    except httpx.ReadTimeout:
        return "[Fehler: Zeitüberschreitung bei qwen3-vl (420s)]"
    if r.status_code == 404:
        return (f"[Fehler: {_VISION_MODEL_LOCAL} nicht installiert. "
                f"ollama pull {_VISION_MODEL_LOCAL}]")
    if r.status_code != 200:
        return f"[Fehler: Ollama HTTP {r.status_code}]"
    return (r.json().get("message") or {}).get("content", "").strip() or "[Fehler: leere Antwort]"


def _vision_cloud(image_path: str, question: str) -> str:
    """Ruft Gemini-Flash ueber OpenRouter auf (base64 in content-Teilen)."""
    if not _OPENROUTER_KEY:
        return "[Fehler: kein OPENROUTER_API_KEY fuer Cloud-Vision]"
    try:
        import httpx
    except ImportError:
        return "[Fehler: httpx nicht installiert]"
    p = Path(image_path)
    if not p.exists():
        return f"[Fehler: Bilddatei nicht gefunden: {image_path}]"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    suffix = p.suffix.lower().lstrip(".") or "png"
    mime = f"image/{suffix if suffix in ('png','jpg','jpeg','webp') else 'png'}"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]}]
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": _VISION_MODEL_CLOUD, "messages": messages, "stream": False},
            headers={
                "Authorization": f"Bearer {_OPENROUTER_KEY}",
                "HTTP-Referer": "https://schoepfer-matrix.local",
            },
            timeout=120.0,
        )
    except Exception as e:
        return f"[Fehler: Cloud-Vision-Call fehlgeschlagen: {e}]"
    if r.status_code != 200:
        return f"[Fehler: OpenRouter HTTP {r.status_code}]"
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return "[Fehler: konnte Cloud-Vision-Antwort nicht lesen]"


def _vision_describe(image_path: str, question: str) -> str:
    """Vision-Leiter: qwen3-vl lokal → Cloud-Fallback."""
    result = _vision_local(image_path, question)
    if not result.startswith("[Fehler"):
        return result
    # Fallback auf Cloud
    cloud_result = _vision_cloud(image_path, question)
    if not cloud_result.startswith("[Fehler"):
        return (f"{cloud_result}\n\n"
                f"[Hinweis: qwen3-vl lokal nicht verfuegbar ({result[:80]}); "
                "Ergebnis via Cloud-Vision (Gemini-Flash).]")
    return (f"[Vision-Fehler: Lokales Modell: {result[:120]} | "
            f"Cloud: {cloud_result[:120]}]")


# ─── MCP Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def screenshot_take(output_path: str = "", region_xywh: str = "") -> str:
    """Nimmt einen Screenshot des Desktops auf und speichert ihn als PNG.

    output_path:  Wo die Datei gespeichert wird.
                  Leer = automatischer Zeitstempel unter output/screenshots/.
    region_xywh:  Optionaler Ausschnitt: 'x,y,breite,hoehe' (Pixel).
                  Leer = gesamter Desktop (alle Monitore).

    Gibt den absoluten Dateipfad zurueck — direkt an vision_describe() oder
    llm__vision_describe() weitergeben fuer die Bildanalyse.

    WICHTIG: Lesen = ungated. Dieser Tool nimmt NUR auf, er handelt nicht."""
    check_freeze()

    if output_path.strip():
        p = Path(output_path)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        p = _OUTPUT_DIR / f"screen_{ts}.png"

    result = _take_screenshot(p, region_xywh)
    if result.startswith("[Fehler"):
        return result

    size_kb = p.stat().st_size // 1024 if p.exists() else 0
    return (f"Screenshot gespeichert: {result}\n"
            f"  Groesse: {size_kb} KB\n"
            f"  Region:  {'gesamter Desktop' if not region_xywh.strip() else region_xywh}\n"
            f"\n"
            f"Naechster Schritt: llm__vision_describe(image_path='{result}', question='...')")


@mcp.tool()
def vision_pipeline(question: str = "Was ist auf diesem Bildschirm? Beschreibe genau.",
                    region_xywh: str = "",
                    save_screenshot: bool = True) -> str:
    """Screenshot + Beschreibung in einem Schritt (Read-then-act Vorstufe fuer Phase C).

    Nimmt einen Screenshot und analysiert ihn sofort mit dem Vision-Modell
    (qwen3-vl lokal → Gemini-Flash Cloud als Fallback).

    question:          Was soll das Modell am Bild analysieren/beantworten?
    region_xywh:       Bildschirmbereich 'x,y,w,h' oder leer fuer alles.
    save_screenshot:   True = Datei behalten, False = nach Analyse loeschen.

    Typische Fragen:
      - 'Was steht im Fenster oben rechts?'
      - 'Ist ein Fehlerdialog sichtbar? Beschreibe ihn genau.'
      - 'Welche Schaltflaechen sind klickbar?'

    LESEN: ungated. Dieser Tool schreibt/klickt NICHTS — nur Beobachtung."""
    check_freeze()

    # Screenshot aufnehmen
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = _OUTPUT_DIR / f"vision_{ts}.png"
    result = _take_screenshot(p, region_xywh)
    if result.startswith("[Fehler"):
        return result

    # Vision-Analyse
    answer = _vision_describe(str(p), question)

    # Optional aufraumen
    if not save_screenshot:
        try:
            p.unlink(missing_ok=True)
            saved_note = "Screenshot nach Analyse geloescht."
        except Exception:
            saved_note = f"Screenshot: {p} (Loeschen fehlgeschlagen)"
    else:
        size_kb = p.stat().st_size // 1024 if p.exists() else 0
        saved_note = f"Screenshot: {p} ({size_kb} KB)"

    return (
        f"VISION-PIPELINE\n"
        f"Frage: {question}\n"
        f"{saved_note}\n"
        f"\n"
        f"--- Antwort ---\n"
        f"{answer}"
    )


if __name__ == "__main__":
    # Selbsttest: Screenshot nehmen + Pfad ausgeben
    print("screenshot-mcp Selbsttest")
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = _OUTPUT_DIR / f"selftest_{ts}.png"
    result = _take_screenshot(p, "")
    if result.startswith("[Fehler"):
        print(f"GELB (Screenshot-Backend fehlt): {result}")
    else:
        size = p.stat().st_size // 1024
        print(f"GRUEN: Screenshot -> {result} ({size} KB)")
    mcp.run(transport="stdio")
