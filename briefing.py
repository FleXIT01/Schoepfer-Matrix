"""briefing.py — Schöpfer-Matrix Morgenbriefing (N1).

Läuft täglich um 07:00 via Windows Scheduled Task (briefing.cmd).
Liest briefing.yaml, fragt arXiv ab, sammelt Kosten/Eval/Backup-Status
und sendet eine kompakte Telegram-Zusammenfassung.

Abhängigkeiten: Python-stdlib + PyYAML (via pip install pyyaml)
"""
from __future__ import annotations

import html as html_lib
import os
import re
import sqlite3
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
BRIEFING_YAML = ROOT / "briefing.yaml"
COSTS_DB = ROOT / "mcp-servers" / "llm_mcp" / "costs.db"
GOLDEN_LOG = ROOT / "eval" / "results" / "nightly_golden.log"
# Backup-Ziel: aus BACKUP_DEST (matrix.env, via briefing.cmd/env.cmd), Fallback lokal.
BACKUPS_DIR = Path(os.environ.get("BACKUP_DEST", str(ROOT / "_backups")))

# Python 3.13+ erzwingt VERIFY_X509_STRICT — daran scheitern die CA-Ketten von
# Telegram/arXiv ("Basic Constraints of CA cert not marked critical"). Wir lassen
# die normale Zertifikatspruefung AN und nehmen nur das neue Strict-Flag raus.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")
_ARXIV_NS = "http://www.w3.org/2005/Atom"


# ─── Telegram ─────────────────────────────────────────────────────────────────

def _tg_send(text: str) -> bool:
    if not _TG_TOKEN or not _TG_CHAT:
        print("[warn] TELEGRAM_BOT_TOKEN / TELEGRAM_DEFAULT_CHAT_ID fehlen.", file=sys.stderr)
        return False
    try:
        payload = urllib.parse.urlencode({
            "chat_id": _TG_CHAT,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            data=payload,
        )
        urllib.request.urlopen(req, timeout=15, context=_SSL_CTX)
        return True
    except Exception as e:
        print(f"[warn] Telegram-Fehler: {e}", file=sys.stderr)
        return False


# ─── arXiv ────────────────────────────────────────────────────────────────────

def _arxiv_query(query: str, max_results: int, lookback_days: int) -> list[dict]:
    """Gibt Liste von {title, arxiv_id, published} zurück (nur neue Einreichungen)."""
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date()
    # arXiv-API: Mehrwort-Queries brauchen explizites AND je Wort — "all:a b c"
    # ignoriert den Filter und liefert einfach die neuesten Einreichungen
    # (deshalb standen unter jedem Thema dieselben themenfremden Paper).
    terms = " AND ".join(f"all:{w}" for w in query.split())
    params = urllib.parse.urlencode({
        "search_query": terms,
        "start": 0,
        "max_results": max_results + 2,  # etwas mehr, dann filtern
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "SchoepferMatrix/1.0 (mailto:starwars.felix@outlook.com)"
        })
        with urllib.request.urlopen(req, timeout=25, context=_SSL_CTX) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        papers = []
        for entry in root.findall(f"{{{_ARXIV_NS}}}entry"):
            title_el = entry.find(f"{{{_ARXIV_NS}}}title")
            id_el = entry.find(f"{{{_ARXIV_NS}}}id")
            pub_el = entry.find(f"{{{_ARXIV_NS}}}published")
            if title_el is None or id_el is None:
                continue
            pub_str = (pub_el.text or "")[:10] if pub_el is not None else "?"
            try:
                pub_date = datetime.strptime(pub_str, "%Y-%m-%d").date()
            except ValueError:
                pub_date = None
            if pub_date and pub_date < since:
                continue  # zu alt
            title = " ".join(title_el.text.split())
            arxiv_id = id_el.text.strip().split("/abs/")[-1].split("v")[0]
            papers.append({"title": title, "id": arxiv_id, "published": pub_str})
            if len(papers) >= max_results:
                break
        return papers
    except Exception as e:
        print(f"[warn] arXiv-Fehler ({query[:30]}): {e}", file=sys.stderr)
        return []


# ─── Kosten-Ledger ────────────────────────────────────────────────────────────

def _cloud_costs_yesterday() -> tuple[float, float]:
    """Gibt (verbrauch_eur, limit_eur) für gestern zurück."""
    if not COSTS_DB.exists():
        return 0.0, 2.0
    try:
        con = sqlite3.connect(str(COSTS_DB))
        row = con.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM cloud_calls "
            "WHERE date(ts)=date('now','-1 day')"
        ).fetchone()
        con.close()
        usd = row[0] if row else 0.0
        limit_eur = float(os.environ.get("CLOUD_DAILY_LIMIT_EUR", "2.0"))
        return round(usd * 0.92, 4), limit_eur
    except Exception:
        return 0.0, 2.0


# ─── Eval-Ergebnis ────────────────────────────────────────────────────────────

def _latest_eval() -> str | None:
    """Kurztext des letzten Golden-Eval-Laufs aus nightly_golden.log.

    Die alte runner.py/eval-*.yaml-Quelle ist tot (kaputter CLI-Pfad) —
    massgeblich ist jetzt das Log des V18-Runners (run_eval.cmd).
    """
    if not GOLDEN_LOG.exists():
        return None
    try:
        text = GOLDEN_LOG.read_text(encoding="utf-8", errors="replace")
        results = re.findall(r"ERGEBNIS:\s*(\d+)/(\d+)", text)
        skips = re.findall(r"\[(\d{4}-\d{2}-\d{2})_\d{4}\] SKIP:", text)
        stamps = re.findall(r"\[(\d{4}-\d{2}-\d{2})_(\d{4})\] Golden-Eval Ende", text)
        if not results:
            if skips:
                return f"[SKIP] uebersprungen (Ollama aus, {skips[-1]})"
            return None
        passed, total = (int(x) for x in results[-1])
        when = f"{stamps[-1][0]} {stamps[-1][1][:2]}:{stamps[-1][1][2:]}" if stamps else "?"
        failed = total - passed
        icon = "[OK]" if failed == 0 else ("[WARN]" if failed <= 2 else "[FAIL]")
        return f"{icon} {passed}/{total} gruen ({when})"
    except Exception:
        return None


# ─── Backup-Status ────────────────────────────────────────────────────────────

def _backup_status() -> str:
    if not BACKUPS_DIR.exists():
        return "[WARN] Backup-Laufwerk I: nicht erreichbar"
    dirs = sorted([d for d in BACKUPS_DIR.iterdir() if d.is_dir()], reverse=True)
    if not dirs:
        return "noch kein Backup"
    last = dirs[0]
    try:
        dt = datetime.strptime(last.name, "%Y-%m-%d_%H%M%S")
        age_h = (datetime.now() - dt).total_seconds() / 3600
        icon = "[OK]" if age_h < 30 else "[WARN]"
        return f"{icon} {dt.strftime('%d.%m. %H:%M')} (vor {age_h:.0f}h)"
    except Exception:
        return f"[OK] {last.name}"


# ─── Hauptfunktion ────────────────────────────────────────────────────────────

def main() -> None:
    if not BRIEFING_YAML.exists():
        print(f"[err] briefing.yaml nicht gefunden: {BRIEFING_YAML}", file=sys.stderr)
        sys.exit(1)
    with open(BRIEFING_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    arxiv_cfg = cfg.get("arxiv", {})
    max_results = int(arxiv_cfg.get("max_results", 3))
    lookback_days = int(arxiv_cfg.get("lookback_days", 1))
    topics = arxiv_cfg.get("topics", [])

    lines = [
        f"<b>MATRIX-BRIEFING {datetime.now().strftime('%d.%m.%Y %H:%M')}</b>",
        "",
    ]

    # arXiv-Abfragen
    if topics:
        lines.append("<b>Neue Paper (arXiv):</b>")
        any_paper = False
        for t in topics:
            label = html_lib.escape(t.get("label", "?"))
            query = t.get("query", "")
            papers = _arxiv_query(query, max_results, lookback_days)
            if papers:
                any_paper = True
                lines.append(f"  <b>{label}:</b>")
                for p in papers:
                    safe_title = html_lib.escape(p["title"][:90])
                    lines.append(
                        f'  · <a href="https://arxiv.org/abs/{p["id"]}">'
                        f"{safe_title}</a>"
                    )
            else:
                lines.append(f"  <b>{label}:</b> keine neuen Treffer")
        if not any_paper:
            lines.append("  Keine neuen Paper in den letzten 24h.")
        lines.append("")

    # Cloud-Kosten
    spent, limit = _cloud_costs_yesterday()
    cost_icon = "[OK]" if spent < limit * 0.5 else ("[WARN]" if spent < limit else "[LIMIT]")
    lines.append(f"<b>Cloud-Kosten gestern:</b> {cost_icon} {spent:.4f} EUR / {limit:.2f} EUR Limit")

    # Eval
    eval_txt = _latest_eval()
    lines.append(f"<b>Eval letzte Nacht:</b> {eval_txt or '— (noch kein Ergebnis)'}")

    # Backup
    lines.append(f"<b>Backup:</b> {_backup_status()}")

    msg = "\n".join(lines)
    print(msg)
    print()

    ok = _tg_send(msg)
    if ok:
        print("[ok] Briefing gesendet.")
    else:
        print("[warn] Telegram-Versand fehlgeschlagen — Token/Chat-ID pruefen.")
        sys.exit(1)


if __name__ == "__main__":
    main()
