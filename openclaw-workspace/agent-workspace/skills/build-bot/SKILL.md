---
name: build-bot
description: "Aus einer Spezifikation einen vollständigen, in einer Sandbox VERIFIZIERTEN Bot/Agenten generieren (Architect→Coder→Gates→Fixer) und prüfen."
metadata:
  {
    "openclaw":
      {
        "emoji": "🏭",
        "requires": { "mcp": ["factory", "review"] }
      }
  }
---

# Build Bot — verifizierte Software-Fabrik

Trigger: „baue einen Bot/Agenten", „generiere ein Programm für …", „erstelle eine
App, die …". Nutzt den `factory`-MCP (echte Sandbox-Verifikation, die ein freier
Coding-Agent so nicht hat) + `review`-MCP als Gate.

## Ablauf

1. SPEZIFIKATION schärfen: Name, Zweck (description), System-Prompt, erste Nachricht.
   Bei unklaren Anforderungen kurz rückfragen (1 Frage).

2. FÄHIGKEITEN sichten: `factory.list_capabilities()` zeigt, welche Bausteine
   (Tools) der Bot bekommen kann (z.B. web_fetch, arxiv_search, chembl_search,
   generate_image). Passende für den Zweck wählen.

3. BAUEN: `factory.build_bot(name, description, system_prompt, first_message)`.
   Das durchläuft Architect → Coder → Import/Smoke/Tool-Gates → Fixer und schreibt
   ein lauffähiges Paket + BUILD_REPORT.md. (Benötigt laufendes Ollama.)

4. VERIFIZIEREN (Gate, Pflicht):
   - `factory.verify_package(path)` — Import-Gate des erzeugten Pakets
   - `review.scan_repo(path)` — statische Qualitäts-/Sicherheitsprüfung
   Bei „NICHT BESTANDEN": die gemeldeten Punkte beheben (erneut build/fix) und
   erneut prüfen. Erst bei grünem Gate als fertig melden.

5. ÜBERGEBEN: Pfad zum Paket + Kurzfassung des BUILD_REPORT zurückgeben.
   Niemals Erfolg behaupten, wenn verify_package fehlschlug.
