"""pdf-mcp — PDF lesen, zusammenfassen und übersetzen als MCP-Server.

Self-contained (pypdf + lokales Ollama-Modell). Ersetzt die Rolle von
PDFMathTranslate/nano-pdf für die Alltagsfälle, ohne schwere Modelle/Cloud:

  - pdf_extract(pdf_path)            -> roher Text (Seiten wählbar)
  - pdf_summarize(pdf_path)          -> deutsche Zusammenfassung (lokales Modell)
  - pdf_translate(pdf_path, lang)    -> Übersetzung in Zielsprache (lokales Modell)

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pdf-mcp")

_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_MODEL = os.environ.get("PDF_MODEL", "gpt-oss-32k")


def _ollama_chat(messages: list[dict], *, timeout: float = 300.0,
                 num_ctx: int = 16384) -> str:
    import httpx

    payload = {"model": _MODEL, "messages": messages, "stream": False,
               "options": {"num_ctx": num_ctx}}
    try:
        r = httpx.post(f"{_OLLAMA}/api/chat", json=payload, timeout=timeout)
    except httpx.ConnectError:
        return f"[Fehler: Ollama nicht erreichbar unter {_OLLAMA}.]"
    except httpx.ReadTimeout:
        return f"[Fehler: Zeitüberschreitung ({timeout:.0f}s) bei Modell '{_MODEL}'.]"
    if r.status_code != 200:
        return f"[Fehler: Ollama HTTP {r.status_code}: {r.text[:200]}]"
    return ((r.json().get("message") or {}).get("content", "").strip()
            or "[Fehler: leere Modellantwort.]")


def _extract(pdf_path: str, max_pages: int) -> tuple[str, int, str]:
    """Liefert (text, seiten_gelesen, fehler)."""
    p = Path(pdf_path)
    if not p.exists():
        return "", 0, f"PDF nicht gefunden: {pdf_path}"
    if p.suffix.lower() != ".pdf":
        return "", 0, f"Keine PDF-Datei: {pdf_path}"
    try:
        from pypdf import PdfReader
    except Exception as e:  # noqa: BLE001
        return "", 0, f"pypdf fehlt: {e} (pip install pypdf)"
    try:
        reader = PdfReader(str(p))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                return "", 0, "PDF ist verschlüsselt (Passwort nötig)."
        pages = reader.pages[:max_pages]
        chunks = []
        for i, page in enumerate(pages):
            txt = (page.extract_text() or "").strip()
            if txt:
                chunks.append(f"--- Seite {i + 1} ---\n{txt}")
        text = "\n\n".join(chunks)
        if not text.strip():
            return "", len(pages), ("Kein extrahierbarer Text — vermutlich ein "
                                    "gescanntes PDF (Bild). OCR nötig.")
        return text, len(pages), ""
    except Exception as e:  # noqa: BLE001
        return "", 0, f"Lesefehler: {e}"


_PDF_OUT = os.environ.get("PDF_OUT_DIR", "n:/allinall/openclaw-workspace/output")
_RENDERER = str(Path(__file__).parent / "render_pdf.py")


def _safe_name(title: str) -> str:
    import re
    base = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "_")[:60]
    return base or "dokument"


def _render_pdf(title: str, content: str, out_path: Path) -> tuple[int, str]:
    """Rendert das PDF in einem SUBPROZESS (render_pdf.py). So berührt die laute
    fpdf2/fontTools-Ausgabe niemals den MCP-stdio-Kanal dieses Servers. Liefert
    (seiten, fehler)."""
    import json
    import subprocess
    import sys
    import tempfile

    payload = {"title": title, "content": content, "out": str(out_path)}
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(payload, tf)
        tf.close()
        # WICHTIG: stdin/stderr NICHT erben/capturen — sonst hängt der Aufruf, wenn der
        # Server als MCP-stdio-Prozess läuft (geerbte stdin-Pipe blockiert auf Windows).
        # stdout=PIPE liefert das JSON-Ergebnis, stderr verwerfen (fontTools-Lärm).
        proc = subprocess.run([sys.executable, _RENDERER, tf.name],
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return 0, "Render-Subprozess Zeitüberschreitung (120s)."
    except Exception as e:  # noqa: BLE001
        return 0, f"Render-Subprozess nicht startbar: {e}"
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass

    res = {}
    for ln in reversed((proc.stdout or "").strip().splitlines()):
        try:
            res = json.loads(ln)
            break
        except Exception:  # noqa: BLE001
            continue
    if proc.returncode != 0 or "error" in res or "pages" not in res:
        detail = res.get("error") or (proc.stderr or "").strip()[-300:] or "unbekannt"
        return 0, f"Render fehlgeschlagen: {detail}"
    return int(res.get("pages", 0)), ""


@mcp.tool()
def pdf_create(title: str, content: str, filename: str = "") -> str:
    """Erzeugt EINE NEUE PDF aus Titel + Text/Markdown und speichert sie als Datei.
    Für: Recherche-Ergebnisse, Berichte oder Zusammenfassungen als PDF ausgeben
    (z.B. um sie dann zu verschicken). `title` = Überschrift, `content` = der Text
    (einfaches Markdown: '# Überschrift', '## ', '- Aufzählung', **fett** werden
    formatiert), `filename` = optionaler Dateiname (sonst aus dem Titel abgeleitet).
    Gibt den ABSOLUTEN PFAD der erzeugten PDF zurück (für mail email_send o.ä.)."""
    if not (content or "").strip():
        return "[Fehler: leerer Inhalt — nichts zu schreiben.]"
    raw = (filename or title or "").strip()
    if raw.lower().endswith(".pdf"):  # Endung vor dem Sanitizing abtrennen
        raw = raw[:-4]
    out = Path(_PDF_OUT) / (_safe_name(raw) + ".pdf")
    pages, err = _render_pdf(title, content, out)
    if err:
        return f"[Fehler: {err}]"
    size_kb = out.stat().st_size / 1024 if out.exists() else 0
    return (f"PDF erstellt: {out}\n"
            f"  Titel: {title.strip()}\n  Seiten: {pages}  Größe: {size_kb:.0f} KB\n"
            f"Diesen Pfad kannst du an email_send (attachment_path) übergeben.")


@mcp.tool()
def pdf_extract(pdf_path: str, max_pages: int = 30) -> str:
    """Extrahiert den Text aus einer PDF-Datei (bis max_pages Seiten).
    Für: Inhalt einer PDF lesbar machen, bevor man sie weiterverarbeitet.
    `pdf_path` = Pfad zur PDF, `max_pages` = max. Seitenzahl."""
    text, n, err = _extract(pdf_path, max(1, min(200, max_pages)))
    if err:
        return f"[Fehler: {err}]"
    head = f"PDF-TEXT ({n} Seiten gelesen) — {Path(pdf_path).name}\n" + "=" * 50 + "\n"
    return head + text


@mcp.tool()
def pdf_summarize(pdf_path: str, max_pages: int = 30, focus: str = "") -> str:
    """Fasst eine PDF auf Deutsch zusammen (lokales Modell, ohne Cloud).
    Für: schnell verstehen, worum es in einem Dokument/Paper geht.
    `pdf_path` = Pfad zur PDF, `max_pages` = wie viele Seiten einbeziehen,
    `focus` = optionaler Schwerpunkt (z.B. 'Methodik', 'Ergebnisse')."""
    text, n, err = _extract(pdf_path, max(1, min(120, max_pages)))
    if err:
        return f"[Fehler: {err}]"
    if len(text) > 26000:
        text = text[:26000] + "\n…[gekürzt]"
    focus_line = f" Lege den Schwerpunkt auf: {focus}." if focus.strip() else ""
    prompt = (
        f"Fasse das folgende PDF-Dokument auf Deutsch strukturiert zusammen "
        f"(Kurzfazit, dann die wichtigsten Punkte als Stichpunkte).{focus_line} "
        f"Stütze dich nur auf den Text, erfinde nichts.\n\n=== PDF ({n} Seiten) ===\n{text}"
    )
    return _ollama_chat([{"role": "user", "content": prompt}], timeout=360.0, num_ctx=32768)


@mcp.tool()
def pdf_translate(pdf_path: str, target_lang: str = "Deutsch", max_pages: int = 10) -> str:
    """Übersetzt den Text einer PDF in eine Zielsprache (lokales Modell, ohne Cloud).
    Für: fremdsprachige Dokumente/Paper lesbar machen.
    `pdf_path` = Pfad zur PDF, `target_lang` = Zielsprache (default Deutsch),
    `max_pages` = wie viele Seiten (Übersetzung ist token-intensiv, klein halten)."""
    text, n, err = _extract(pdf_path, max(1, min(40, max_pages)))
    if err:
        return f"[Fehler: {err}]"
    if len(text) > 16000:
        text = text[:16000] + "\n…[gekürzt — für längere PDFs max_pages erhöhen schrittweise]"
    prompt = (
        f"Übersetze den folgenden PDF-Text vollständig und originalgetreu nach "
        f"{target_lang}. Behalte die Absatzstruktur bei; übersetze keine Eigennamen/"
        f"Formeln unnötig.\n\n=== TEXT ({n} Seiten) ===\n{text}"
    )
    return _ollama_chat([{"role": "user", "content": prompt}], timeout=420.0, num_ctx=32768)


if __name__ == "__main__":
    mcp.run()
