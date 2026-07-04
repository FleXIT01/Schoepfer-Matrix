"""assistant-mcp — Ein-Schritt-Pipeline: recherchieren -> PDF -> zustellen.

Warum: Das lokale Hirn (gpt-oss-32k) ueberlaeuft, wenn es Recherche + PDF + Versand
SELBST als mehrere Tool-Schritte verkettet (grosse Recherchetexte fluten den Kontext
-> "Auto-compaction could not recover"). Dieses Tool macht die GANZE Kette INTERN in
einem Prozess und gibt nur eine kurze Statuszeile zurueck -> minimaler Modell-Kontext,
kein Ueberlauf, kein flakiges Selbst-Orchestrieren.

Tool:
  - research_pdf_send(topic, email_to="", title="")
      recherchiert `topic` im Web, baut ein PDF und stellt es zu:
      * email_to gesetzt UND E-Mail eingerichtet -> per E-Mail (mit PDF-Anhang)
      * sonst -> per Telegram in den Chat des Besitzers
      Gibt eine kurze Erfolgs-/Fehlermeldung zurueck (kein langer Text).

Start (stdio):  python server.py
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import smtplib
import ssl
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

# bot1 web_search (DuckDuckGo + bs4) wiederverwenden.
_BOT1 = Path(__file__).resolve().parents[2] / "bot1"
if str(_BOT1) not in sys.path:
    sys.path.insert(0, str(_BOT1))

from mcp.server.fastmcp import FastMCP

try:
    from generator.agent.tools.impl.web_search import web_search as _web_search
except Exception as _e:  # noqa: BLE001
    _web_search = None
    _IMPORT_ERR = str(_e)

mcp = FastMCP("assistant-mcp")

# httpx/urllib3 loggen jeden Request (INFO) — ueber MCP-stdio nur Laerm.
for _n in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(_n).setLevel(logging.WARNING)

_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_MODEL = os.environ.get("ASSISTANT_MODEL", "gpt-oss-32k")
# Wikimedia verlangt einen policy-konformen User-Agent MIT Kontakt, sonst 403.
_UA = os.environ.get(
    "RESEARCH_UA",
    "SchoepferMatrix/1.0 (persoenlicher Recherche-Bot; mailto:starwars.felix@outlook.com)")
_PDF_OUT = os.environ.get("PDF_OUT_DIR", "n:/allinall/openclaw-workspace/output")
_RENDERER = str(Path(__file__).resolve().parents[1] / "pdf_mcp" / "render_pdf.py")
_MAIL_CFG = Path(os.environ.get(
    "MAIL_ACCOUNT_FILE",
    str(Path(__file__).resolve().parents[1] / "mail_mcp" / "mail_account.json")))


def _ollama_chat(prompt: str, *, timeout: float = 300.0, num_ctx: int = 16384) -> str:
    import httpx

    payload = {"model": _MODEL, "messages": [{"role": "user", "content": prompt}],
               "stream": False, "options": {"num_ctx": num_ctx}}
    try:
        r = httpx.post(f"{_OLLAMA}/api/chat", json=payload, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return f"[ollama-Fehler: {e}]"
    if r.status_code != 200:
        return f"[ollama HTTP {r.status_code}]"
    return ((r.json().get("message") or {}).get("content", "").strip()
            or "[leere Modellantwort]")


def _wikipedia(query: str, lang: str = "de") -> str:
    """Zuverlaessiger Unterbau: Wikipedia-API (kein Key). Liefert Intro-Extrakte
    der Top-Treffer + Quelle. DuckDuckGo ist oft rate-limited; Wikipedia nicht."""
    import httpx

    base = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        s = httpx.get(base, params={"action": "query", "list": "search",
                                    "srsearch": query, "srlimit": 3, "format": "json"},
                      timeout=20, headers={"User-Agent": _UA})
        hits = (s.json().get("query") or {}).get("search") or []
    except Exception:  # noqa: BLE001
        return ""
    out = []
    for h in hits[:2]:
        title = h.get("title", "")
        try:
            e = httpx.get(base, params={"action": "query", "prop": "extracts",
                                        "exintro": 1, "explaintext": 1, "redirects": 1,
                                        "titles": title, "format": "json"},
                          timeout=20, headers={"User-Agent": _UA})
            pages = (e.json().get("query") or {}).get("pages") or {}
        except Exception:  # noqa: BLE001
            continue
        for pg in pages.values():
            txt = (pg.get("extract") or "").strip()
            if txt:
                url = f"https://{lang}.wikipedia.org/wiki/" + title.replace(" ", "_")
                out.append(f"## Wikipedia: {title}\n{txt[:4000]}\n(Quelle: {url})")
    return "\n\n".join(out)


_STOP = {
    "alle", "daten", "ueber", "über", "den", "die", "der", "das", "dem", "des", "ein",
    "eine", "einen", "jetzige", "jetzigen", "jetzig", "aktuelle", "aktuellen", "aktuell",
    "heutige", "heutigen", "info", "infos", "information", "informationen", "wer", "was",
    "ist", "sind", "mir", "zum", "zur", "zu", "von", "vom", "und", "wichtigen", "wichtige",
    "details", "fakten", "thema", "suche", "such", "finde", "gib", "ueber",
}


def _keyword(topic: str) -> str:
    """Deterministische Stichwort-Extraktion (ohne Modell, das veraltetes Wissen hat):
    Fuellwoerter raus -> Kernbegriff fuer die Wikipedia-Suche."""
    import re

    words = [w for w in re.findall(r"[\wÄÖÜäöüß\-]+", topic) if w.lower() not in _STOP]
    return " ".join(words) if words else topic


def _research(topic: str) -> str:
    """Recherche -> deutscher Markdown-Bericht mit Quellen. DuckDuckGo (best effort)
    PLUS Wikipedia-API als zuverlaessiger Unterbau."""
    chunks = []
    # 1) DuckDuckGo (liefert oft nichts -> dann ignorieren)
    if _web_search is not None:
        for q in (topic, f"{topic} 2026"):
            try:
                r = _web_search(q, max_results=4, fetch_top=True)
                if r and "Keine Web-Ergebnisse" not in r and not r.startswith("["):
                    chunks.append(f"### Web-Suche: {q}\n{r}")
            except Exception:  # noqa: BLE001
                pass
    # 2) Wikipedia (zuverlaessig). Verbose Naturalsprache trifft die falschen Artikel,
    #    daher Fuellwoerter raus (DETERMINISTISCH, nicht per Modell — das Modell kennt
    #    aktuelle Amtstraeger nicht und wuerde veraltete/englische Begriffe liefern).
    kw = _keyword(topic)
    wiki = ""
    for q in (kw, topic):
        if q:
            wiki = _wikipedia(q)
            if wiki:
                break
    if wiki:
        chunks.append(wiki)
    corpus = "\n\n".join(chunks).strip() or f"[Keine Quellen zu '{topic}' gefunden.]"
    if len(corpus) > 14000:
        corpus = corpus[:14000] + "\n…[gekuerzt]"
    report = _ollama_chat(
        "Erstelle aus den folgenden Quellen einen strukturierten deutschen Bericht zum "
        f"Thema \"{topic}\". WICHTIG: Stütze dich AUSSCHLIESSLICH auf die Quellen, NICHT "
        "auf dein eigenes (möglicherweise veraltetes) Vorwissen. Achte auf Aktualität: "
        "Ist eine Person laut Quelle verstorben oder nicht mehr im Amt, ist sie NICHT der "
        "aktuelle Amtsträger — nenne den, der laut Quellen DERZEIT amtiert. "
        "Nutze Markdown ('# Titel', '## Abschnitt', '- Punkte'); Gliederung: Kurzfazit, "
        "wichtigste Fakten, dann '## Quellen' mit den URLs. Erfinde nichts.\n\n"
        f"=== QUELLEN ===\n{corpus}", timeout=360.0, num_ctx=32768)
    if report.startswith("["):  # ollama-Fehler -> wenigstens die Rohtreffer ins PDF
        return f"# {topic}\n\n## Rohe Suchergebnisse\n{corpus}"
    return report


def _make_pdf(title: str, content: str) -> tuple[str, str]:
    """Rendert PDF im Subprozess (isoliert). Liefert (pfad, fehler)."""
    import re
    safe = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "_")[:60] or "bericht"
    out = str(Path(_PDF_OUT) / (safe + ".pdf"))
    payload = {"title": title, "content": content, "out": out}
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(payload, tf)
        tf.close()
        proc = subprocess.run([sys.executable, _RENDERER, tf.name],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        return "", f"PDF-Subprozess: {e}"
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass
    res = {}
    for ln in reversed((proc.stdout or "").strip().splitlines()):
        try:
            res = json.loads(ln); break
        except Exception:  # noqa: BLE001
            continue
    if proc.returncode != 0 or "pages" not in res:
        return "", res.get("error", "unbekannt")
    return out, ""


def _mailcfg() -> dict:
    c = {"host": os.environ.get("SMTP_HOST", "smtp-mail.outlook.com"),
         "port": int(os.environ.get("SMTP_PORT", "587") or "587"),
         "starttls": os.environ.get("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no"),
         "user": os.environ.get("SMTP_USER", ""), "password": os.environ.get("SMTP_PASS", ""),
         "from": os.environ.get("SMTP_FROM", "")}
    if _MAIL_CFG.exists():
        try:
            d = json.loads(_MAIL_CFG.read_text(encoding="utf-8"))
            for k in ("host", "port", "starttls", "user", "password", "from"):
                if d.get(k) not in (None, ""):
                    c[k] = d[k]
        except Exception:  # noqa: BLE001
            pass
    frm = (c["from"] or "").strip()
    c["from"] = frm if "@" in frm else c["user"]
    c["port"] = int(c["port"])
    return c


def _send_email(to: str, subject: str, body: str, attach: str) -> str:
    cfg = _mailcfg()
    if not cfg["user"] or not cfg["password"]:
        return "NICHT_KONFIGURIERT"
    msg = EmailMessage()
    msg["From"] = cfg["from"]; msg["To"] = to; msg["Subject"] = subject
    msg.set_content(body)
    p = Path(attach)
    ctype, _ = mimetypes.guess_type(str(p))
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
    ctx = ssl.create_default_context()
    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=60, context=ctx) as s:
                s.login(cfg["user"], cfg["password"]); s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=60) as s:
                s.ehlo()
                if cfg["starttls"]:
                    s.starttls(context=ctx); s.ehlo()
                s.login(cfg["user"], cfg["password"]); s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        return f"FEHLER: {e}"
    return "OK"


def _send_telegram(path: str, caption: str) -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")
    if not token or not chat:
        return "NICHT_KONFIGURIERT"
    import httpx

    try:
        with open(path, "rb") as fh:
            r = httpx.post(f"https://api.telegram.org/bot{token}/sendDocument",
                           data={"chat_id": chat, "caption": caption[:1024]},
                           files={"document": (Path(path).name, fh)}, timeout=120)
    except Exception as e:  # noqa: BLE001
        return f"FEHLER: {e}"
    return "OK" if (r.status_code == 200 and (r.json() or {}).get("ok")) else f"FEHLER: HTTP {r.status_code}"


@mcp.tool()
def research_pdf_send(topic: str, email_to: str = "", title: str = "") -> str:
    """RECHERCHIEREN -> PDF -> ZUSTELLEN in EINEM Schritt (genau für Anfragen wie
    'suche Infos über X, fasse als PDF zusammen und schick es mir [per Mail an ...]').
    Macht die ganze Kette intern (kein Kontext-Ueberlauf). `topic` = Thema/Frage,
    `email_to` = Ziel-E-Mail (leer = per Telegram schicken), `title` = optionaler
    PDF-Titel. Liefert eine kurze Statuszeile (Pfad + wohin zugestellt)."""
    if not (topic or "").strip():
        return "[Fehler: kein Thema angegeben.]"
    ttl = (title or topic).strip()[:120]
    report = _research(topic)
    pdf_path, err = _make_pdf(ttl, report)
    if err:
        return f"[Fehler beim PDF-Erstellen: {err}]"

    # Zustellung: E-Mail (falls Adresse + eingerichtet) sonst Telegram.
    if email_to.strip():
        res = _send_email(email_to.strip(), f"Bericht: {ttl}",
                          f"Anbei der Bericht zu '{ttl}' (automatisch erstellt).", pdf_path)
        if res == "OK":
            return f"OK: PDF '{Path(pdf_path).name}' erstellt und per E-Mail an {email_to.strip()} gesendet."
        # Fallback Telegram
        tg = _send_telegram(pdf_path, f"Bericht: {ttl} (E-Mail ging nicht: {res})")
        if res == "NICHT_KONFIGURIERT":
            why = ("E-Mail ist nicht eingerichtet. Bitte einmal mailcfg.cmd ausführen "
                   "(Gmail + App-Passwort — Outlook ist von Microsoft für SMTP gesperrt).")
        else:
            why = f"E-Mail-Versand schlug fehl: {res}"
        if tg == "OK":
            return (f"PDF '{Path(pdf_path).name}' erstellt. {why} "
                    f"Ich habe es dir STATTDESSEN per Telegram geschickt.")
        return f"PDF erstellt ({pdf_path}). {why} Telegram-Versand auch fehlgeschlagen: {tg}"

    tg = _send_telegram(pdf_path, f"Bericht: {ttl}")
    if tg == "OK":
        return f"OK: PDF '{Path(pdf_path).name}' erstellt und per Telegram geschickt."
    if tg == "NICHT_KONFIGURIERT":
        return f"PDF erstellt: {pdf_path} (Telegram nicht eingerichtet — Datei liegt im output-Ordner)."
    return f"PDF erstellt: {pdf_path}, aber Telegram-Versand fehlgeschlagen: {tg}"


@mcp.tool()
def download_file(url: str, dest_dir: str, filename: str = "") -> str:
    """Lädt eine Datei (ISO, ZIP, PDF, Bild, …) von einer URL herunter und speichert
    sie im angegebenen Verzeichnis. `url` = Download-URL, `dest_dir` = Zielordner
    (wird erstellt falls nötig), `filename` = optionaler Dateiname (sonst aus URL).
    Gibt Pfad und Größe zurück oder Fehlermeldung."""
    import httpx
    import re
    from urllib.parse import urlparse, unquote

    if not url or not dest_dir:
        return "[Fehler: url und dest_dir sind Pflicht.]"

    dest = Path(dest_dir)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return f"[Fehler: Verzeichnis erstellen: {e}]"

    # Dateiname aus URL ableiten falls nicht angegeben
    if not filename:
        parsed = urlparse(url)
        filename = unquote(parsed.path.split("/")[-1]) or "download"
        filename = re.sub(r'[<>:"|?*]', '_', filename)  # Windows-safe

    out_path = dest / filename
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=600.0,
                          headers={"User-Agent": _UA}) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
    except httpx.HTTPStatusError as e:
        return f"[Fehler: HTTP {e.response.status_code} bei {url}]"
    except Exception as e:
        return f"[Fehler: Download fehlgeschlagen: {e}]"

    size_mb = out_path.stat().st_size / (1024 * 1024)
    return f"OK: '{out_path}' heruntergeladen ({size_mb:.1f} MB)."


@mcp.tool()
def run_command(command: str, workdir: str = "") -> str:
    """Führt einen Shell-Befehl (PowerShell/CMD) lokal aus und gibt stdout+stderr
    zurück (max 8000 Zeichen). `command` = der Befehl, `workdir` = optionales
    Arbeitsverzeichnis. Timeout: 120s. VORSICHT: Nur für sichere Befehle nutzen."""
    import subprocess as sp

    cwd = workdir.strip() if workdir else None
    if cwd and not Path(cwd).is_dir():
        return f"[Fehler: Verzeichnis '{cwd}' existiert nicht.]"
    try:
        result = sp.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=120, cwd=cwd,
        )
        out = (result.stdout or "") + (result.stderr or "")
        out = out.strip()
        if len(out) > 8000:
            out = out[:8000] + "\n…[gekürzt]"
        code = result.returncode
        return f"[ExitCode={code}]\n{out}" if out else f"[ExitCode={code}, keine Ausgabe]"
    except sp.TimeoutExpired:
        return "[Fehler: Zeitüberschreitung (120s).]"
    except Exception as e:
        return f"[Fehler: {e}]"


@mcp.tool()
def backup_now() -> str:
    """Startet SOFORT ein komplettes Schöpfer-Matrix-Backup (state, mcp-servers,
    Skripte, WeKnora-Docker-Volumes) nach I:\\backup\\matrix. Dauert 1-2 Minuten.
    Trigger: "mach ein Backup", "/backup", "sichere alles", "Backup jetzt".
    Gibt Erfolg/Fehler + Backup-Pfad zurück."""
    import re as _re
    import subprocess as sp

    try:
        result = sp.run(
            ["cmd", "/c", r"n:\allinall\backup.cmd"],
            capture_output=True, text=True, timeout=600,
            stdin=sp.DEVNULL,  # MCP-stdio-Gotcha: nie das stdio-Protokoll erben
        )
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        m = _re.search(r"I:\\backup\\matrix\\\d{4}-\d{2}-\d{2}_\d{6}", out)
        target = m.group(0) if m else "I:\\backup\\matrix"
        if "ERFOLGREICH" in out and result.returncode == 0:
            return f"[OK] Backup erfolgreich: {target} (state + mcp-servers + Skripte + Docker-Volumes)."
        tail = out[-600:] if out else "keine Ausgabe"
        return f"[FEHLER] Backup fehlgeschlagen (ExitCode={result.returncode}). Ende der Ausgabe:\n{tail}"
    except sp.TimeoutExpired:
        return "[FEHLER] Backup-Zeitüberschreitung (>10 min) — backup.log prüfen."
    except Exception as e:
        return f"[FEHLER] Backup-Start fehlgeschlagen: {e}"


if __name__ == "__main__":
    mcp.run()

