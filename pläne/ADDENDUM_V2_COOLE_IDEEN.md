# IDEEN-ADDENDUM ZU MASTERPLAN V2 — „Was jetzt noch cool wär"
## Sechs große Ideen · drei Goodies · der konkrete nächste Schritt

```
Erstellt:  2026-06-11
Basis:     MASTERPLAN v1 (Phasen 0–4 fertig & end-to-end bewiesen)
           + MASTERPLAN V2 (Phasen 6–10 geplant)
Regel:     KEINE dieser Ideen vor der Phase-6-Sicherung (Backups, Gates,
           Kosten-Limit). Jede Idee dockt an bestehende V-/N-Punkte an —
           nichts hier ersetzt V2, alles baut darauf auf.

UMSETZUNGSSTATUS (Stand 2026-06-13): ALLE 9 ITEMS VOLLSTÄNDIG UMGESETZT ✅
  I1 ✅  I2 ✅  I3 ✅  I4 ✅  I5 ✅  I6 ✅  G1 ✅  G2 ✅  G3 ✅
```

---

## 0. Kurzfassung

Sechs Ideen — alle aus Teilen gebaut, die schon existieren oder in V2 geplant sind:

| # | Idee | braucht |
|---|------|---------|
| I1 | Matrix überall (globaler Hotkey) | N4 (HTTP-Eingang) |
| I2 | Die Fabrik mit Augen (visuelles Gate) | browser + qwen3-vl |
| I3 | Rat der Modelle (Zweitmeinung) | nur llm-mcp (+V9) |
| I4 | Neugier-Schleife (lernt selbstständig) | N7 + V12 |
| I5 | Paper-Podcast (Berichte als Audio) | N2 (Voice) |
| I6 | Issue→PR-Pipeline (eigenes „Claude Code") | V6 + GitHub-Token |

Schnellster Einstieg: **I3** (ein neues Tool in llm-mcp, sofort nützlich).
Wichtigster Schritt VOR allem anderen: **Tag-1-Paket aus V2 (BACKUPS!)** — siehe §4.

---

## 1. Die sechs großen Ideen

### I1 — Matrix überall: globaler Hotkey  ✅ UMGESETZT
**Was:** Text in IRGENDEINEM Programm markieren, Hotkey drücken → Antwort der Matrix
als Popup und/oder in der Zwischenablage. Die Matrix sitzt damit in jeder App,
nicht mehr nur in Telegram.

**Zutaten:** N4 (HTTP-Eingang am Gateway / Mini-FastAPI mit Token) + AutoHotkey v2.

**Bauplan:**
1. N4 umsetzen: `POST /turn {text, preset}` → Antwort als JSON.
2. AHK-Script (~50 Zeilen): Clipboard sichern, `^c` senden, ClipWait, HTTP-POST
   an `127.0.0.1:<port>` mit Token-Header, Antwort als Tooltip/GUI + optional
   ins Clipboard.
3. Hotkey-Presets: `Win+Y` erklären · `Win+U` umformulieren · `Win+I` übersetzen ·
   `Win+O` freie Frage (InputBox).

**Sicherheit:** Endpoint NUR an 127.0.0.1 binden + Token. Kein LAN, kein Internet.
**Aufwand:** 1 Abend (nach N4).
**Beweis:** Markierter Text in beliebiger App → Hotkey → Antwort < 10 s im Popup.

### I2 — Die Fabrik mit Augen: visuelles Completion-Gate  ✅ UMGESETZT
**Was:** factory baut eine Web-App, die Matrix SCHAUT sie sich selbst an: Browser
öffnet die App, Screenshot, qwen3-vl bewertet gegen die Spezifikation („Button
fehlt", „Layout bricht"), Fixer-Runde. Das Completion-Gate-Prinzip aus v1 bekommt
Augen.

**Zutaten:** factory-mcp, native browser-Extension, qwen3-vl im llm-Routing,
review-mcp, planner-mcp (VRAM!).

**Bauplan:**
1. factory: gebaute Web-Apps auf freiem Port lokal starten.
2. browser: Seite öffnen + Screenshot ziehen.
3. Neues Tool `visual_review(screenshot, spec)` → Findings-Liste (in review-mcp
   oder llm-mcp, geroutet auf qwen3-vl).
4. build-bot-Skill erweitern: max. 3 visuelle Fix-Iterationen, Abschlussbericht
   mit Vorher/Nachher-Screenshot.

**VRAM:** `planner-mcp.can_load` VOR qwen3-vl fragen (Modelltausch 20b ↔ vl — es
passt nur EIN großes Modell in die 16 GB).
**Aufwand:** 2–3 Abende.
**Beweis:** Absichtlich kaputtes CSS (Spec-Verstoß) → System findet und repariert
es OHNE menschlichen Hinweis.

### I3 — Rat der Modelle: eingebaute Zweitmeinung  ✅ UMGESETZT
**Was:** Bei wichtigen Fragen antworten gpt-oss (lokal) und cloud_cheap (DeepSeek)
UNABHÄNGIG voneinander; ein Richter führt zusammen und markiert Widersprüche
EXPLIZIT. Killt Single-Model-Blindspots.

**Zutaten:** llm-mcp (vorhanden), V9-Kosten-Ledger als Bremse.

**Bauplan:**
1. Neues llm-mcp-Tool `council(prompt, judge="local|reason")`: parallel lokal +
   cloud_cheap; Richter (Default lokal, für Wichtiges cloud_reason) liefert:
   Konsens, WIDERSPRÜCHE als Liste, Empfehlung.
2. Skill „zweitmeinung" (Trigger: „wichtige Entscheidung", „sicher gehen",
   „Zweitmeinung", „vergleiche Antworten").

**Kosten:** Centbereich pro Frage; zählt ins V9-Tageslimit.
**Aufwand:** 1 Abend. Geht SOFORT nach Quick-Win Tag 4 (Ledger).
**Beweis:** Frage mit bekanntem Lokal-Blindspot → Council markiert den Widerspruch
korrekt statt ihn zu verschlucken.
**Bonus:** Starkes Kunden-Demo-Stück: „eingebaute Zweitmeinung".

### I4 — Neugier-Schleife: das System lernt selbstständig  ✅ UMGESETZT
**Was:** Liefert kb_search nichts Brauchbares, legt die Matrix SELBST einen
Research-Job in die Queue und ingestiert das Ergebnis in die learnings-Collection.
Beim zweiten Mal kennt sie die Antwort. Die Lern-Schleife (v1 §5.8 / V12) wird
selbstverstärkend.

**Zutaten:** kb-mcp (+ `kb_ingest` aus V12), jobs-mcp (N7), research-mcp.

**Bauplan:**
1. kb_search gibt Score/Konfidenz zurück.
2. Regel (AGENTS.md + dünner Skill): Score < Schwelle UND Thema relevant/Watchlist
   → `jobs.submit(deep_research)` + Notiz an den User („Lücke erkannt, recherchiere
   im Hintergrund").
3. Job-Ende → `kb_ingest(bericht, collection="learnings", meta={query, datum, quelle})`.

**Schutz:** Max. 3 Auto-Jobs/Tag; Recherche nur lokal/gratis (SearXNG/DDG); NIE
Cloud ohne GO. Sonst recherchiert sich das System in Schleifen.
**Aufwand:** 1–2 Abende (nach N7 + V12).
**Beweis:** Gleiche Frage zweimal: Tag 1 = Lücke + Job, Tag 2 = direkte Antwort
mit Quelle „learnings".

### I5 — Paper-Podcast: Berichte zum Anhören  ✅ UMGESETZT
**Was:** deep-research-Bericht oder 1–3 PDFs → ~5-Minuten-Audio → kommt als
Telegram-Sprachnachricht aufs Handy. Berichte hören statt lesen (Weg, Sport,
Abwasch).

**Zutaten:** research-mcp / pdf-mcp, voice-mcp (N2, speak), telegram_send.

**Bauplan — Skill „podcast":**
1. Inhalt holen (Thema → deep_research; PDFs → pdf-mcp).
2. Hirn schreibt SPRECHTEXT: gesprochene Sprache, keine Aufzählungen,
   ~750–800 Wörter (≈ 5 min).
3. `voice.speak` (Piper) → ogg → telegram_send als Sprachnachricht.

**Kür:** Zwei Piper-Stimmen als Dialog (Host fragt, Experte antwortet) — hörbar
angenehmer als Monolog.
**Aufwand:** 1 Nachmittag (nach N2).
**Beweis:** PDF rein → 5-Min-Audio aufs Handy, beim Spazieren verständlich.

### I6 — Issue→PR-Pipeline: das eigene „Claude Code"  ✅ UMGESETZT
**Was:** „Matrix, fix Issue #4 in `<repo>`" → Fix wird gebaut, hart reviewt, als
Branch gepusht und als Pull Request geöffnet. Eigenes Coding-Agent-Produkt aus
eigenen Teilen.

**Zutaten:** factory-mcp, review-mcp, git + gh CLI, GitHub-Token (fein-granular,
NUR eigene Repos), V6-Gate.

**Bauplan — Skill „repo-fix":**
1. git clone/pull in die Sandbox.
2. Issue-Text via gh/GitHub-API holen.
3. factory-/Coding-Schritt baut Fix (+ Tests, wo möglich).
4. review-mcp-Gate MUSS grün sein.
5. Branch `fix/issue-N` anlegen, committen.
6. **V6-APPROVAL-GATE vor jedem Push:** „PENDING: will Branch X pushen + PR
   öffnen — GO?"
7. `gh pr create`, Review-Bericht in den PR-Text.

**Sicherheit:** Token minimal-scope (nur eigene Repos), NIE force-push, Push
IMMER hinter GO.
**Testobjekt:** spiel-git-devsimulator (SWK-SIMULATOR).
**Aufwand:** 2 Abende (nach Quick-Win Tag 5 / V6).
**Beweis:** Issue anlegen → EINE Telegram-Zeile → fertiger PR mit grünem
Review-Bericht online.
**Business:** Identischer Ablauf später am Kundenrepo vorführbar.

---

## 2. Drei kleinere Goodies

- **G1 — GO/NO als Inline-Buttons:** ✅ UMGESETZT — mail_mcp sendet bei PENDING automatisch GO/NO-Buttons; tg_callback_poll.py führt bestätigte Aktionen aus.
- **G2 — factory-Sandbox in Docker:** ✅ UMGESETZT — factory_mcp/build_bot + verify_package laufen in python:3.12-slim ohne Netzwerk.
- **G3 — Build in public:** ✅ UMGESETZT — wiki_mcp.build_in_public(topic) + list_article_topics(); Artikel nach n:\allinall\articles\.

---

## 3. Reihenfolge & Andockpunkte

| Idee | braucht | frühester Zeitpunkt | Aufwand |
|------|---------|---------------------|---------|
| I3 | llm-mcp + V9 (Deckel) | sofort nach Quick-Win Tag 4 | 1 Abend |
| I1 | N4 (HTTP-Eingang) | nach Phase 6 (N4 vorziehbar) | 1 Abend |
| I6 | V6 + GitHub-Token | nach Quick-Win Tag 5 | 2 Abende |
| I5 | N2 (Voice) | Phase 8 | 1 Nachmittag |
| I2 | N3 (Vision stabil) | Phase 8/9 | 2–3 Abende |
| I4 | N7 + V12 | Phase 10 | 1–2 Abende |

**Empfohlene Kette:**
Tag-1-Paket (§4) → V2-Quick-Wins (7 Tage) → I3 → N4 vorziehen + I1 → I6 →
Phase 8 (N1/N2/N3) → I5 → I2 → Phase 10 → I4.

---

## 4. Der konkrete nächste Schritt: Tag-1-Paket (aus V2, VOR allen Ideen)

Inhalt des Pakets (wird fertig geliefert, einbaufertig):

- **a) backup.cmd** — robocopy von openclaw-workspace, mcp-servers, AGENTS.md,
  *.cmd auf die Zielplatte + Docker-Volume-Dumps (Qdrant/ParadeDB) per
  `docker run --rm -v <vol>:/d -v <ziel>:/b alpine tar czf /b/<vol>_DATUM.tgz -C /d .`
  + Scheduled Task (nächtlich) + RESTORE-Probe-Anleitung.
- **b) watchdog.cmd** — 5-min-Task: Ollama (11434), Gateway, WeKnora, Reranker
  pingen; bei Ausfall Neustart (gateway.cmd-Logik) + Telegram-Alarm.
- **c) gate_middleware.py** — FastMCP-Decorator `@requires_go` für email_send /
  Shell / Push: legt Pending-Eintrag (SQLite) an, antwortet „PENDING `<id>` —
  GO `<id>` zum Ausführen", zweiter Aufruf mit go_id führt aus.

**Dafür wird gebraucht (eine Nachricht genügt):**
1. Ausgabe von `docker volume ls` (echte Namen der Qdrant/ParadeDB-Volumes)
2. Backup-Zielpfad (zweite Platte, z. B. `d:\backup\matrix`)
3. Gateway-Port (für watchdog + später N4)

---

## 5. Ehrliche Abgrenzung

- NICHTS davon vor gesichertem State (V5). Ein Plattencrash macht jede coole
  Idee wertlos.
- I4 nur mit Tagesdeckel — sonst Endlos-Recherche-Schleifen.
- I6 niemals ohne Review-Gate UND GO-Gate; Token minimal-scope.
- I2 ist Kür: beeindruckend, aber erst wenn Vision (N3) im Alltag stabil ist.
- Keine neuen Dauer-Dienste: alles dockt an bestehende MCP-Server und Skills an.
  Die Architektur bleibt die aus v1/V2.

```
================================================================================
  ENDE ADDENDUM — Reihenfolge bestätigen, dann Tag-1-Paket anfordern (§4)
================================================================================
```
