"""research-mcp — Lokale Tiefenrecherche als MCP-Server.

Mehrstufige Recherche ganz ohne Cloud-Key: ein Thema wird in Teilfragen zerlegt,
jede Teilfrage via echter Web-Suche (DuckDuckGo) recherchiert, die Top-Seiten
abgerufen und am Ende von einem lokalen Modell (gpt-oss) zu einem strukturierten
Bericht mit Quellen zusammengefasst. Ersetzt die Rolle von gpt-researcher als
schlanker, self-contained Dienst.

Tools:
  - deep_research(topic, ...)  -> kompletter Recherchebericht mit Quellen
  - web_lookup(query, ...)     -> schnelle einzelne Web-Suche

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# bot1 für die bewährte web_search-Funktion (DuckDuckGo + bs4) einbinden.
_BOT1 = Path(__file__).resolve().parents[2] / "bot1"
if str(_BOT1) not in sys.path:
    sys.path.insert(0, str(_BOT1))

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resilience import breaker  # noqa: E402  (R2: hängende Recherche friert nicht jeden Turn ein)

try:
    from generator.agent.tools.impl.web_search import web_search as _web_search
except Exception as _e:  # noqa: BLE001
    _web_search = None
    _IMPORT_ERR = str(_e)

mcp = FastMCP("research-mcp")

_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
# Großes Kontextmodell, das der Agent ohnehin geladen hat -> kein Modell-Swap.
_MODEL = os.environ.get("RESEARCH_MODEL", "gpt-oss-32k")


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


def _make_subqueries(topic: str, n: int) -> list[str]:
    """Zerlegt ein Thema in n konkrete Suchanfragen (per lokalem Modell)."""
    prompt = (
        f"Zerlege das folgende Recherchethema in genau {n} konkrete, voneinander "
        f"verschiedene Web-Suchanfragen, die zusammen das Thema gut abdecken. "
        f"Gib NUR die Suchanfragen aus, eine pro Zeile, ohne Nummerierung.\n\n"
        f"Thema: {topic}"
    )
    out = _ollama_chat([{"role": "user", "content": prompt}], timeout=120.0, num_ctx=4096)
    lines = [l.strip(" -•\t").strip() for l in out.splitlines() if l.strip()]
    queries = [l for l in lines if not l.startswith("[Fehler")]
    return queries[:n] if queries else [topic]


@mcp.tool()
@breaker("research")
def deep_research(topic: str, num_subqueries: int = 3, sources_per_query: int = 4) -> str:
    """Führt eine mehrstufige Web-Recherche zu einem Thema durch und liefert einen
    strukturierten Bericht MIT Quellen. Für: tiefe Fragen, die mehrere Quellen
    brauchen (Stand der Technik, Vergleiche, Hintergründe). Lokal, ohne Cloud-Key.
    `topic` = Thema/Frage, `num_subqueries` = Anzahl Teilrecherchen (1-5),
    `sources_per_query` = Treffer je Teilrecherche."""
    if _web_search is None:
        return f"[Fehler: web_search nicht verfügbar: {_IMPORT_ERR}]"
    num_subqueries = max(1, min(5, num_subqueries))
    sources_per_query = max(1, min(6, sources_per_query))

    subqueries = _make_subqueries(topic, num_subqueries)
    collected: list[str] = []
    for q in subqueries:
        res = _web_search(q, max_results=sources_per_query, fetch_top=True)
        collected.append(f"### Teilrecherche: {q}\n{res}")
    corpus = "\n\n".join(collected)
    if len(corpus) > 24000:  # Kontext schonen
        corpus = corpus[:24000] + "\n…[gekürzt]"

    synth_prompt = (
        "Du bist ein sorgfältiger Rechercheanalyst. Erstelle aus den folgenden "
        "Web-Suchergebnissen einen strukturierten deutschen Bericht zum Thema "
        f"\"{topic}\". Gliederung: Kurzfazit, dann die wichtigsten Punkte mit "
        "Belegen, dann eine Quellenliste (die URLs aus den Ergebnissen). "
        "Erfinde nichts; stütze dich nur auf die Ergebnisse.\n\n"
        f"=== SUCHERGEBNISSE ===\n{corpus}"
    )
    report = _ollama_chat([{"role": "user", "content": synth_prompt}],
                          timeout=420.0, num_ctx=32768)
    header = (f"RECHERCHEBERICHT — {topic}\n"
              f"(Teilrecherchen: {len(subqueries)} | Quellen je Recherche: {sources_per_query})\n"
              + "=" * 60 + "\n")
    return header + report


@mcp.tool()
@breaker("websearch")
def web_lookup(query: str, max_results: int = 5) -> str:
    """Schnelle einzelne Web-Suche (DuckDuckGo) inkl. Text der Top-Seite.
    Für: eine konkrete Faktenfrage, aktuelle Infos. Leichter als deep_research."""
    if _web_search is None:
        return f"[Fehler: web_search nicht verfügbar: {_IMPORT_ERR}]"
    return _web_search(query, max_results=max(1, min(10, max_results)), fetch_top=True)


if __name__ == "__main__":
    mcp.run()
