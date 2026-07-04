"""
retro.py — Wochen-Retro der Schöpfer-Matrix (N9, V3+V10)
Liest letzte 7 Tage aus trace.db + eval/tests.yaml-Ergebnisse,
generiert Top-3-Verbesserungsvorschläge via lokalem LLM, sendet via Telegram.

Aufruf: python retro.py  (oder via retro.cmd)
"""
from __future__ import annotations

import os
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Python 3.13+ / Zertifikatsketten: gleicher SSL-Kontext wie briefing.py
# (Pruefung bleibt an, nur VERIFY_X509_STRICT raus; httpx fand hier zudem
# kein CA-Bundle -> urllib + dieser Kontext ist der bewaehrte Weg).
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

# ─── Konfiguration ────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent  # portabel: Ordner dieser Datei = Matrix-Root
TRACE_DB = ROOT / "mcp-servers" / "trace_mcp" / "trace.db"
EVAL_DIR = ROOT / "eval"
STATE_DIR = ROOT / "openclaw-workspace" / "state"
OLLAMA_MODEL = os.environ.get("RETRO_MODEL", "gpt-oss-32k")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")
LOG_PATH = ROOT / "openclaw-workspace" / "output" / "retro.log"

# ─── Daten sammeln ────────────────────────────────────────────────────────────

def _collect_trace_summary(days: int = 7) -> str:
    if not TRACE_DB.exists():
        return "Keine Trace-DB gefunden."
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(TRACE_DB) as c:
            c.row_factory = sqlite3.Row
            total = c.execute("SELECT COUNT(*) FROM turns WHERE ts >= ?", (since,)).fetchone()[0]
            errors = c.execute(
                "SELECT COUNT(*) FROM turns WHERE ts >= ? AND status != 'ok'", (since,)
            ).fetchone()[0]
            cost = c.execute(
                "SELECT COALESCE(SUM(cost_usd),0) FROM turns WHERE ts >= ?", (since,)
            ).fetchone()[0]
            # Top-5 Fehler-Zusammenfassungen
            err_rows = c.execute(
                "SELECT summary, tools FROM turns WHERE ts >= ? AND status != 'ok' LIMIT 5",
                (since,),
            ).fetchall()
            # Häufigste Tools
            tool_rows = c.execute(
                "SELECT tools FROM turns WHERE ts >= ? AND tools != ''", (since,)
            ).fetchall()
    except Exception as e:
        return f"Trace-DB-Fehler: {e}"

    tool_counts: dict[str, int] = {}
    for row in tool_rows:
        for t in (row[0] or "").split(","):
            t = t.strip()
            if t:
                tool_counts[t] = tool_counts.get(t, 0) + 1
    top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]

    lines = [
        f"TRACE (letzte {days} Tage):",
        f"  Turns: {total}  Fehler: {errors} ({errors/total*100:.1f}% Fehlerrate)"
        if total else "  Turns: 0",
        f"  Kosten: ${cost:.4f}",
        f"  Top-Tools: {', '.join(f'{n}({c})' for n,c in top_tools) or 'keine'}",
    ]
    if err_rows:
        lines.append("  Fehler-Details:")
        for r in err_rows:
            lines.append(f"    - [{r['tools'] or '?'}] {(r['summary'] or '')[:80]}")
    return "\n".join(lines)


def _collect_eval_summary() -> str:
    """Letztes Golden-Eval-Ergebnis aus nightly_golden.log (V18-Runner).

    Frueher startete das hier den TOTEN alten runner.py als Subprozess
    (kaputter 'openclaw agent --local'-Pfad) und hing 300s im Timeout.
    Jetzt: nur das Log des nächtlichen Laufs lesen — schnell und ehrlich.
    """
    log = EVAL_DIR / "results" / "nightly_golden.log"
    if not log.exists():
        return "EVAL: noch kein Golden-Lauf protokolliert."
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
        results = re.findall(r"ERGEBNIS:\s*(\d+)/(\d+)", text)
        regs = re.findall(r"REGRESSION:\s*(.+)", text)
        stamps = re.findall(r"\[(\d{4}-\d{2}-\d{2})_(\d{4})\] Golden-Eval Ende", text)
        if not results:
            return "EVAL: kein Ergebnis im Log (nur Skips? Ollama nachts aus)."
        passed, total = (int(x) for x in results[-1])
        when = f"{stamps[-1][0]} {stamps[-1][1][:2]}:{stamps[-1][1][2:]}" if stamps else "?"
        line = f"EVAL (Golden, letzter Lauf {when}): {passed}/{total} gruen"
        if passed < total and regs:
            line += f"\n  letzte Regressionen: {regs[-1][:120]}"
        return line
    except Exception as e:
        return f"EVAL: Fehler: {e}"


def _llm_retro(trace_sum: str, eval_sum: str) -> str:
    """Generiert Top-3 Verbesserungsvorschläge via Ollama."""
    prompt = (
        "Du bist Qualitätssicherungs-Analyst der Schöpfer-Matrix (lokales KI-Agenten-System).\n\n"
        f"{trace_sum}\n\n{eval_sum}\n\n"
        "Analysiere die Daten und nenne genau 3 konkrete Verbesserungsvorschläge.\n"
        "Format:\n"
        "1. [Problem] → [Vorschlag] (Aufwand: gering/mittel/hoch)\n"
        "2. ...\n"
        "3. ...\n"
        "Sei präzise und handlungsorientiert. Keine Einleitung, kein Fazit."
    )
    import httpx
    try:
        r = httpx.post(
            "http://localhost:11434/api/generate",
            # gpt-oss ist ein Reasoning-Modell: es "denkt" erst (thinking-Feld) und
            # antwortet dann. num_predict 400 wurde komplett vom Denken aufgebraucht
            # -> response war leer. Also: mehr Budget + thinking als Fallback.
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"num_predict": 1500, "temperature": 0.3}},
            timeout=180,
        )
        data = r.json()
        text = (data.get("response") or "").strip()
        if not text:
            text = (data.get("thinking") or "").strip()
        return text or "[LLM lieferte keine Antwort]"
    except Exception as e:
        return f"[LLM nicht erreichbar: {e}]"


def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[retro] Telegram nicht konfiguriert — nur Logfile.")
        return False
    try:
        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=payload,
        )
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[retro] Telegram-Fehler: {e}")
        return False


# ─── Hauptlauf ────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now()
    week_str = now.strftime("KW%V %Y")
    print(f"[retro] Wochen-Retro {week_str} ...")

    trace_sum = _collect_trace_summary(days=7)
    print(trace_sum)

    eval_sum = _collect_eval_summary()
    print(eval_sum)

    suggestions = _llm_retro(trace_sum, eval_sum)
    print(f"\nVorschläge:\n{suggestions}")

    now_str = now.strftime("%d.%m.%Y %H:%M")
    message = (
        f"🔁 Wochen-Retro {week_str} ({now_str})\n\n"
        f"{trace_sum}\n\n"
        f"{eval_sum}\n\n"
        f"Top-3 Verbesserungen:\n{suggestions}\n\n"
        f"Umsetzung NUR nach GO (skill-creator)."
    )

    # Logfile
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n{message}\n")
    print(f"[retro] Logfile: {LOG_PATH}")

    sent = _send_telegram(message)
    print(f"[retro] Telegram: {'OK' if sent else 'nicht gesendet (kein Token/Chat-ID?)'}")
    print("[retro] Fertig.")


if __name__ == "__main__":
    # secrets.env laden falls vorhanden
    secrets = Path(__file__).resolve().parent / "secrets.env"
    if secrets.exists():
        for line in secrets.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    main()
