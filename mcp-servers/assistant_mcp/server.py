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
def _resolve_shell(shell: str) -> tuple[str, str]:
    """Gibt (kind, exe) zurueck; kind in {'ps','cmd'}.
    'auto'/'pwsh'/'powershell' -> PowerShell (pwsh 7 bevorzugt, sonst 5.1),
    'cmd' -> cmd.exe. So laeuft es unabhaengig von der installierten Version."""
    import shutil
    s = (shell or "auto").lower().strip()
    if s == "cmd":
        return "cmd", (shutil.which("cmd") or "cmd")
    if s == "powershell":  # explizit Windows PowerShell 5.1 erzwingen
        return "ps", (shutil.which("powershell") or "powershell")
    # auto/pwsh: PowerShell 7 (pwsh) bevorzugen, sonst 5.1
    return "ps", (shutil.which("pwsh") or shutil.which("powershell") or "powershell")


def _decode_bytes(b: bytes) -> str:
    """Robuste Dekodierung von Shell-Ausgabe: UTF-16 (PS-5.1-Dateiredirect schreibt
    so!), UTF-8, sonst OEM-Codepage cp850 (deutsche Konsole/native Tools wie ping)."""
    if not b:
        return ""
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", errors="replace")
    if b[:3] == b"\xef\xbb\xbf":
        return b.decode("utf-8-sig", errors="replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp850", errors="replace")


def _needs_elevation(text: str) -> bool:
    t = text.lower()
    return any(n in t for n in (
        "access is denied", "zugriff verweigert", "zugriff wurde verweigert",
        "der zugriff auf den pfad", "requires elevation", "erfordert erhöhte",
        "unauthorizedaccess", "permission denied",
        "run as administrator", "als administrator", "ausreichende berechtigung"))


def _run_elevated(kind: str, exe: str, command: str, cwd: str | None, timeout: int) -> str:
    """Fuehrt `command` mit Adminrechten aus (einmalige UAC-Bestaetigung) und faengt
    die Ausgabe ueber eine Temp-Datei ab. Start-Process -Verb RunAs kann NICHT direkt
    umgeleitet werden (UseShellExecute), darum: Befehl -> Skriptdatei, der ERHOEHTE
    Prozess leitet selbst in die Datei um, wir lesen sie danach zurueck."""
    import subprocess as sp
    import tempfile
    import uuid

    d = Path(tempfile.gettempdir())
    tag = uuid.uuid4().hex[:8]
    out_file = d / f"matrix_elev_{tag}.out"
    script = d / (f"matrix_elev_{tag}.bat" if kind == "cmd" else f"matrix_elev_{tag}.ps1")
    launcher = d / f"matrix_elev_{tag}_launch.ps1"
    try:
        if kind == "cmd":
            script.write_text(
                "@echo off\r\n" + (f'cd /d "{cwd}"\r\n' if cwd else "") + command + "\r\n",
                encoding="utf-8")
            arglist = f"@('/d','/c','\"{script}\" > \"{out_file}\" 2>&1')"
        else:
            script.write_text(
                (f"Set-Location -LiteralPath '{cwd}'\r\n" if cwd else "") + command + "\r\n",
                encoding="utf-8-sig")  # BOM -> auch PS 5.1 liest die Datei als UTF-8
            arglist = (f"@('-NoProfile','-ExecutionPolicy','Bypass','-Command',"
                       f"\"& '{script}' *> '{out_file}'\")")
        launcher.write_text(
            "$ErrorActionPreference='Stop'\r\n"
            "try {\r\n"
            f"  $p = Start-Process -FilePath \"{exe}\" -ArgumentList {arglist} "
            "-Verb RunAs -Wait -PassThru -WindowStyle Hidden\r\n"
            "  exit $p.ExitCode\r\n"
            "} catch {\r\n"
            f"  [IO.File]::WriteAllText('{out_file}', 'ELEVATION_ABGELEHNT: ' + $_.Exception.Message)\r\n"
            "  exit 1223\r\n"
            "}\r\n", encoding="utf-8")
        r = sp.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(launcher)], capture_output=True, timeout=timeout)
        code = r.returncode
        out = _decode_bytes(out_file.read_bytes()).strip() if out_file.exists() else ""
        if code == 1223 or out.startswith("ELEVATION_ABGELEHNT"):
            return "[Fehler: Elevation abgelehnt (UAC verneint/abgebrochen).]"
        if len(out) > 8000:
            out = out[:8000] + "\n…[gekuerzt]"
        return f"[ExitCode={code}] via {Path(exe).stem} (elevated)\n{out or 'keine Ausgabe'}"
    except sp.TimeoutExpired:
        return f"[Fehler: Zeitueberschreitung ({timeout}s) — UAC evtl. nicht bestaetigt.]"
    except Exception as e:
        return f"[Fehler (elevated): {e}]"
    finally:
        for f in (script, launcher, out_file):
            try:
                f.unlink()
            except Exception:
                pass


def _run_background(kind: str, command: str, cwd: str | None,
                    elevated: bool, notify: bool) -> str:
    """Startet `command` DETACHED (kein Warten) und kehrt sofort zurueck — fuer lange
    Laeufer (sfc, dism, chkdsk, Backups), die den 60-s-MCP-Timeout sprengen wuerden.
    Ausgabe geht in eine Logdatei; ist notify=True, schickt der Hintergrundprozess das
    Ergebnis selbst per Telegram, wenn er fertig ist (autonom, ohne dass der Turn wartet).
    elevated=True -> einmalige UAC-Bestaetigung, danach laeuft es erhoeht weiter."""
    import subprocess as sp
    import tempfile
    import uuid

    root = Path(__file__).resolve().parents[2]
    logdir = root / "openclaw-workspace" / "output"
    try:
        logdir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logdir = Path(tempfile.gettempdir())
    d = Path(tempfile.gettempdir())
    tag = uuid.uuid4().hex[:8]
    log = logdir / f"cmd_{tag}.log"
    wrapper = d / f"matrix_bg_{tag}.ps1"

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "") if notify else ""
    chat = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip() if notify else ""

    # Kindskript mit dem eigentlichen Befehl (bat fuer cmd, ps1 sonst)
    if kind == "cmd":
        child = d / f"matrix_bg_{tag}.bat"
        child.write_text("@echo off\r\n" + (f'cd /d "{cwd}"\r\n' if cwd else "")
                         + command + "\r\n", encoding="utf-8")
        invoke = f"& cmd.exe /d /c '{child}'"
    else:
        child = d / f"matrix_bg_{tag}_cmd.ps1"
        child.write_text((f"Set-Location -LiteralPath '{cwd}'\r\n" if cwd else "")
                         + command + "\r\n", encoding="utf-8-sig")
        invoke = f"& '{child}'"

    # Telegram-Meldung am Ende (PowerShell/Invoke-RestMethod nutzt Windows-Cert-Store
    # -> Avast-CA bekannt, anders als Python ohne truststore)
    notify_block = ""
    if token and chat:
        notify_block = (
            "try {\r\n"
            "  $tail = ''\r\n"
            "  if (Test-Path -LiteralPath $log) { $tail = (Get-Content -LiteralPath $log -Tail 25) -join \"`n\" }\r\n"
            "  if ($tail.Length -gt 3000) { $tail = '…' + $tail.Substring($tail.Length-3000) }\r\n"
            f"  $b = @{{ chat_id='{chat}'; text=(\"✅ Hintergrund-Befehl fertig (ExitCode \" + $code + \"):`n`n\" + $tail) }} | ConvertTo-Json -Compress\r\n"
            f"  Invoke-RestMethod -Uri 'https://api.telegram.org/bot{token}/sendMessage' -Method Post -Body $b -ContentType 'application/json; charset=utf-8' -TimeoutSec 25 | Out-Null\r\n"
            "} catch {}\r\n")

    wrapper.write_text(
        "$ErrorActionPreference='Continue'\r\n"
        f"$log = '{log}'\r\n"
        f"{invoke} *> $log\r\n"
        "$code = $LASTEXITCODE\r\n"
        + notify_block +
        f"Remove-Item -LiteralPath '{child}' -Force -ErrorAction SilentlyContinue\r\n"
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\r\n",
        encoding="utf-8")

    ps_args = ("'-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden',"
               f"'-File','{wrapper}'")
    verb = " -Verb RunAs" if elevated else ""
    launch = (f"$ErrorActionPreference='Stop'; try {{ Start-Process -FilePath 'powershell' "
              f"-ArgumentList {ps_args} -WindowStyle Hidden{verb} | Out-Null; exit 0 }} "
              "catch { exit 1223 }")
    try:
        r = sp.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", launch],
                   capture_output=True, timeout=90)
    except sp.TimeoutExpired:
        return "[Fehler: Start abgebrochen — UAC evtl. nicht bestaetigt (90s).]"
    except Exception as e:
        return f"[Fehler (background): {e}]"
    if r.returncode == 1223:
        return "[Fehler: Elevation abgelehnt (UAC verneint/abgebrochen).]"

    short = (command.strip().splitlines() or [""])[0][:70]
    tail = ("\nErgebnis kommt automatisch per Telegram, wenn fertig."
            if (token and chat) else
            f"\nFortschritt pruefen: Get-Content '{log}' -Tail 30")
    return (f"[Hintergrund gestartet{' · elevated' if elevated else ''}] {short}\n"
            f"Log: {log}{tail}")


@mcp.tool()
def run_command(command: str, workdir: str = "", shell: str = "auto",
                elevated: bool = False, timeout: int = 120,
                background: bool = False, notify: bool = True) -> str:
    """Fuehrt einen Shell-Befehl lokal aus und gibt stdout+stderr zurueck (max 20000 Z.).
    Laeuft UNABHAENGIG von der PowerShell-Version und wahlweise mit Adminrechten.

    `command`  = der Befehl (ein- oder mehrzeilig).
    `workdir`  = optionales Arbeitsverzeichnis.
    `shell`    = 'auto' (PowerShell; nimmt pwsh 7 wenn vorhanden, sonst 5.1) |
                 'powershell' (erzwingt Windows PowerShell 5.1) | 'pwsh' (PS 7) |
                 'cmd' (klassische Eingabeaufforderung, fuer .bat/dir/copy/net use etc.).
    `elevated` = True -> mit Adminrechten (einmalige UAC-Bestaetigung AM PC durch den
                 Nutzer — per Fernsteuerung/Telegram kann niemand klicken!). Fuer
                 Dienste, geschuetzte Pfade, Netzwerkkonfig, Treiber, sc/netsh/reg.
    `timeout`  = Sekunden (5..600, Standard 120) — nur fuer den NORMALEN (wartenden) Lauf.
    `background` = True -> Befehl DETACHED starten, sofort zurueckkehren. PFLICHT fuer
                 lange Laeufer (sfc /scannow, dism, chkdsk, grosse Kopien) — die sprengen
                 sonst den 60-s-MCP-Timeout ('Request timed out'). Ausgabe geht in ein Log;
                 bei notify=True schickt der Prozess das Ergebnis selbst per Telegram, wenn
                 er fertig ist. Mit elevated kombinierbar (eine UAC-Bestaetigung).
    `notify`   = (nur bei background) True -> Ergebnis am Ende per Telegram melden.

    NETZWERK-SCANS NICHT hier: dafuer `net_scan` nutzen (schnell, ohne Timeout).
    Bei 'Zugriff verweigert' -> denselben Befehl mit elevated=True erneut aufrufen.
    'sfc /scannow' & Co. IMMER mit background=True (+elevated=True) starten.
    VORSICHT: Nur fuer sichere Befehle; irreversibles vorher bestaetigen lassen."""
    import subprocess as sp

    cwd = workdir.strip() if workdir else None
    if cwd and not Path(cwd).is_dir():
        return f"[Fehler: Verzeichnis '{cwd}' existiert nicht.]"
    try:
        timeout = max(5, min(int(timeout or 120), 600))
    except (TypeError, ValueError):
        timeout = 120
    kind, exe = _resolve_shell(shell)

    if background:
        return _run_background(kind, command, cwd, elevated, notify)
    if elevated:
        return _run_elevated(kind, exe, command, cwd, timeout)

    if kind == "cmd":
        argv = [exe, "/d", "/c", command]
    else:
        argv = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    try:
        result = sp.run(argv, capture_output=True, timeout=timeout, cwd=cwd)
    except sp.TimeoutExpired:
        return f"[Fehler: Zeitueberschreitung ({timeout}s).]"
    except FileNotFoundError:
        return f"[Fehler: Shell '{exe}' nicht gefunden.]"
    except Exception as e:
        return f"[Fehler: {e}]"

    out = (_decode_bytes(result.stdout) + _decode_bytes(result.stderr)).strip()
    code = result.returncode
    hint = ""
    if code != 0 and _needs_elevation(out):
        hint = ("\n[Hinweis: Adminrechte fehlen — denselben Befehl mit elevated=True "
                "erneut aufrufen (einmalige UAC-Bestaetigung).]")
    if len(out) > 20000:
        out = out[:20000] + "\n…[gekuerzt]"
    tail = f" via {Path(exe).stem}"
    return f"[ExitCode={code}]{tail}\n{out}{hint}" if out else \
           f"[ExitCode={code}]{tail}, keine Ausgabe{hint}"


_STD_PORTS = [21, 22, 23, 25, 53, 80, 110, 139, 143, 443, 445, 3389, 8080]


def _local_subnet() -> tuple[str, str]:
    """Ermittelt die primaere IPv4 und das /24-Praefix ('192.168.1') des eigenen PCs."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # kein Traffic — nur Routing-Entscheidung
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip, ip.rsplit(".", 1)[0]


def _ping(host: str, timeout_ms: int = 500) -> bool:
    """Ein ICMP-Ping via Windows-ping (kein Admin noetig). Liest BYTES —
    deutsches ping gibt OEM-Codepage aus (0x81 u.a.), text=True wuerde unter
    PYTHONUTF8 im Reader-Thread crashen. 'TTL='/'ttl=' im Rohbyte-Puffer =
    echte Antwort (returncode allein ist unter Windows unzuverlaessig)."""
    import subprocess as sp
    try:
        r = sp.run(["ping", "-n", "1", "-w", str(timeout_ms), host],
                   capture_output=True, timeout=timeout_ms / 1000 + 2)
        return b"ttl=" in (r.stdout or b"").lower()
    except Exception:
        return False


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


@mcp.tool()
def net_scan(target: str = "", ports: str = "", max_hosts: int = 254) -> str:
    """Schneller Netzwerk-Scan (Ping-Sweep + Port-Scan) — nebenlaeufig, ohne nmap,
    ohne Admin-Rechte, PowerShell-unabhaengig. NUTZE DIESES TOOL fuer jede Anfrage
    'mach einen Ping-/Port-Scan', 'scanne mein Netzwerk', 'welche Geraete/offenen Ports'.
    Schreibe NICHT selbst PowerShell-Scan-Skripte (Test-Connection/Test-NetConnection
    sind zu langsam und laufen in den Timeout).

    `target`: leer = EIGENES lokales /24-Subnetz (Standard); eine IP/Host (z.B.
              '192.168.1.10' oder 'meinserver.local') = nur dieses Ziel; ein Praefix
              wie '10.0.0' = dieses /24.
    `ports` : leer = Standard-Ports (21,22,23,25,53,80,110,139,143,443,445,3389,8080);
              sonst kommagetrennt (z.B. '80,443,8080') oder Bereich '1-1024'.
    `max_hosts`: Sicherheitsdeckel fuer die Host-Zahl beim Subnetz-Scan.

    Gibt eine kompakte Zusammenfassung (erreichbare Hosts + offene Ports je Host)
    zurueck — direkt fuer eine PDF/Antwort verwendbar."""
    import concurrent.futures as cf
    import ipaddress

    # ── Ports parsen ──────────────────────────────────────────────────────────
    plist: list[int] = []
    if ports.strip():
        for part in ports.replace(" ", "").split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                if a.isdigit() and b.isdigit():
                    plist.extend(range(int(a), min(int(b), 65535) + 1))
            elif part.isdigit():
                plist.append(int(part))
        plist = sorted(set(p for p in plist if 0 < p <= 65535))[:1024]
    if not plist:
        plist = list(_STD_PORTS)

    # ── Zielhosts bestimmen ───────────────────────────────────────────────────
    own_ip, own_pref = _local_subnet()
    t = target.strip()
    scope = ""
    if not t:
        prefix = own_pref
        hosts = [f"{prefix}.{i}" for i in range(1, 255)][:max_hosts]
        scope = f"eigenes Subnetz {prefix}.0/24 (eigene IP {own_ip})"
    else:
        # Einzelnes /24-Praefix wie '10.0.0'
        if t.count(".") == 2 and all(o.isdigit() for o in t.split(".")):
            hosts = [f"{t}.{i}" for i in range(1, 255)][:max_hosts]
            scope = f"Subnetz {t}.0/24"
        else:
            # Einzel-IP oder Hostname
            try:
                ipaddress.ip_address(t)
            except ValueError:
                pass  # Hostname ist ok
            hosts = [t]
            scope = f"Host {t}"

    # ── Ping-Sweep (nur bei mehr als einem Host; Einzelziel wird direkt gescannt) ─
    if len(hosts) > 1:
        with cf.ThreadPoolExecutor(max_workers=128) as ex:
            alive = [h for h, ok in zip(hosts, ex.map(_ping, hosts)) if ok]
    else:
        alive = hosts

    if not alive:
        return (f"[net_scan] {scope}: kein Host geantwortet (Ping). "
                f"Moeglich: Geraete blocken ICMP, oder falsches Subnetz. "
                f"Eigene IP ist {own_ip} — ggf. target='{own_pref}' explizit angeben.")

    # ── Port-Scan der erreichbaren Hosts (nebenlaeufig) ───────────────────────
    tasks = [(h, p) for h in alive for p in plist]
    open_map: dict[str, list[int]] = {h: [] for h in alive}
    with cf.ThreadPoolExecutor(max_workers=256) as ex:
        results = ex.map(lambda hp: (hp[0], hp[1], _port_open(hp[0], hp[1])), tasks)
        for h, p, is_open in results:
            if is_open:
                open_map[h].append(p)

    # ── Bericht ───────────────────────────────────────────────────────────────
    lines = [f"Netzwerk-Scan — {scope}",
             f"Erreichbare Hosts (Ping): {len(alive)} von {len(hosts)} geprueft",
             f"Gepruefte Ports: {', '.join(map(str, plist)) if len(plist) <= 20 else str(len(plist)) + ' Ports'}",
             ""]
    for h in sorted(alive, key=lambda x: [int(o) if o.isdigit() else o for o in x.split(".")]):
        op = open_map.get(h, [])
        lines.append(f"  {h:<16} offene Ports: {', '.join(map(str, op)) if op else 'keine'}")
    return "\n".join(lines)


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

