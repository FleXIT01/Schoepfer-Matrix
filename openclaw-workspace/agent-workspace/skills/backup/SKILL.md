---
name: backup
description: "Sofort-Backup der ganzen Schöpfer-Matrix (state, MCP-Server, Skripte, Docker-Volumes) nach I:\\backup\\matrix."
metadata:
  {
    "openclaw":
      {
        "emoji": "💾",
        "requires": { "mcp": ["assistant"] }
      }
  }
---

# Backup-Skill — Sofort-Sicherung per Chat

Trigger: `/backup`, „mach ein Backup", „Backup jetzt", „sichere alles",
„sicherung machen", „backup starten".

## Ablauf

### 1. Backup starten (EIN Tool-Aufruf, nichts selbst orchestrieren)

```
assistant.backup_now()
```

Das Tool führt intern `n:\allinall\backup.cmd` aus (state + mcp-servers +
Startskripte + WeKnora-Docker-Volumes → `I:\backup\matrix\<zeitstempel>`)
und wartet bis zum Ende (1–2 Minuten). KEIN GO-Gate nötig — Backup ist
lesend/lokal und immer erlaubt.

### 2. Ergebnis melden

- Antwort beginnt mit `[OK]` → kurz bestätigen: Backup-Pfad + was gesichert wurde.
- Antwort beginnt mit `[FEHLER]` → Fehlertext wörtlich weitergeben und auf
  `n:\allinall\openclaw-workspace\output\backup.log` verweisen.
  Häufigste Ursache: Laufwerk `I:` nicht eingebunden.

## Hinweise

- Backups älter als 14 Tage räumt backup.cmd selbst auf (Retention).
- Backup-Alter jederzeit prüfbar: der Watchdog alarmiert automatisch,
  wenn das jüngste Backup älter als 3 Tage ist.
- NICHT mit `assistant.run_command` nachbauen (120s-Timeout zu knapp) —
  immer `assistant.backup_now` verwenden.
