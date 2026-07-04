---
name: retro
description: "Wochen-Retrospektive: analysiert Traces + Eval-Ergebnisse der letzten 7 Tage und sendet Top-3-Verbesserungsvorschläge per Telegram. Läuft automatisch jeden Sonntag 20:00 via Scheduled Task."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔁",
        "requires": { "mcp": ["trace", "status"] }
      }
  }
---

# Retro — Wochen-Retrospektive

Trigger: „starte die Retro", „wöchentliche Retro jetzt", „was lief diese Woche gut/schlecht".
Automatisch: Jeden Sonntag 20:00 via `SchoepferMatrix-Retro` Task (ruft `retro.cmd` → `retro.py`).

## Was die Retro macht

1. Liest `trace.db` (letzte 7 Tage): Turms, Fehlerrate, Kosten, Top-Tools, Fehler-Details.
2. Startet den Eval-Runner (`eval/runner.py --no-telegram`) und sammelt Testergebnisse.
3. Schickt beides an das lokale LLM (gpt-oss:20b) → Top-3 konkrete Verbesserungsvorschläge.
4. Sendet die Zusammenfassung per Telegram + schreibt ins Logfile (`openclaw-workspace/output/retro.log`).

## Manuell auslösen

Wenn der Nutzer „starte Retro" sagt:

```
Rufe direkt auf: C:\Python314\python.exe n:\allinall\retro.py
```

Oder informiere den Nutzer: „Die Retro läuft automatisch jeden Sonntag 20:00. Soll ich sie jetzt manuell starten?"

## Ergebnisse nutzen

Die Top-3-Vorschläge sind VORSCHLÄGE — keine automatischen Änderungen.
Alle Umsetzungen NUR nach explizitem GO des Nutzers.
Für komplexe Änderungen den `skill-creator`-Skill konsultieren.
