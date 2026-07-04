# Roadmap & Architektur-Entscheidungen

Bewertung externer Verbesserungsvorschläge (Juli 2026) — was umgesetzt ist,
was geplant ist und was **bewusst nicht** gemacht wird (mit Begründung).

## ✅ Umgesetzt

| Vorschlag | Umsetzung |
|---|---|
| Feingranulares Permission-Scoping | Webhook-**Host-Allowlist** in `hook_mcp` (server-seitig erzwungen, `hook_allowlist_add` nur auf Nutzer-Zuruf) — ergänzt die bestehenden GO/TOTP-Gates (mail, github, browser) |
| LLM-as-a-Judge im Eval | `expect_judge:`-Checks in `eval/golden.py` — semantische Bewertung (Stil, Verständlichkeit, Korrektheit) mit dem lokalen Modell, temp 0 + Seed → deterministisch wie die restliche Suite |
| Einheitliches CLI | `matrix.py` (`up/stop/status/eval/backup/briefing/retro/budget/logs`) — stdlib-only, delegiert an die getesteten Skripte statt Logik zu duplizieren |
| Skill RAG-Pflege | `skills/rag-optimize` — nutzt vorhandene `kb_dedup`/`kb_resolve_conflicts`/`kb_stats` + Stichproben-Qualitätstest |
| Skill API-Integration | `skills/api-integrate` — Doku lesen → MCP-Server aus `mcp-servers/_template_mcp/` generieren → lokal testen → **GO-Gate** → registrieren. Nie ohne Freigabe. |

## 🟡 Teilweise vorhanden (kein Neubau nötig)

- **Critic-Reflection-Loop / Multi-Agent-Debate:** existiert als `llm.council`
  (lokal + Cloud antworten unabhängig, Richter markiert Konsens/Widersprüche)
  und `review.review_code` vor jedem Commit im GitHub-Workflow.
- **Zustands-Serialisierung bei Abstürzen:** `resilience.py` R4 liefert
  Checkpoint/Resume für Langläufer (`run_steps`); Circuit-Breaker + Idempotenz
  decken die häufigsten Fehlerklassen ab. Eine volle State-Machine lohnt erst,
  wenn mehrstufige Workflows regelmäßig scheitern — bisher nicht der Fall
  (Golden-Suite überwacht genau das).

## ❌ Bewusst nicht (mit Begründung)

- **State-Machine für `orchestrator.py` / Debate für `fixer.py`/`coder.py`:**
  Diese Dateien gehören zur **Legacy-Architektur** (`bot1/`, Vor-OpenClaw).
  Das lebende System orchestriert über OpenClaw + MCP; Legacy-Code wird nicht
  weiter ausgebaut.
- **Firecracker-Micro-VMs:** Firecracker braucht KVM (Linux). Auf diesem
  Windows-Host wäre das ein WSL2/Hyper-V-Großumbau — und er widerspräche dem
  Kernzweck: Der Assistent soll *diesen* PC direkt bedienen (Screenshots,
  Apps, Dateien). Risiko wird stattdessen über Gates, Allowlists, Audit-Log
  und Not-Aus gesteuert.
- **Voll-Containerisierung der Matrix:** Ollama-GPU, ComfyUI, Task-Scheduler,
  Bildschirm-/Browser-Steuerung sind host-gebunden. Docker bleibt für die
  passenden Teile (WeKnora-RAG, SearXNG, n8n). Eine Linux-Server-Variante
  wäre ein eigenes Projekt, kein Feature.
- **API-Mocks für die Golden-Suite:** Die Suite prüft **Tool-Wahl** — Tools
  werden dabei gar nicht ausgeführt, es entstehen keine API-Kosten/Rate-Limits.
  Mocks würden Aufwand kosten, ohne die Messung zu verbessern. (Für die
  wenigen Live-Integrationstests gilt: sparsam, mit echten Endpunkten.)

## 🔭 Später vielleicht

- Judge-Zweitmodell (z. B. qwen2.5:7b) statt Selbstbewertung, wenn sich
  systematische Selbst-Milde zeigt.
- `matrix.py` um `matrix doctor` erweitern (Diagnose-Sammlung für Bug-Reports).
- Linux-Portierung als Community-Beitrag, falls das Repo Anklang findet.
