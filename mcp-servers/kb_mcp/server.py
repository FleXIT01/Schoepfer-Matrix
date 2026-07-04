"""kb-mcp — schlanker Zugang zur WeKnora-Wissensbasis (Hybrid-RAG) als MCP-Server.

Dünner Wrapper um WeKnoras Hybrid-Search-API (Qdrant dense + ParadeDB BM25,
Embedding via bge-m3, optional BGE-Reranker). Statt WeKnoras 28 Verwaltungs-Tools
exponiert dieser Server nur das, was das Hirn wirklich braucht: semantisch+keyword
über den Korpus suchen. Das Hirn (lokal oder Cloud) formuliert die Antwort selbst.

Tools:
  - kb_search(query, top_k)  -> relevanteste Korpus-Stellen (Hybrid Search)
  - kb_stats()               -> Größe/Status der Wissensbasis

Env: WEKNORA_BASE_URL, WEKNORA_API_KEY, WEKNORA_KB_ID
Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import breaker  # noqa: E402  (R2: kranke WeKnora blockt nicht jeden Turn)
from tracelib import log_step, step_timer  # noqa: E402  (V14: Pro-Schritt-Latenz)

mcp = FastMCP("kb-mcp")

_BASE = os.environ.get("WEKNORA_BASE_URL", "http://localhost:8080/api/v1").rstrip("/")
_KEY = os.environ.get("WEKNORA_API_KEY", "")
_KB = os.environ.get("WEKNORA_KB_ID", "")
# BGE-Reranker-v2-Dienst (leer = ohne Rerank, nur Hybrid).
_RERANK_URL = os.environ.get("RERANK_URL", "http://localhost:8011").rstrip("/")


def _rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Ordnet Hybrid-Kandidaten mit BGE-reranker-v2 neu (falls Dienst erreichbar)."""
    if not _RERANK_URL or not candidates:
        return candidates[:top_k]
    import httpx

    docs = [(c.get("content") or "") for c in candidates]
    _t0 = time.monotonic()
    try:
        r = httpx.post(f"{_RERANK_URL}/rerank",
                       json={"query": query, "documents": docs}, timeout=60)
        log_step("reranker", latency_ms=int((time.monotonic() - _t0) * 1000),
                 detail=f"BGE-v2 {len(docs)}->{top_k} http{r.status_code}")
        if r.status_code != 200:
            return candidates[:top_k]
        ranked = r.json().get("results") or []
        out = []
        for item in ranked[:top_k]:
            idx = item.get("index", 0)
            if 0 <= idx < len(candidates):
                c = dict(candidates[idx])
                c["rerank_score"] = item.get("score")
                out.append(c)
        return out or candidates[:top_k]
    except Exception:  # noqa: BLE001
        return candidates[:top_k]


def _headers() -> dict:
    return {"X-API-Key": _KEY, "Content-Type": "application/json"}


@mcp.tool()
@breaker("weknora")
def kb_search(query: str, top_k: int = 5) -> str:
    """Durchsucht die Wissensbasis (Korpus der Schöpfer-Matrix) per HYBRID SEARCH
    (semantische Vektor-Suche + Keyword/BM25, multilingual). Für: fundierte Fakten
    aus dem Lern-Korpus holen, bevor man antwortet. `query` = Frage/Stichworte,
    `top_k` = Anzahl Treffer. Gibt die relevantesten Textstellen mit Quelle zurück."""
    if not _KB:
        return "[Fehler: WEKNORA_KB_ID nicht gesetzt.]"
    import httpx

    # Mehr Kandidaten holen, als am Ende gebraucht werden — der Reranker sortiert.
    fetch_n = max(top_k * 3, 12)
    payload = {"query_text": query, "match_count": min(30, fetch_n),
               "vector_threshold": 0.1, "keyword_threshold": 0.0}
    try:
        with step_timer("retrieval", detail=f"WeKnora hybrid match={min(30, fetch_n)}"):
            r = httpx.request("GET", f"{_BASE}/knowledge-bases/{_KB}/hybrid-search",
                              headers=_headers(), json=payload, timeout=60)
    except httpx.ConnectError:
        return (f"[Fehler: WeKnora nicht erreichbar unter {_BASE}. "
                "Läuft der Docker-Stack? (WeKnora-Container + rerank-server)]")
    if r.status_code == 401:
        return "[Fehler: WeKnora-API-Key ungültig (401).]"
    if r.status_code != 200:
        return f"[Fehler: WeKnora HTTP {r.status_code}: {r.text[:200]}]"
    data = r.json().get("data") or []
    if not data:
        return (f"Keine Treffer in der Wissensbasis für: {query}\n"
                f"KONFIDENZ: KEINE_TREFFER — Wissenslücke erkannt.\n"
                f"I4-Tipp: auto_research_quota() prüfen → jobs.job_submit('[AUTO] deep_research: {query[:80]}')")
    # Hybrid-Kandidaten -> BGE-reranker-v2 -> Top-K
    results = _rerank(query, data, max(1, min(20, top_k)))
    reranked = any("rerank_score" in c for c in results)
    head = (f"WISSENSBASIS-TREFFER für: {query} "
            f"(Hybrid {'+ BGE-Reranker-v2' if reranked else '(ohne Rerank)'})")
    lines = [head, "=" * 50]
    for i, c in enumerate(results, 1):
        src = c.get("knowledge_title") or c.get("knowledge_filename") or "?"
        score = c.get("rerank_score", c.get("score", 0.0)) or 0.0
        content = (c.get("content") or "").strip().replace("\n", " ")
        lines.append(f"\n[{i}] (Score {score:.3f}) Quelle: {src}\n{content[:500]}")
    # I4: Low-Confidence-Indikator — wenn alle Scores schwach, Neugier-Schleife anbieten
    max_score = max((c.get("rerank_score", c.get("score", 0.0)) or 0.0) for c in results)
    if max_score < 0.30:
        lines.append(
            f"\nKONFIDENZ: NIEDRIG (Höchster Score: {max_score:.2f}) — "
            f"Wissensbasis hat keine guten Treffer für diese Anfrage.\n"
            f"I4-Tipp: auto_research_quota() prüfen → "
            f"jobs.job_submit('[AUTO] deep_research: {query[:80]}') wenn < 3 Auto-Jobs heute."
        )
    return "\n".join(lines)


@mcp.tool()
def kb_ingest(
    text: str,
    title: str = "",
    meta_json: str = "{}",
) -> str:
    """Fügt Text in die Wissensbasis ein (V12: Lern-Schleife schließen).
    Verwende nach jedem research-/deep-research-/pdf_extract-Ergebnis, damit
    das System seine eigenen Berichte später abrufen kann.

    text      = Inhalt (Markdown/Klartext, max ~200 KB empfohlen)
    title     = Dokumenttitel (leer = Zeitstempel)
    meta_json = optionale Metadaten als JSON-Dict z.B. '{"quelle":"arXiv","thema":"EGFR"}'

    Gibt die WeKnora-Knowledge-ID zurück oder eine Fehlermeldung."""
    if not _KB:
        return "[Fehler: WEKNORA_KB_ID nicht gesetzt.]"

    import httpx
    import json as _json
    import tempfile
    import os
    from datetime import datetime

    title_clean = title.strip() or datetime.now().strftime("Ingest_%Y%m%d_%H%M%S")

    try:
        _json.loads(meta_json) if meta_json.strip() else {}
    except Exception:
        pass

    # Titelzeile voranstellen wenn nicht vorhanden
    if not text.startswith("#"):
        full_text = f"# {title_clean}\n\n{text}"
    else:
        full_text = text

    # Temp-Datei mit .md-Extension — WeKnora erkennt Markdown
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(full_text)
            tmp_path = tmp.name

        headers = {"X-API-Key": _KEY}
        with open(tmp_path, "rb") as f:
            r = httpx.post(
                f"{_BASE}/knowledge-bases/{_KB}/knowledge/file",
                headers=headers,
                files={"file": (f"{title_clean}.md", f, "text/markdown")},
                data={"enable_multimodel": "false"},
                timeout=120,
            )
    except httpx.ConnectError:
        return f"[Fehler: WeKnora nicht erreichbar unter {_BASE}.]"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if r.status_code not in (200, 201):
        return f"[kb_ingest] Fehler HTTP {r.status_code}: {r.text[:300]}"

    resp = r.json()
    kid = (resp.get("data") or {}).get("id") or resp.get("id") or "?"
    return f"[kb_ingest] OK — Dokument '{title_clean}' in Wissensbasis (ID: {kid})."


@mcp.tool()
def kb_ingest_url(
    url: str,
    title: str = "",
) -> str:
    """Ingestiert eine Web-URL in die Wissensbasis (WeKnora lädt + chunked).
    Gut für: Paper-Abstracts, Docs-Seiten, Blog-Posts direkt per URL einlesen.

    url   = vollständige HTTP(S)-URL
    title = optionaler Dokumenttitel (leer = URL selbst)

    Gibt die WeKnora-Knowledge-ID zurück oder eine Fehlermeldung."""
    if not _KB:
        return "[Fehler: WEKNORA_KB_ID nicht gesetzt.]"

    import httpx

    if not url.startswith(("http://", "https://")):
        return "[kb_ingest_url] URL muss mit http:// oder https:// beginnen."

    try:
        r = httpx.post(
            f"{_BASE}/knowledge-bases/{_KB}/knowledge/url",
            headers=_headers(),
            json={"url": url, "enable_multimodel": False},
            timeout=120,
        )
    except httpx.ConnectError:
        return f"[Fehler: WeKnora nicht erreichbar unter {_BASE}.]"

    if r.status_code not in (200, 201):
        return f"[kb_ingest_url] Fehler HTTP {r.status_code}: {r.text[:300]}"

    resp = r.json()
    kid = (resp.get("data") or {}).get("id") or resp.get("id") or "?"
    label = title.strip() or url
    return f"[kb_ingest_url] OK — '{label}' in Wissensbasis (ID: {kid})."


# ════════════════════════════════════════════════════════════════════════════════
#  G1 — PLAYBOOKS: prozedurales Gedächtnis (V3 Phase 12)
#  WIE eine Aufgabe gelöst wurde — lokale SQLite (Signatur-Lookup muss exakt
#  und schnell sein; WeKnora bleibt für semantische FAKTEN-Suche zuständig).
# ════════════════════════════════════════════════════════════════════════════════

import sqlite3 as _sql
from datetime import datetime as _dt

_PB_DB = Path(__file__).parent / "playbooks.db"


def _pb_init() -> None:
    with _sql.connect(_PB_DB) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS playbooks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                signature  TEXT NOT NULL,      -- z.B. 'repo-review+python'
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,      -- Schritte, Tools, Stolperstellen
                uses       INTEGER NOT NULL DEFAULT 0,
                archived   INTEGER NOT NULL DEFAULT 0,  -- D19: nie hart löschen
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pb_sig ON playbooks(signature);
        """)
        con.commit()


def _pb_now() -> str:
    return _dt.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def playbook_save(signature: str, title: str, content: str) -> str:
    """Speichert ein PLAYBOOK: wie eine mehrstufige Aufgabe ERFOLGREICH gelöst wurde.

    NUR nach bestandenem Gate aufrufen (erfolgreiche supervisor-Läufe) — sonst
    lernt das System Murks. Gibt es zur Signatur schon ein Playbook, wird das
    alte archiviert (nie gelöscht, D19) und das neue gespeichert.

    signature: Aufgaben-Signatur 'kategorie+stichwort', z.B. 'repo-review+python',
               'recherche+biotech', 'android-app+protein'
    title:     Kurzbeschreibung der Aufgabe
    content:   Das Verfahren: Schrittfolge, genutzte Tools+Parameter,
               Stolperstellen + wie umgangen (Markdown)."""
    _pb_init()
    sig = signature.strip().lower()
    if not sig or not content.strip():
        return "[playbook_save] signature und content sind Pflicht."
    with _sql.connect(_PB_DB) as con:
        old = con.execute(
            "SELECT id FROM playbooks WHERE signature=? AND archived=0", (sig,)
        ).fetchall()
        for (oid,) in old:
            con.execute("UPDATE playbooks SET archived=1, updated_at=? WHERE id=?",
                        (_pb_now(), oid))
        con.execute(
            "INSERT INTO playbooks (signature, title, content, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (sig, title.strip(), content.strip(), _pb_now(), _pb_now()))
        con.commit()
    note = f" ({len(old)} Vorgänger archiviert)" if old else ""
    return f"[playbook_save] Playbook für '{sig}' gespeichert{note}."


@mcp.tool()
def playbook_lookup(signature: str) -> str:
    """Holt das Playbook zu einer Aufgaben-Signatur — VOR dem Planen aufrufen!

    Match-Logik: exakte Signatur zuerst, sonst Teilwort-Match (beste Überdeckung).
    Das Playbook ist ein VORSCHLAG als Startplan, kein Befehl (D16) — bei
    anderer Lage davon abweichen.

    signature: z.B. 'repo-review+python'. Bei Treffer: Titel + Verfahren."""
    _pb_init()
    sig = signature.strip().lower()
    with _sql.connect(_PB_DB) as con:
        row = con.execute(
            "SELECT id, title, content, uses, created_at FROM playbooks "
            "WHERE signature=? AND archived=0 ORDER BY created_at DESC LIMIT 1", (sig,)
        ).fetchone()
        if not row:
            # Teilwort-Match: meiste gemeinsame Tokens gewinnt
            tokens = set(t for t in sig.replace("+", " ").split() if t)
            best, best_score = None, 0
            for r in con.execute(
                "SELECT id, signature, title, content, uses, created_at "
                "FROM playbooks WHERE archived=0").fetchall():
                cand = set(r[1].replace("+", " ").split())
                score = len(tokens & cand)
                if score > best_score:
                    best, best_score = r, score
            if best and best_score > 0:
                row = (best[0], best[2], best[3], best[4], best[5])
        if not row:
            return (f"Kein Playbook für '{sig}' — Aufgabe normal planen und am Ende "
                    f"mit playbook_save das Verfahren festhalten.")
        pid, title, content, uses, created = row
        con.execute("UPDATE playbooks SET uses=uses+1 WHERE id=?", (pid,))
        con.commit()
    return (f"PLAYBOOK '{title}' (Signatur-Treffer, {uses + 1}. Nutzung, vom {created}):\n"
            f"Als STARTPLAN laden und an die aktuelle Lage anpassen — kein Dogma.\n\n"
            f"{content}")


@mcp.tool()
def playbook_list() -> str:
    """Listet alle aktiven Playbooks (Signatur, Titel, Nutzungen)."""
    _pb_init()
    with _sql.connect(_PB_DB) as con:
        rows = con.execute(
            "SELECT signature, title, uses, created_at FROM playbooks "
            "WHERE archived=0 ORDER BY uses DESC, created_at DESC").fetchall()
    if not rows:
        return "Noch keine Playbooks gespeichert."
    lines = [f"PLAYBOOKS ({len(rows)} aktiv):"]
    for sig, title, uses, created in rows:
        lines.append(f"  [{sig}] {title}  ({uses}x genutzt, seit {created})")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════════
#  G2 — GEDÄCHTNIS-HYGIENE: Dedup + Konfliktauflösung (V3 Phase 12)
#  Arbeitet auf den lokalen Speichern (playbooks.db). D19: nie hart löschen —
#  immer archivieren. Lauf-Protokoll fürs Morgenbriefing (N1).
# ════════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def kb_dedup() -> str:
    """Gedächtnis-Pflege: führt near-duplicate Playbooks zusammen (G2).

    Gleiche Signatur ODER >85% Text-Ähnlichkeit → ältere Version wird
    archiviert (NIE gelöscht, D19), die neueste bleibt aktiv.
    Wöchentlich per Cron aufrufen (neben der Retro N9).
    Gibt Protokoll zurück: 'x zusammengeführt, y archiviert'."""
    import difflib
    _pb_init()
    archived = 0
    with _sql.connect(_PB_DB) as con:
        rows = con.execute(
            "SELECT id, signature, content, created_at FROM playbooks "
            "WHERE archived=0 ORDER BY created_at DESC").fetchall()
        seen: list[tuple[int, str, str]] = []  # (id, sig, content) — Neueste zuerst
        for pid, sig, content, _created in rows:
            dup_of = None
            for sid, ssig, scontent in seen:
                if sig == ssig:
                    dup_of = sid
                    break
                ratio = difflib.SequenceMatcher(
                    None, content[:2000], scontent[:2000]).ratio()
                if ratio > 0.85:
                    dup_of = sid
                    break
            if dup_of is not None:
                con.execute("UPDATE playbooks SET archived=1, updated_at=? WHERE id=?",
                            (_pb_now(), pid))
                archived += 1
            else:
                seen.append((pid, sig, content))
        con.commit()
    return (f"[kb_dedup] Pflege-Lauf fertig: {archived} Duplikat(e) archiviert, "
            f"{len(seen)} aktive Playbooks verbleiben. Nichts gelöscht (D19).")


@mcp.tool()
def kb_resolve_conflicts(signature: str = "") -> str:
    """Gedächtnis-Pflege: löst widersprüchliche Playbooks je Signatur auf (G2).

    Regel: die NEUESTE Version gewinnt, ältere werden als 'veraltet' archiviert
    (nie gelöscht, D19 — Original bleibt in der DB abrufbar).

    signature: nur diese Signatur prüfen (leer = alle)."""
    _pb_init()
    resolved = 0
    with _sql.connect(_PB_DB) as con:
        if signature.strip():
            sigs = [(signature.strip().lower(),)]
        else:
            sigs = con.execute(
                "SELECT DISTINCT signature FROM playbooks WHERE archived=0").fetchall()
        for (sig,) in sigs:
            rows = con.execute(
                "SELECT id FROM playbooks WHERE signature=? AND archived=0 "
                "ORDER BY created_at DESC", (sig,)).fetchall()
            for (old_id,) in rows[1:]:  # alles außer der neuesten
                con.execute("UPDATE playbooks SET archived=1, updated_at=? WHERE id=?",
                            (_pb_now(), old_id))
                resolved += 1
        con.commit()
    return (f"[kb_resolve_conflicts] {resolved} veraltete Version(en) archiviert — "
            f"je Signatur gewinnt die neueste. Nichts gelöscht (D19).")


@mcp.tool()
def kb_stats() -> str:
    """Status/Größe der Wissensbasis (Anzahl Dokumente, Chunks, Verarbeitung).
    Für: prüfen, ob/was in der Wissensbasis indexiert ist."""
    if not _KB:
        return "[Fehler: WEKNORA_KB_ID nicht gesetzt.]"
    import httpx

    try:
        r = httpx.get(f"{_BASE}/knowledge-bases/{_KB}", headers=_headers(), timeout=30)
    except httpx.ConnectError:
        return f"[Fehler: WeKnora nicht erreichbar unter {_BASE}.]"
    if r.status_code != 200:
        return f"[Fehler: WeKnora HTTP {r.status_code}: {r.text[:200]}]"
    d = (r.json().get("data") or {})
    caps = d.get("capabilities") or {}
    return (f"WISSENSBASIS '{d.get('name', '?')}':\n"
            f"  Dokumente: {d.get('knowledge_count', '?')}\n"
            f"  Chunks: {d.get('chunk_count', '?')}\n"
            f"  Verarbeitung läuft: {d.get('is_processing', '?')}\n"
            f"  Fähigkeiten: vector={caps.get('vector')} keyword={caps.get('keyword')} "
            f"(Hybrid={bool(caps.get('vector') and caps.get('keyword'))})")


if __name__ == "__main__":
    mcp.run()
