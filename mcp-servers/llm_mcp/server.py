"""llm-mcp — Modell-Routing als MCP-Server.

Das Hirn (gpt-oss:20b, zuverlässiges Tool-Calling) bleibt der Dirigent und ruft
je nach Aufgabe das passende lokale Spezialmodell als Tool auf:

  - code_generate   -> codestral        (starkes Code-Modell)
  - vision_describe -> qwen3-vl:32b      (multimodal, Bildverständnis)
  - reason_deep     -> gpt-oss:20b       (tiefes Reasoning, passt in 16 GB VRAM)
  - quick_answer    -> qwen2.5:7b        (schnell & günstig für Routine)
  - route_model     -> Empfehlung, welches Modell/Tool für eine Aufgabe passt

Cloud-Calls (cloud_reason, cloud_cheap, cloud_code) werden in SQLite protokolliert
(costs.db). Tagesbudget ist konfigurierbar (CLOUD_DAILY_LIMIT_EUR, Standard: 2 EUR).
Tool budget_status() zeigt aktuellen Verbrauch und Limit.

Start (stdio):  python server.py
"""
from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import run_capability, audit_log  # noqa: E402  (R1: Fähigkeits-Leiter)

mcp = FastMCP("llm-mcp")

_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
# Hauptmodell des Agenten — wird nach ComfyUI-Batch vorgeladen (ollama_reload_main)
_MAIN_MODEL = os.environ.get("OLLAMA_MAIN_MODEL", "gpt-oss-32k:latest")

# Cloud (OpenRouter) — nur genutzt, wenn ein Key gesetzt ist. Kostet Geld pro Aufruf.
_OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
_CLOUD_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
_CLOUD_CODE_MODEL = os.environ.get("OPENROUTER_CODE_MODEL", _CLOUD_MODEL)
# Günstige Cloud-Stufe (DeepSeek) — ~10-15x billiger als Claude, gut für Routine.
_CHEAP_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek/deepseek-v3.2")

# Tagesbudget für Cloud-Calls (in EUR). Harte Sperre, wenn überschritten.
_DAILY_LIMIT_EUR = float(os.environ.get("CLOUD_DAILY_LIMIT_EUR", "2.0"))
# Sub-Limits (Phase A): Stundenlimit + Alarm bei 50% Tagesbudget
_HOURLY_LIMIT_EUR = float(os.environ.get("CLOUD_HOURLY_LIMIT_EUR", "0.50"))
_ALERT_THRESHOLD = 0.50   # 50%-Alarm: Vermerk in Antwort, kein harter Block
_USD_TO_EUR = 0.92  # Annäherung; kein Live-Kurs nötig

# Kosten je 1M Tokens (USD). Quelle: OpenRouter-Preisseite, Stand 2026-06.
_COST_PER_1M_USD: dict[str, dict[str, float]] = {
    "anthropic/claude-opus-4.8":   {"in": 15.0,   "out": 75.0},
    "anthropic/claude-opus-4-8":   {"in": 15.0,   "out": 75.0},
    "anthropic/claude-sonnet-4.6": {"in": 3.0,    "out": 15.0},
    "deepseek/deepseek-v3.2":      {"in": 0.27,   "out": 1.10},
    "deepseek/deepseek-r1":        {"in": 0.55,   "out": 2.19},
}

# Aufgabe -> (Modell, Begründung). Modelle, die lokal installiert sind.
_MODEL_MAP = {
    "code":      ("codestral:latest", "Spezialisiertes Code-Modell."),
    "vision":    ("qwen3-vl:32b",     "Multimodales VL-Modell für Bilder."),
    "reasoning": ("gpt-oss:20b",      "Starkes Reasoning, passt komplett in 16 GB VRAM."),
    "quick":     ("qwen2.5:7b",       "Klein & schnell für Routine/Klassifikation."),
}

# SQLite Kosten-Ledger
_DB_PATH = Path(__file__).parent / "costs.db"

# F2 (V3): Empirisches Routing — jede Ausführung wird je (Aufgabentyp, Modell)
# protokolliert; ab _ROUTING_MIN_RUNS Datenpunkten (D18) überschreibt die
# Empirie die Handregel. Kleiner Explorations-Anteil, sonst lernt man nie dazu.
_ROUTING_DB = Path(__file__).parent / "routing.db"
_ROUTING_MIN_RUNS = int(os.environ.get("ROUTING_MIN_RUNS", "20"))   # D18
_ROUTING_EXPLORE = 0.10  # 10% der Empfehlungen probieren bewusst eine Alternative


def _routing_init() -> None:
    with sqlite3.connect(_ROUTING_DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT NOT NULL,
                kind     TEXT NOT NULL,     -- code|vision|reasoning|quick|cloud_*
                model    TEXT NOT NULL,
                ok       INTEGER NOT NULL,  -- 1 = brauchbares Ergebnis
                latency  REAL NOT NULL,     -- Sekunden
                cost_usd REAL NOT NULL DEFAULT 0
            )
        """)
        con.commit()


def _routing_log(kind: str, model: str, ok: bool, latency: float,
                 cost_usd: float = 0.0) -> None:
    try:
        _routing_init()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(_ROUTING_DB) as con:
            con.execute(
                "INSERT INTO runs (ts, kind, model, ok, latency, cost_usd) VALUES (?,?,?,?,?,?)",
                (ts, kind, model, 1 if ok else 0, round(latency, 2), cost_usd))
            con.commit()
    except Exception:  # Logging darf nie den eigentlichen Call zerstören
        pass


def _timed_ollama(kind: str, model: str, messages: list[dict], **kw) -> str:
    """_ollama_chat mit F2-Routing-Protokollierung."""
    import time as _t
    t0 = _t.monotonic()
    result = _ollama_chat(model, messages, **kw)
    ok = not (isinstance(result, str) and result.lstrip().startswith("[Fehler"))
    _routing_log(kind, model, ok, _t.monotonic() - t0)
    return result


def _init_db() -> None:
    with sqlite3.connect(_DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS cloud_calls (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL,
                purpose   TEXT NOT NULL,
                model     TEXT NOT NULL,
                in_tok    INTEGER NOT NULL DEFAULT 0,
                out_tok   INTEGER NOT NULL DEFAULT 0,
                cost_usd  REAL NOT NULL DEFAULT 0,
                status    TEXT NOT NULL DEFAULT 'ok'
            )
        """)
        con.commit()


def _estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    """Geschätzte Kosten in USD für einen API-Call."""
    prices = _COST_PER_1M_USD.get(model, {"in": 5.0, "out": 15.0})
    return (in_tok * prices["in"] + out_tok * prices["out"]) / 1_000_000


def _log_call(purpose: str, model: str, in_tok: int, out_tok: int,
              cost_usd: float, status: str = "ok") -> None:
    _init_db()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(_DB_PATH) as con:
        con.execute(
            "INSERT INTO cloud_calls (ts, purpose, model, in_tok, out_tok, cost_usd, status) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, purpose, model, in_tok, out_tok, cost_usd, status),
        )
        con.commit()


def _daily_total_usd() -> float:
    """Heutiger Cloud-Verbrauch in USD."""
    _init_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(_DB_PATH) as con:
        row = con.execute(
            "SELECT SUM(cost_usd) FROM cloud_calls WHERE ts LIKE ? AND status='ok'",
            (f"{today}%",),
        ).fetchone()
    return float(row[0] or 0.0)


def _hourly_total_usd() -> float:
    """Cloud-Verbrauch der letzten 60 Minuten in USD."""
    _init_db()
    from datetime import timedelta
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(_DB_PATH) as con:
        row = con.execute(
            "SELECT SUM(cost_usd) FROM cloud_calls WHERE ts >= ? AND status='ok'",
            (hour_ago,),
        ).fetchone()
    return float(row[0] or 0.0)


def _check_budget(model: str) -> str | None:
    """None = Budget OK. String = Fehlermeldung (Limit ueberschritten).
    Prueft: hartes Tageslimit + hartes Stundenlimit."""
    spent_usd = _daily_total_usd()
    spent_eur = spent_usd * _USD_TO_EUR
    # Hartes Tageslimit
    if spent_eur >= _DAILY_LIMIT_EUR:
        return (f"[Budget-Limit erreicht: heute {spent_eur:.2f} € von {_DAILY_LIMIT_EUR:.2f} € "
                f"({spent_usd:.4f} USD). Cloud-Call fuer '{model}' abgelehnt. "
                f"Limit erhoehen: CLOUD_DAILY_LIMIT_EUR in openclaw.json env setzen.]")
    # Hartes Stundenlimit
    hourly_eur = _hourly_total_usd() * _USD_TO_EUR
    if hourly_eur >= _HOURLY_LIMIT_EUR:
        return (f"[Stunden-Limit erreicht: letzte Stunde {hourly_eur:.2f} € von "
                f"{_HOURLY_LIMIT_EUR:.2f} €. Cloud-Call fuer '{model}' pausiert. "
                f"Limit: CLOUD_HOURLY_LIMIT_EUR in openclaw.json env setzen.]")
    return None


def _budget_note() -> str:
    """Gibt eine 50%-Warnung zurueck wenn noetig, sonst leerer String."""
    spent_eur = _daily_total_usd() * _USD_TO_EUR
    if spent_eur >= _DAILY_LIMIT_EUR * _ALERT_THRESHOLD:
        pct = spent_eur / _DAILY_LIMIT_EUR * 100
        return (f"\n\n[Budget-Warnung: {spent_eur:.2f} € von {_DAILY_LIMIT_EUR:.2f} € "
                f"heute verbraucht ({pct:.0f}%)]")
    return ""


def _ollama_chat(model: str, messages: list[dict], *, timeout: float = 300.0,
                 num_ctx: int | None = None) -> str:
    """Ein nicht-gestreamter Chat-Call an die lokale Ollama-Instanz."""
    import httpx

    payload: dict = {"model": model, "messages": messages, "stream": False}
    if num_ctx:
        payload["options"] = {"num_ctx": num_ctx}
    try:
        r = httpx.post(f"{_OLLAMA}/api/chat", json=payload, timeout=timeout)
    except httpx.ConnectError:
        return f"[Fehler: Ollama nicht erreichbar unter {_OLLAMA}. Läuft die Ollama-App?]"
    except httpx.ReadTimeout:
        return (f"[Fehler: Zeitüberschreitung ({timeout:.0f}s) bei Modell '{model}'. "
                "Großes Modell lädt evtl. noch / läuft teilweise auf CPU.]")
    if r.status_code == 404:
        return (f"[Fehler: Modell '{model}' ist in Ollama nicht installiert. "
                f"Mit `ollama pull {model}` holen.]")
    if r.status_code != 200:
        return f"[Fehler: Ollama HTTP {r.status_code}: {r.text[:300]}]"
    data = r.json()
    content = (data.get("message") or {}).get("content", "").strip()
    return content or "[Fehler: Ollama lieferte leeren Inhalt.]"


def _openrouter_chat(model: str, messages: list[dict], *,
                     purpose: str = "cloud_call",
                     timeout: float = 180.0) -> str:
    """Ein Chat-Call an OpenRouter (Cloud). Braucht OPENROUTER_API_KEY.
    Protokolliert Token-Verbrauch und Kosten in costs.db."""
    import httpx

    if not _OPENROUTER_KEY:
        return ("[Fehler: kein OPENROUTER_API_KEY gesetzt — Cloud nicht verfügbar. "
                "Lokale Tools (reason_deep/code_generate) nutzen.]")

    # Tagesbudget prüfen
    budget_err = _check_budget(model)
    if budget_err:
        _log_call(purpose, model, 0, 0, 0.0, "blocked_budget")
        return budget_err

    headers = {
        "Authorization": f"Bearer {_OPENROUTER_KEY}",
        "HTTP-Referer": "https://schoepfer-matrix.local",
        "X-Title": "Schoepfer-Matrix",
    }
    payload = {"model": model, "messages": messages, "stream": False}
    import time as _t
    _t0 = _t.monotonic()
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       json=payload, headers=headers, timeout=timeout)
    except httpx.ConnectError:
        _log_call(purpose, model, 0, 0, 0.0, "connect_error")
        return "[Fehler: OpenRouter nicht erreichbar (Internet?).]"
    except httpx.ReadTimeout:
        _log_call(purpose, model, 0, 0, 0.0, "timeout")
        return f"[Fehler: Zeitüberschreitung ({timeout:.0f}s) bei Cloud-Modell '{model}'.]"
    if r.status_code == 401:
        _log_call(purpose, model, 0, 0, 0.0, "auth_error")
        return "[Fehler: OpenRouter-Key ungültig/abgelaufen (HTTP 401).]"
    if r.status_code == 402:
        _log_call(purpose, model, 0, 0, 0.0, "no_credits")
        return "[Fehler: OpenRouter-Guthaben aufgebraucht (HTTP 402). Credits aufladen.]"
    if r.status_code != 200:
        _log_call(purpose, model, 0, 0, 0.0, f"http_{r.status_code}")
        return f"[Fehler: OpenRouter HTTP {r.status_code}: {r.text[:300]}]"

    try:
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip() or "[Fehler: leere Cloud-Antwort.]"
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens") or 0)
        out_tok = int(usage.get("completion_tokens") or 0)
        cost_usd = _estimate_cost(model, in_tok, out_tok)
        _log_call(purpose, model, in_tok, out_tok, cost_usd, "ok")
        elapsed = _t.monotonic() - _t0
        _routing_log(purpose, model, True, elapsed, cost_usd)
        # V14: in den vereinheitlichten Pro-Schritt-Trace einspeisen (Engpass-Analyse)
        try:
            import sys as _sys
            from pathlib import Path as _P
            _sys.path.insert(0, str(_P(__file__).parent.parent))
            from tracelib import log_step as _trace_step
            _trace_step("llm_cloud", latency_ms=int(elapsed * 1000),
                        cost_usd=cost_usd, tokens=in_tok + out_tok,
                        detail=f"{purpose}:{model}")
        except Exception:  # noqa: BLE001 — Trace nie kritisch
            pass
        return content + _budget_note()
    except Exception as e:  # noqa: BLE001
        _log_call(purpose, model, 0, 0, 0.0, "parse_error")
        return f"[Fehler beim Lesen der Cloud-Antwort: {e}]"


@mcp.tool()
def code_generate(task: str, language: str = "python") -> str:
    """Generiert Quellcode mit dem spezialisierten Code-Modell (codestral).
    Für: Funktionen/Skripte/Klassen schreiben, Code erklären/refactoren.
    `task` = präzise Aufgabe, `language` = Programmiersprache (default python)."""
    messages = [
        {"role": "system", "content":
            f"You are an expert {language} programmer. Output clean, correct, "
            f"production-ready {language} code. Prefer code with brief comments; "
            "no lengthy prose."},
        {"role": "user", "content": task},
    ]
    return _timed_ollama("code", _MODEL_MAP["code"][0], messages, num_ctx=8192)


@mcp.tool()
def vision_describe(image_path: str, question: str = "Beschreibe dieses Bild genau.") -> str:
    """Analysiert ein lokales Bild mit dem multimodalen Modell (qwen3-vl).
    Für: Screenshots/Diagramme/Fotos verstehen, Text aus Bildern lesen.
    `image_path` = Pfad zu einer Bilddatei (png/jpg), `question` = was du wissen willst."""
    p = Path(image_path)
    if not p.exists():
        return f"[Fehler: Bilddatei nicht gefunden: {image_path}]"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception as e:  # noqa: BLE001
        return f"[Fehler beim Lesen des Bildes: {e}]"
    messages = [{"role": "user", "content": question, "images": [b64]}]
    return _timed_ollama("vision", _MODEL_MAP["vision"][0], messages, timeout=420.0)


@mcp.tool()
def reason_deep(prompt: str) -> str:
    """Tiefes Reasoning/Analyse mit dem starken Modell (gpt-oss:20b).
    Für: schwierige Schlussfolgerungen, Planung, Abwägungen, Synthese.
    `prompt` = die zu durchdenkende Frage/Aufgabe.
    R1-Fallback-Leiter: gpt-oss lokal -> cloud_cheap (DeepSeek) -> qwen2.5:7b.
    Fällt eine Stufe aus (OOM/Timeout/Verweigerung), übernimmt die nächste —
    die Antwort vermerkt dann den Abstieg."""
    messages = [
        {"role": "system", "content":
            "Du bist ein sorgfältiger Analyst. Denke Schritt für Schritt und "
            "liefere eine klare, begründete Antwort."},
        {"role": "user", "content": prompt},
    ]
    cloud_msgs = [
        {"role": "system", "content":
            "Du bist ein sorgfältiger Analyst. Antworte klar und begründet auf Deutsch."},
        {"role": "user", "content": prompt},
    ]
    ladder = [
        ("gpt-oss lokal",
         lambda: _timed_ollama("reasoning", _MODEL_MAP["reasoning"][0], messages, num_ctx=8192)),
        ("cloud_cheap (DeepSeek)",
         lambda: _openrouter_chat(_CHEAP_MODEL, cloud_msgs, purpose="reason_fallback")),
        ("qwen2.5:7b lokal",
         lambda: _timed_ollama("reasoning", _MODEL_MAP["quick"][0], messages)),
    ]
    return run_capability("reason", ladder)


@mcp.tool()
def quick_answer(prompt: str) -> str:
    """Schnelle Antwort/Klassifikation mit kleinem, flottem Modell (qwen2.5:7b).
    Für: kurze Fragen, Routing-Entscheidungen, Zusammenfassen, Klassifizieren.
    `prompt` = die kurze Aufgabe."""
    messages = [{"role": "user", "content": prompt}]
    return _timed_ollama("quick", _MODEL_MAP["quick"][0], messages, timeout=120.0)


@mcp.tool()
def cloud_reason(prompt: str) -> str:
    """STÄRKSTES Reasoning (Claude Opus über OpenRouter) — TEUERSTE Stufe, LETZTER Ausweg.
    NUR aufrufen, wenn die Aufgabe WIRKLICH SCHWER ist (mehrstufige Logik, knifflige
    Trade-offs, tiefe Analyse über viel Kontext) UND die lokalen Modelle (reason_deep)
    bzw. cloud_cheap (DeepSeek) nicht ausreichen. NIEMALS für einfache/mittlere Fragen —
    dafür lokal antworten. Jeder Aufruf kostet spürbar Geld und sendet Text in die Cloud.
    `prompt` = die wirklich anspruchsvolle Frage/Aufgabe."""
    messages = [
        {"role": "system", "content":
            "Du bist ein erstklassiger Analyst. Denke gründlich und liefere eine "
            "präzise, gut begründete Antwort auf Deutsch."},
        {"role": "user", "content": prompt},
    ]
    return _openrouter_chat(_CLOUD_MODEL, messages, purpose="cloud_reason")


@mcp.tool()
def cloud_cheap(prompt: str) -> str:
    """GÜNSTIGES Cloud-Modell (DeepSeek über OpenRouter) — ~10-15x billiger als Claude.
    Für: Cloud-Qualität bei begrenztem Budget, Routine-Reasoning, Zusammenfassen,
    längere Texte. Stärker als die lokalen Modelle, aber sehr günstig. Wenn es um
    maximale Qualität geht, stattdessen cloud_reason (Claude) nehmen.
    `prompt` = die Aufgabe/Frage."""
    messages = [
        {"role": "system", "content":
            "Du bist ein hilfreicher, präziser Assistent. Antworte klar auf Deutsch."},
        {"role": "user", "content": prompt},
    ]
    return _openrouter_chat(_CHEAP_MODEL, messages, purpose="cloud_cheap")


@mcp.tool()
def cloud_code(task: str, language: str = "python") -> str:
    """STARKE Cloud-Codegenerierung (Claude über OpenRouter). KOSTET Geld + Cloud.
    NUR aufrufen, wenn der Nutzer ausdrücklich starken/Cloud-Code wünscht ODER die
    Aufgabe wirklich komplex ist (Architektur, mehrteilige Module, kniffliges Refactoring).
    Standard für Code ist LOKAL (code_generate/codestral) — nicht für triviale Snippets
    oder normale Funktionen die Cloud nehmen. `task` = Aufgabe, `language` = Sprache."""
    messages = [
        {"role": "system", "content":
            f"You are a world-class {language} engineer. Output correct, clean, "
            f"production-ready {language} code with brief comments. No filler prose."},
        {"role": "user", "content": task},
    ]
    return _openrouter_chat(_CLOUD_CODE_MODEL, messages, purpose="cloud_code")


@mcp.tool()
def council(prompt: str, judge: str = "local") -> str:
    """Rat der Modelle: lokal (gpt-oss:20b) + cloud_cheap (DeepSeek) antworten UNABHAENGIG;
    ein Richter fasst zusammen und markiert Widersprueche EXPLIZIT als Liste.
    Killt Single-Model-Blindspots bei wichtigen Entscheidungen.
    Kosten: 1 DeepSeek-Call (Centbereich) + optionaler Richter-Cloud-Call.
    `prompt` = die Frage/Aufgabe.
    `judge`  = 'local' (gpt-oss, Default) | 'cloud' (Claude Opus, teurer, fuer kritische Entscheidungen).
    Trigger: 'wichtige Entscheidung', 'Zweitmeinung', 'sicher gehen', 'vergleiche Antworten'."""
    import concurrent.futures

    local_model = _MODEL_MAP["reasoning"][0]  # gpt-oss:20b

    local_msgs = [
        {"role": "system", "content":
            "Du bist ein sorgfaeltiger Analyst. Antworte praezise, direkt und auf Deutsch."},
        {"role": "user", "content": prompt},
    ]
    cloud_msgs = [
        {"role": "system", "content":
            "Du bist ein hilfreicher, praeziser Assistent. Antworte klar auf Deutsch."},
        {"role": "user", "content": prompt},
    ]

    # Budget-Check — faellt Budget-Limit: nur lokale Antwort
    if _check_budget(_CHEAP_MODEL):
        local_ans = _ollama_chat(local_model, local_msgs, num_ctx=8192)
        return f"[Council: nur Lokal, Cloud-Budget erschoepft]\n\n{local_ans}"

    # Parallel: lokal + Cloud
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_local = ex.submit(_ollama_chat, local_model, local_msgs, num_ctx=8192)
        fut_cloud = ex.submit(_openrouter_chat, _CHEAP_MODEL, cloud_msgs, purpose="council")
        local_ans = fut_local.result()
        cloud_ans = fut_cloud.result()

    # Richter-Pass
    judge_prompt = (
        f"FRAGE: {prompt}\n\n"
        f"ANTWORT A (Lokal/gpt-oss): {local_ans}\n\n"
        f"ANTWORT B (Cloud/DeepSeek): {cloud_ans}\n\n"
        "Erstelle eine knappe Synthese in drei Abschnitten:\n"
        "1. KONSENS: Worin sind sich beide einig?\n"
        "2. WIDERSPRUECHE: Was widerspricht sich? Jeden Widerspruch als Bullet-Point, konkret.\n"
        "3. EMPFEHLUNG: Welche Antwort/welcher Aspekt ist zuverlaessiger und warum?\n"
        "Kein Fuellttext, keine Einleitung."
    )
    judge_msgs = [
        {"role": "system", "content":
            "Du bist ein kritischer Synthesizer. Markiere Widersprueche explizit."},
        {"role": "user", "content": judge_prompt},
    ]

    if judge == "cloud" and _OPENROUTER_KEY and not _check_budget(_CLOUD_MODEL):
        synthesis = _openrouter_chat(_CLOUD_MODEL, judge_msgs, purpose="council_judge")
    else:
        synthesis = _ollama_chat(local_model, judge_msgs, num_ctx=8192, timeout=300.0)

    return (
        "=== RAT DER MODELLE ===\n\n"
        f"--- Lokal (gpt-oss:20b) ---\n{local_ans}\n\n"
        f"--- Cloud (DeepSeek) ---\n{cloud_ans}\n\n"
        f"--- Richter-Synthese ({judge}) ---\n{synthesis}"
    )


@mcp.tool()
def budget_status() -> str:
    """Zeigt den heutigen Cloud-API-Verbrauch und das Tageslimit.
    Für: prüfen, wie viel Cloud-Budget heute noch übrig ist, bevor man
    cloud_reason / cloud_cheap / cloud_code aufruft."""
    _init_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(_DB_PATH) as con:
        rows = con.execute(
            "SELECT model, COUNT(*), SUM(in_tok), SUM(out_tok), SUM(cost_usd) "
            "FROM cloud_calls WHERE ts LIKE ? AND status='ok' "
            "GROUP BY model ORDER BY SUM(cost_usd) DESC",
            (f"{today}%",),
        ).fetchall()
        total_usd = con.execute(
            "SELECT SUM(cost_usd) FROM cloud_calls WHERE ts LIKE ? AND status='ok'",
            (f"{today}%",),
        ).fetchone()[0] or 0.0
        blocked = con.execute(
            "SELECT COUNT(*) FROM cloud_calls WHERE ts LIKE ? AND status='blocked_budget'",
            (f"{today}%",),
        ).fetchone()[0] or 0

    total_eur = total_usd * _USD_TO_EUR
    limit_eur = _DAILY_LIMIT_EUR
    pct = (total_eur / limit_eur * 100) if limit_eur > 0 else 0

    lines = [
        f"Cloud-Budget heute ({today}):",
        f"  Verbraucht: {total_eur:.4f} € ({total_usd:.5f} USD)  "
        f"von {limit_eur:.2f} € Limit  [{pct:.1f}%]",
    ]
    if blocked:
        lines.append(f"  ⚠️  {blocked} Call(s) durch Budget-Limit geblockt")
    if rows:
        lines.append("  Aufschlüsselung:")
        for model, n, in_t, out_t, cost in rows:
            eur = (cost or 0) * _USD_TO_EUR
            lines.append(f"    {model}: {n} Calls | {in_t:,} In + {out_t:,} Out Tok "
                         f"| {eur:.4f} €")
    else:
        lines.append("  Keine Cloud-Calls heute.")
    remaining = max(0.0, limit_eur - total_eur)
    lines.append(f"  Restbudget: {remaining:.4f} €")
    return "\n".join(lines)


@mcp.tool()
def ollama_loaded_models() -> str:
    """Zeigt welche Ollama-Modelle aktuell im VRAM geladen sind und wie viel sie belegen.
    Fuer: pruefen ob VRAM frei ist, bevor man ComfyUI (Bild/Video) startet."""
    import httpx
    try:
        r = httpx.get(f"{_OLLAMA}/api/ps", timeout=5)
    except httpx.ConnectError:
        return "[Fehler: Ollama nicht erreichbar]"
    if r.status_code != 200:
        return f"[Fehler: Ollama /api/ps HTTP {r.status_code}]"
    models = r.json().get("models", [])
    if not models:
        return "Kein Modell im VRAM geladen — GPU frei."
    lines = [f"{len(models)} Modell(e) im VRAM:"]
    for m in models:
        vram_mb = m.get("size_vram", 0) // (1024 * 1024)
        total_mb = m.get("size", 0) // (1024 * 1024)
        lines.append(f"  - {m['name']}: VRAM {vram_mb} MB (Gesamt {total_mb} MB)")
    return "\n".join(lines)


@mcp.tool()
def ollama_unload_all() -> str:
    """Entlaedt ALLE geladenen Ollama-Modelle aus dem VRAM.

    PFLICHT vor Bild- und Video-Generierung via ComfyUI — das grosse LLM (gpt-oss-32k,
    ~14 GB) und ComfyUI/SDXL (~6-10 GB) passen nicht gleichzeitig in 16 GB VRAM.

    WICHTIG fuer Sequenzen (mehrere Bilder/Videos hintereinander):
      1. Einmal ollama_unload_all() am Anfang
      2. ALLE ComfyUI-Jobs hintereinander (kein zwischenzeitliches Reload!)
      3. Danach ollama_reload_main() — Modell vorladen bevor LLM-Aktionen folgen
         (z.B. senden, beschreiben, weiterrechnen)

    Einzeljob-Workflow:
      1. llm.ollama_unload_all()
      2. comfy / video-generate
      3. llm.ollama_reload_main()  — dann weiter mit LLM-Aufgaben
    """
    import httpx
    import subprocess

    try:
        r = httpx.get(f"{_OLLAMA}/api/ps", timeout=5)
    except httpx.ConnectError:
        return "[Fehler: Ollama nicht erreichbar — nichts zu entladen.]"
    if r.status_code != 200:
        return f"[Fehler: Ollama /api/ps HTTP {r.status_code}]"

    models = r.json().get("models", [])
    if not models:
        return "Kein Modell geladen — VRAM bereits frei. ComfyUI kann direkt starten."

    unloaded: list[str] = []
    errors: list[str] = []
    for m in models:
        name = m["name"]
        vram_mb = m.get("size_vram", 0) // (1024 * 1024)
        try:
            # keep_alive=0 weist Ollama an, das Modell sofort zu entladen
            httpx.post(
                f"{_OLLAMA}/api/generate",
                json={"model": name, "keep_alive": 0},
                timeout=15,
            )
            unloaded.append(f"{name} ({vram_mb} MB VRAM)")
        except Exception:
            # CLI-Fallback
            try:
                subprocess.run(
                    ["ollama", "stop", name],
                    capture_output=True, timeout=10, check=False,
                )
                unloaded.append(f"{name} ({vram_mb} MB VRAM, via CLI)")
            except Exception as e2:
                errors.append(f"{name}: {e2}")

    audit_log("ollama_unload_all",
              f"Entladen: {', '.join(unloaded) or 'keine'}", "OK")
    lines = [f"VRAM freigegeben: {len(unloaded)} Modell(e) entladen."]
    lines += [f"  - {u}" for u in unloaded]
    if errors:
        lines.append("Nicht entladen (Fehler):")
        lines += [f"  ! {e}" for e in errors]
    lines.append("ComfyUI kann jetzt starten.")
    return "\n".join(lines)


@mcp.tool()
def ollama_reload_main() -> str:
    """Laedt das Haupt-LLM (gpt-oss-32k) wieder in den VRAM vor.

    NACH dem letzten ComfyUI-Job aufrufen — BEVOR LLM-Aktionen folgen
    (Versand, Beschreibung, weitere Berechnungen). So ist das Modell
    sofort bereit und der naechste Aufruf hat keine Kaltstartverzoegerung.

    Sequenz-Workflow:
      ollama_unload_all()
      → comfy/video Job 1
      → comfy/video Job 2
      → ...alle Jobs...
      → ollama_reload_main()   <-- hier
      → mail senden / telegram / weiter mit LLM
    """
    import httpx

    try:
        # keep_alive=-1 = "fuer immer halten" (bis naechstes explizites Entladen)
        # Leeres Prompt laedt das Modell, ohne Tokens zu generieren
        r = httpx.post(
            f"{_OLLAMA}/api/generate",
            json={"model": _MAIN_MODEL, "prompt": "", "keep_alive": -1},
            timeout=60,
        )
    except httpx.ConnectError:
        return "[Fehler: Ollama nicht erreichbar — Modell konnte nicht vorgeladen werden.]"
    except httpx.TimeoutException:
        return f"[Timeout: {_MAIN_MODEL} braucht zu lange zum Laden — wird beim naechsten Aufruf automatisch geladen.]"

    if r.status_code != 200:
        return f"[Fehler: Ollama HTTP {r.status_code} beim Vorladen von {_MAIN_MODEL}]"

    audit_log("ollama_reload_main", f"Vorgeladen: {_MAIN_MODEL}", "OK")
    # Aktuellen VRAM-Stand pruefen
    ps = httpx.get(f"{_OLLAMA}/api/ps", timeout=5)
    loaded = [m["name"] for m in ps.json().get("models", [])] if ps.status_code == 200 else []
    if any(_MAIN_MODEL in m for m in loaded):
        vram_info = next(
            (f"{m.get('size_vram', 0) // (1024*1024)} MB"
             for ml in [ps.json().get("models", [])]
             for m in ml if _MAIN_MODEL in m["name"]),
            "?"
        )
        return f"Bereit: {_MAIN_MODEL} im VRAM ({vram_info}). LLM-Aufgaben koennen sofort starten."
    return f"{_MAIN_MODEL} wird geladen (erscheint beim ersten LLM-Aufruf im VRAM)."


def _empirical_best(kind: str) -> tuple[str, dict] | None:
    """F2: belegt bestes Modell für einen Aufgabentyp — oder None (zu wenig Daten, D18).
    Rang: höchste Erfolgsquote, bei Gleichstand niedrigere Median-Latenz."""
    _routing_init()
    with sqlite3.connect(_ROUTING_DB) as con:
        rows = con.execute(
            "SELECT model, COUNT(*) n, AVG(ok) success, AVG(latency) lat, AVG(cost_usd) cost "
            "FROM runs WHERE kind=? GROUP BY model", (kind,)).fetchall()
    qualified = [r for r in rows if r[1] >= _ROUTING_MIN_RUNS]
    if not qualified:
        return None
    best = max(qualified, key=lambda r: (r[2], -r[3]))
    return best[0], {"runs": best[1], "success": best[2], "latency": best[3], "cost": best[4]}


@mcp.tool()
def route_model(task_description: str) -> str:
    """Empfiehlt, welches lokale Modell/Tool für eine Aufgabe am besten passt.
    Für: das Hirn entscheidet vorab, welches Spezial-Tool es aufrufen soll.
    F2 (V3): sobald genug Trace-Daten vorliegen (>=20 Läufe je Aufgabentyp+Modell),
    wählt das BELEGT beste Modell statt der Handregel; die Handregel bleibt
    Kaltstart-Prior. 10% Exploration, damit Alternativen Daten sammeln.
    Gibt Aufgabentyp, Modell, passendes llm-Tool und Begründung zurück."""
    import random

    t = task_description.lower()
    if any(k in t for k in ("bild", "image", "screenshot", "foto", "diagramm", "ocr", "sieh")):
        kind = "vision"; tool = "llm__vision_describe"
    elif any(k in t for k in ("code", "funktion", "function", "skript", "script",
                              "programm", "klasse", "bug", "refactor", "python", "java")):
        kind = "code"; tool = "llm__code_generate"
    elif any(k in t for k in ("kurz", "schnell", "klassifizier", "ja/nein", "label",
                              "einordn", "quick")):
        kind = "quick"; tool = "llm__quick_answer"
    else:
        kind = "reasoning"; tool = "llm__reason_deep"

    hand_model, hand_why = _MODEL_MAP[kind]

    # Exploration (Banditen-Prinzip, simpel): gelegentlich bewusst eine
    # Alternative empfehlen, damit auch andere Modelle Datenpunkte sammeln.
    if random.random() < _ROUTING_EXPLORE:
        alts = [m for k2, (m, _) in _MODEL_MAP.items() if k2 != kind and k2 != "vision"]
        if alts:
            alt = random.choice(alts)
            return (f"Aufgabentyp: {kind}\nModell: {alt}\nTool: {tool}\n"
                    f"Grund: EXPLORATION (10%-Anteil) — Alternativmodell sammelt "
                    f"Datenpunkte fürs empirische Routing (F2).")

    emp = _empirical_best(kind)
    if emp:
        model, stats = emp
        src = "EMPIRISCH"
        why = (f"belegt bestes Modell für '{kind}': {stats['success']*100:.0f}% Erfolg "
               f"über {stats['runs']} Läufe, Ø {stats['latency']:.1f}s"
               + (f", Ø ${stats['cost']:.4f}" if stats['cost'] else ""))
        if model != hand_model:
            why += f" — überschreibt Handregel ({hand_model})"
    else:
        model, src, why = hand_model, "Handregel (Kaltstart-Prior)", hand_why

    return (f"Aufgabentyp: {kind}\nModell: {model}\nTool: {tool}\n"
            f"Quelle: {src}\nGrund: {why}\n"
            f"Hinweis: Tool '{tool}' aufrufen; VRAM-Lage ggf. mit planner__can_load prüfen.")


@mcp.tool()
def routing_stats() -> str:
    """F2: zeigt die empirischen Routing-Daten je (Aufgabentyp, Modell):
    Anzahl Läufe, Erfolgsquote, Ø-Latenz, Ø-Kosten. Ab >=20 Läufen (D18)
    überschreibt die Empirie die Handregel in route_model."""
    _routing_init()
    with sqlite3.connect(_ROUTING_DB) as con:
        rows = con.execute(
            "SELECT kind, model, COUNT(*) n, AVG(ok) success, AVG(latency) lat, "
            "AVG(cost_usd) cost FROM runs GROUP BY kind, model "
            "ORDER BY kind, success DESC").fetchall()
    if not rows:
        return ("Noch keine Routing-Daten — sie sammeln sich automatisch bei jeder "
                "Nutzung von code_generate/reason_deep/quick_answer/vision_describe.")
    lines = [f"EMPIRISCHES ROUTING (F2) — Daten-Schwelle: {_ROUTING_MIN_RUNS} Läufe (D18)\n",
             f"{'Aufgabentyp':12} {'Modell':28} {'Läufe':>6} {'Erfolg':>7} {'Ø-Lat':>7} {'Ø-Kosten':>9}  Status"]
    for kind, model, n, success, lat, cost in rows:
        status = "AKTIV (Empirie)" if n >= _ROUTING_MIN_RUNS else f"sammelt ({n}/{_ROUTING_MIN_RUNS})"
        cost_s = f"${cost:.4f}" if cost else "gratis"
        lines.append(f"{kind:12} {model:28} {n:>6} {success*100:>6.0f}% {lat:>6.1f}s {cost_s:>9}  {status}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
