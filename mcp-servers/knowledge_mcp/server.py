"""knowledge-mcp — durchsucht den lokalen Wissens-Index (Lern-Korpus).

Backend für den OpenClaw-Skill `knowledge-ask`. Durchsucht den von
knowledge-ingest/ingest.py erzeugten index.json mit einem BM25-ähnlichen
Ranking — komplett ohne externe Abhängigkeiten oder Docker. MaxKB/WeKnora
können dies später ersetzen; die Tool-Schnittstelle bleibt gleich.

Start (stdio):  python server.py
Voraussetzung:  vorher  python knowledge-ingest/ingest.py  ausführen.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("knowledge-mcp")

_INDEX_PATH = Path(__file__).resolve().parents[2] / "knowledge-ingest" / "index.json"
_TOKEN = re.compile(r"[a-zA-ZäöüÄÖÜß0-9]{3,}")
_CACHE: dict | None = None


def _load() -> dict | None:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not _INDEX_PATH.exists():
        return None
    try:
        _CACHE = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return _CACHE


def _score(query_terms: list[str], doc: dict, df: dict, n_docs: int) -> float:
    """BM25-ähnliches Ranking (k1=1.5, vereinfachte Längen-Normalisierung)."""
    tf: dict[str, int] = {}
    for t in doc["tokens"]:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for qt in query_terms:
        if qt not in tf:
            continue
        idf = math.log(1 + (n_docs - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5))
        f = tf[qt]
        score += idf * (f * 2.5) / (f + 1.5)
    return score


@mcp.tool()
def knowledge_search(query: str, max_results: int = 5, tag: str = "") -> str:
    """Durchsucht den lokalen Lern-Korpus (system-design-primer, roadmaps,
    public-apis, build-your-own-x, ...) und liefert die relevantesten Dokumente
    mit Auszug und Quelle. Optional auf ein Thema einschränken
    (tag: architektur|roadmap|apis|implementierung|coding|...).
    Für: Architektur-, API-, Lern- und Implementierungswissen."""
    index = _load()
    if index is None:
        return ("[Wissens-Index fehlt. Bitte zuerst ausführen:\n"
                "   python knowledge-ingest/ingest.py]")

    docs = index["docs"]
    if tag:
        docs = [d for d in docs if d.get("tag") == tag]
    if not docs:
        return f"[Keine Dokumente für tag='{tag}'.]"

    q_terms = [t.lower() for t in _TOKEN.findall(query)]
    if not q_terms:
        return "[Leere Suchanfrage.]"

    df, n = index["df"], index["n_docs"]
    ranked = sorted(docs, key=lambda d: _score(q_terms, d, df, n), reverse=True)
    top = [d for d in ranked if _score(q_terms, d, df, n) > 0][:max(1, min(max_results, 10))]

    if not top:
        return f"[Kein Treffer im Korpus für '{query}'.]"

    lines = [f"Wissens-Korpus: {len(top)} Treffer für '{query}'\n"]
    for i, d in enumerate(top, 1):
        lines.append(
            f"[{i}] {d['title']}  ({d['tag']})\n"
            f"    Quelle: {d['path']}\n"
            f"    {d['excerpt'][:300]}…\n"
        )
    return "\n".join(lines)


@mcp.tool()
def knowledge_stats() -> str:
    """Zeigt den Zustand des Wissens-Index (Anzahl Dokumente, Themen).
    Für: prüfen, ob der Korpus indexiert ist."""
    index = _load()
    if index is None:
        return "[Wissens-Index fehlt — bitte knowledge-ingest/ingest.py ausführen.]"
    tags: dict[str, int] = {}
    for d in index["docs"]:
        tags[d.get("tag", "?")] = tags.get(d.get("tag", "?"), 0) + 1
    lines = [f"Wissens-Index: {index['n_docs']} Dokumente, {len(index['df'])} Terme"]
    for t, c in sorted(tags.items(), key=lambda x: -x[1]):
        lines.append(f"  {t}: {c}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
