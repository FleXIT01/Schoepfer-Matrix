"""
quiz_mcp — Lern-Quiz aus der Wissensbasis (N8)
FastMCP-Server: Fragt Inhalte aus kb (Collection uni/tech) ab,
generiert Multiple-Choice- + offene Fragen, merkt sich Fehler in SQLite.

Tools:
  - quiz_start(topic, n_questions, collection) → Session-ID + erste Frage
  - quiz_answer(session_id, answer)            → Bewertung + nächste Frage / Abschluss
  - quiz_stats(topic)                          → Fehlerquoten je Thema
  - quiz_topics()                              → Alle bekannten Themen mit Statistik

Braucht: FastMCP, kb_search (läuft separat via kb-mcp), llm-mcp für Fragenerstellung
Start (stdio): python server.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("quiz")

_DB_PATH = Path(os.environ.get(
    "QUIZ_DB_PATH",
    r"n:\allinall\openclaw-workspace\state\quiz.db"
))

# ─── DB ───────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                topic       TEXT NOT NULL,
                collection  TEXT NOT NULL DEFAULT 'uni',
                questions   TEXT NOT NULL DEFAULT '[]',
                answers     TEXT NOT NULL DEFAULT '[]',
                current_q   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                topic       TEXT NOT NULL,
                collection  TEXT NOT NULL,
                question    TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                correct     INTEGER NOT NULL,
                explanation TEXT NOT NULL DEFAULT ''
            );
        """)

_init_db()


def _db() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _session_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _kb_search(query: str, top_k: int = 4) -> str:
    """Ruft kb-mcp über HTTP ab (falls WeKnora läuft), sonst leer."""
    import httpx
    base = os.environ.get("WEKNORA_BASE_URL", "http://localhost:8080/api/v1").rstrip("/")
    key = os.environ.get("WEKNORA_API_KEY", "")
    kb_id = os.environ.get("WEKNORA_KB_ID", "")
    if not kb_id:
        return ""
    try:
        r = httpx.request(
            "GET", f"{base}/knowledge-bases/{kb_id}/hybrid-search",
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            json={"query_text": query, "match_count": top_k,
                  "vector_threshold": 0.1, "keyword_threshold": 0.0},
            timeout=30,
        )
        data = r.json().get("data") or []
        return "\n\n".join(
            f"[{i+1}] {c.get('knowledge_title','?')}: {(c.get('content') or '')[:400]}"
            for i, c in enumerate(data[:top_k])
        )
    except Exception:
        return ""


def _llm_generate(prompt: str, max_tokens: int = 800) -> str:
    """Ruft Ollama (gpt-oss-32k) lokal ab für Fragenerstellung."""
    import httpx
    model = os.environ.get("QUIZ_MODEL", "gpt-oss:20b")
    try:
        r = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"num_predict": max_tokens, "temperature": 0.4}},
            timeout=120,
        )
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[LLM-Fehler: {e}]"


def _make_questions(topic: str, context: str, n: int) -> list[dict]:
    """Generiert n Fragen (Mix: Multiple-Choice + offen) via LLM."""
    prompt = (
        f"Du bist ein Prüfungs-Coach. Thema: '{topic}'.\n"
        f"Kontext aus der Wissensbasis:\n{context}\n\n"
        f"Erstelle genau {n} Prüfungsfragen zum Thema. Mix: "
        f"mind. {n//2} Multiple-Choice (4 Optionen, eine richtig), Rest offen.\n"
        f"Antworte NUR mit einem JSON-Array ohne weitere Erklärung:\n"
        f'[{{"type":"mc","q":"Frage?","opts":["A","B","C","D"],"ans":"A","exp":"Erkl."}},'
        f'{{"type":"open","q":"Frage?","ans":"Musterlösung","exp":"Erkl."}}]\n'
        f"JSON:"
    )
    raw = _llm_generate(prompt, max_tokens=1200)
    # JSON aus Antwort extrahieren
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start < 0 or end <= start:
        return []
    try:
        qs = json.loads(raw[start:end])
        # Validieren
        valid = []
        for q in qs:
            if not isinstance(q, dict) or "q" not in q or "ans" not in q:
                continue
            q.setdefault("type", "open")
            q.setdefault("opts", [])
            q.setdefault("exp", "")
            valid.append(q)
        return valid[:n]
    except json.JSONDecodeError:
        return []


def _format_question(q: dict, idx: int, total: int) -> str:
    lines = [f"Frage {idx}/{total}: {q['q']}"]
    if q.get("type") == "mc" and q.get("opts"):
        for opt in q["opts"]:
            lines.append(f"  {opt}")
        lines.append("(Antwort: A / B / C / D)")
    else:
        lines.append("(Offene Antwort)")
    return "\n".join(lines)


# ─── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def quiz_start(
    topic: str,
    n_questions: int = 5,
    collection: str = "uni",
) -> str:
    """Startet eine neue Quiz-Session zum angegebenen Thema.
    Sucht Kontext in der Wissensbasis (kb_search) und generiert Fragen per LLM.

    topic       = Lernthema, z.B. 'Stahlerzeugung', 'EGFR-Inhibitoren', 'Python async'
    n_questions = Anzahl Fragen (1–10, Standard 5)
    collection  = Wissensbasis-Collection (uni / tech / learnings)

    Gibt Session-ID + erste Frage zurück."""
    n = max(1, min(10, int(n_questions)))

    context = _kb_search(topic, top_k=5)
    if not context:
        context = f"Kein spezifischer Kontext in der Wissensbasis für '{topic}' gefunden. Allgemeinwissen nutzen."

    questions = _make_questions(topic, context, n)
    if not questions:
        return (
            f"[quiz_start] Konnte keine Fragen zum Thema '{topic}' generieren.\n"
            "Tipp: Stelle sicher, dass WeKnora läuft und Skripten zum Thema ingestiert sind."
        )

    sid = _session_id()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db() as c:
        c.execute(
            "INSERT INTO sessions (id, topic, collection, questions, answers, current_q, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, topic.strip(), collection.strip(), json.dumps(questions), "[]", 0, ts),
        )

    first_q = _format_question(questions[0], 1, len(questions))
    return (
        f"Quiz gestartet! Session-ID: {sid}\n"
        f"Thema: {topic} | {len(questions)} Fragen\n\n"
        f"{first_q}\n\n"
        f"Antworte mit: quiz_answer(session_id='{sid}', answer='<Deine Antwort>')"
    )


@mcp.tool()
def quiz_answer(session_id: str, answer: str) -> str:
    """Beantwortet die aktuelle Frage einer laufenden Quiz-Session.

    session_id = ID aus quiz_start
    answer     = Antwort (bei MC: 'A'/'B'/'C'/'D', bei offen: Freitext)

    Gibt Bewertung + nächste Frage (oder Abschlussbericht) zurück."""
    with _db() as c:
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return f"[quiz_answer] Session '{session_id}' nicht gefunden."

        questions = json.loads(row["questions"])
        answers_so_far = json.loads(row["answers"])
        idx = row["current_q"]

        if idx >= len(questions):
            return "[quiz_answer] Diese Session ist bereits abgeschlossen."

        q = questions[idx]
        user_ans = answer.strip()
        correct_ans = q["ans"].strip()

        # Bewertung
        if q.get("type") == "mc":
            # Vergleich: erster Buchstabe oder ganze Option
            ua_letter = user_ans[0].upper() if user_ans else ""
            ca_letter = correct_ans[0].upper() if correct_ans else ""
            is_correct = ua_letter == ca_letter
        else:
            # Offen: LLM-Bewertung
            eval_prompt = (
                f"Frage: {q['q']}\n"
                f"Musterlösung: {correct_ans}\n"
                f"Nutzer-Antwort: {user_ans}\n\n"
                "Ist die Nutzer-Antwort inhaltlich korrekt? Antworte NUR mit 'JA' oder 'NEIN'."
            )
            verdict = _llm_generate(eval_prompt, max_tokens=5).upper().strip()
            is_correct = verdict.startswith("J")

        explanation = q.get("exp", "")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Ergebnis speichern
        c.execute(
            "INSERT INTO results (ts, topic, collection, question, user_answer, correct, explanation) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, row["topic"], row["collection"], q["q"], user_ans, int(is_correct), explanation),
        )

        answers_so_far.append({"q_idx": idx, "answer": user_ans, "correct": is_correct})
        next_idx = idx + 1
        c.execute(
            "UPDATE sessions SET answers=?, current_q=? WHERE id=?",
            (json.dumps(answers_so_far), next_idx, session_id),
        )

        feedback = "Richtig!" if is_correct else f"Falsch. Richtig: {correct_ans}"
        if explanation:
            feedback += f"\nErklaerung: {explanation}"

        if next_idx >= len(questions):
            # Abschluss
            c.execute("UPDATE sessions SET finished_at=? WHERE id=?", (ts, session_id))
            n_correct = sum(1 for a in answers_so_far if a["correct"])
            pct = n_correct / len(questions) * 100
            grade = "Sehr gut" if pct >= 80 else "Gut" if pct >= 60 else "Wiederholen"
            return (
                f"{feedback}\n\n"
                f"=== Quiz abgeschlossen! ===\n"
                f"Ergebnis: {n_correct}/{len(questions)} ({pct:.0f}%) — {grade}\n"
                f"Tipp: quiz_stats(topic='{row['topic']}') fuer detaillierte Fehleranalyse."
            )

        next_q = _format_question(questions[next_idx], next_idx + 1, len(questions))
        return f"{feedback}\n\nWeiter:\n{next_q}"


@mcp.tool()
def quiz_stats(topic: str = "") -> str:
    """Zeigt Fehlerquoten und Schwachstellen-Analyse je Thema.
    Gut fuer: herausfinden, welche Bereiche wiederholt werden sollten.

    topic = Filter (leer = alle Themen)"""
    with _db() as c:
        if topic.strip():
            rows = c.execute(
                "SELECT topic, question, correct, COUNT(*) cnt FROM results "
                "WHERE topic LIKE ? GROUP BY topic, question ORDER BY correct ASC, cnt DESC",
                (f"%{topic.strip()}%",),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT topic, question, correct, COUNT(*) cnt FROM results "
                "GROUP BY topic, question ORDER BY topic, correct ASC, cnt DESC"
            ).fetchall()

    if not rows:
        return "Noch keine Quiz-Ergebnisse vorhanden. Starte mit quiz_start()."

    # Aggregieren
    from collections import defaultdict
    topic_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "wrong": 0, "wrong_q": []})
    for r in rows:
        td = topic_data[r["topic"]]
        td["total"] += r["cnt"]
        if not r["correct"]:
            td["wrong"] += r["cnt"]
            td["wrong_q"].append((r["question"][:80], r["cnt"]))

    lines = ["QUIZ-STATISTIKEN\n"]
    for t, d in sorted(topic_data.items()):
        pct_wrong = d["wrong"] / d["total"] * 100 if d["total"] else 0
        lines.append(f"Thema: {t}")
        lines.append(f"  Gesamt-Antworten: {d['total']}  Falsch: {d['wrong']} ({pct_wrong:.0f}%)")
        if d["wrong_q"]:
            lines.append("  Schwache Fragen (haeufig falsch):")
            for q_text, cnt in d["wrong_q"][:5]:
                lines.append(f"    [{cnt}x falsch] {q_text}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def quiz_topics() -> str:
    """Listet alle Themen auf, die bisher im Quiz bearbeitet wurden, mit Statistik."""
    with _db() as c:
        rows = c.execute(
            "SELECT topic, COUNT(*) sessions FROM sessions GROUP BY topic ORDER BY sessions DESC"
        ).fetchall()
        result_rows = c.execute(
            "SELECT topic, SUM(correct) ok, COUNT(*) total FROM results GROUP BY topic"
        ).fetchall()

    if not rows:
        return "Noch keine Quiz-Sessions. Starte mit quiz_start(topic='Dein Thema')."

    result_map = {r["topic"]: r for r in result_rows}
    lines = ["BEKANNTE QUIZ-THEMEN:\n"]
    for r in rows:
        t = r["topic"]
        res = result_map.get(t)
        if res and res["total"]:
            pct = res["ok"] / res["total"] * 100
            lines.append(f"  {t}: {r['sessions']} Session(s), {pct:.0f}% richtig ({res['total']} Antworten)")
        else:
            lines.append(f"  {t}: {r['sessions']} Session(s), noch keine Antworten")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
