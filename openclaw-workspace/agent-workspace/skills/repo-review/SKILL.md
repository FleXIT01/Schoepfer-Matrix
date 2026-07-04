---
name: repo-review
description: "Ein Code-Repository oder eine Datei prüfen: Syntax, Sicherheit (eval/exec/os.system), Smells, Komplexität — strukturierte Findings mit Schweregrad."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔍",
        "requires": { "mcp": ["review"] }
      }
  }
---

# Repo Review — Code-Qualitäts-Gate

Trigger: „reviewe mein Repo/Datei", „prüfe den Code", „ist dieser Code sicher?".
Auch als Pflicht-Gate nach jeder Code-Generierung (vom `build-bot`/`supervisor`).

## Ablauf

1. UMFANG bestimmen: ganze Datei (`review.review_file(path)`), ein Snippet
   (`review.review_code(code)`) oder ein ganzes Projekt (`review.scan_repo(path)`).

2. PRÜFEN: Tool aufrufen. Es liefert Findings mit Schweregrad
   (🔴 critical, 🟠 high, 🟡 medium, ⚪ low) und ein Gesamturteil
   (BESTANDEN / NICHT BESTANDEN).

3. BERICHTEN: Findings nach Schweregrad ordnen; zu jedem kritischen/hohen Punkt
   einen konkreten Fix vorschlagen.

4. GATE: Gibt es kritische Findings oder Syntaxfehler -> „NICHT BESTANDEN".
   In automatischen Pipelines (supervisor/build-bot) darf der Prozess dann NICHT
   als erfolgreich gelten, bis die kritischen Punkte behoben sind.
