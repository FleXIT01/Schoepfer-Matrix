"""Beweis-Tests für V3 Phase 12+13 (G1/G2/F2) — ruft die Tool-Funktionen direkt.
Phase-11-Beweis liegt im Selbsttest von resilience.py (alle 8 grün).
"""
import sys
import sqlite3
from pathlib import Path

MCP = Path(r"n:\allinall\mcp-servers")

# ── G1/G2: Playbooks + Hygiene ──────────────────────────────────────────────────
sys.path.insert(0, str(MCP / "kb_mcp"))
import server as kb  # noqa: E402

print("G1 — Playbooks:")
r = kb.playbook_save("test-proof+python", "Proof-Lauf", "## Schritte\n1. A\n2. B")
assert "gespeichert" in r, r
r = kb.playbook_lookup("test-proof+python")
assert "PLAYBOOK" in r and "1. A" in r, r
print("  ok: save + exakter Lookup")

r = kb.playbook_lookup("test-proof+java")        # Teilwort-Match (test-proof)
assert "PLAYBOOK" in r, r
print("  ok: Teilwort-Match findet verwandtes Playbook")

# Konflikt: zweite Version derselben Signatur → alte wird archiviert
kb.playbook_save("test-proof+python", "Proof v2", "## Schritte\n1. NEU")
r = kb.playbook_lookup("test-proof+python")
assert "NEU" in r and "1. A" not in r, r
print("  ok: neuere Version gewinnt, alte archiviert (nie gelöscht)")

print("G2 — Hygiene:")
kb.playbook_save("test-dup+x", "Dup A", "Gleicher Inhalt " * 50)
kb.playbook_save("test-dup+y", "Dup B", "Gleicher Inhalt " * 50)   # >85% ähnlich
r = kb.kb_dedup()
assert "archiviert" in r, r
print(f"  ok: {r}")
r = kb.kb_resolve_conflicts()
assert "[kb_resolve_conflicts]" in r, r
print(f"  ok: {r}")

# Aufräumen: Test-Playbooks archivieren (D19-konform, kein DELETE)
with sqlite3.connect(MCP / "kb_mcp" / "playbooks.db") as con:
    con.execute("UPDATE playbooks SET archived=1 WHERE signature LIKE 'test-%'")
    con.commit()

# ── F2: Empirisches Routing ─────────────────────────────────────────────────────
sys.path.insert(0, str(MCP / "llm_mcp"))
del sys.modules["server"]
import server as llm  # noqa: E402

print("F2 — Empirisches Routing:")
# Kunst-Daten: für 'reasoning' ist qwen2.5:7b nachweislich besser als gpt-oss
llm._routing_init()
with sqlite3.connect(llm._ROUTING_DB) as con:
    con.execute("DELETE FROM runs WHERE kind='proof_reasoning'")
    for _ in range(25):
        con.execute("INSERT INTO runs (ts,kind,model,ok,latency,cost_usd) "
                    "VALUES ('2026-06-12','proof_reasoning','qwen2.5:7b',1,2.0,0)")
    for _ in range(25):
        con.execute("INSERT INTO runs (ts,kind,model,ok,latency,cost_usd) "
                    "VALUES ('2026-06-12','proof_reasoning','gpt-oss:20b',0,9.0,0)")
    con.commit()

best = llm._empirical_best("proof_reasoning")
assert best and best[0] == "qwen2.5:7b", best
print(f"  ok: Empirie wählt belegt bestes Modell: {best[0]} "
      f"({best[1]['success']*100:.0f}% vs. 0%) — Handregel überschrieben")

# Unter der D18-Schwelle: keine Empirie (Kaltstart-Schutz)
with sqlite3.connect(llm._ROUTING_DB) as con:
    con.execute("DELETE FROM runs WHERE kind='proof_thin'")
    for _ in range(5):
        con.execute("INSERT INTO runs (ts,kind,model,ok,latency,cost_usd) "
                    "VALUES ('2026-06-12','proof_thin','x',1,1.0,0)")
    con.commit()
assert llm._empirical_best("proof_thin") is None
print(f"  ok: unter {llm._ROUTING_MIN_RUNS} Läufen (D18) bleibt die Handregel (Kaltstart-Schutz)")

r = llm.routing_stats()
assert "proof_reasoning" in r
print("  ok: routing_stats zeigt die Aggregat-Daten")

# Proof-Daten wieder raus
with sqlite3.connect(llm._ROUTING_DB) as con:
    con.execute("DELETE FROM runs WHERE kind LIKE 'proof_%'")
    con.commit()

print("\nALLE V3-BEWEISE GRÜN (G1, G2, F2). F1-Mechanik: shadow.py list/apply/rollback testbar,")
print("Schatten-Lauf braucht laufende Eval-Suite (Gateway).")
