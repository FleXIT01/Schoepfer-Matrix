---
name: repo-wiki
description: "Ein Code-Repository automatisch in eine Architektur-Doku / ein Wiki verwandeln (Struktur, Komponenten, Datenfluss)."
metadata:
  {
    "openclaw":
      {
        "emoji": "📚",
        "requires": { "mcp": ["wiki"] }
      }
  }
---

# Repo Wiki — Repository automatisch dokumentieren

Trigger: „dokumentiere das Repo …", „erkläre mir die Architektur von …",
„mach ein Wiki/README für …".

Alles lokal über das `wiki`-MCP (AST-Scan + Modell), kein Cloud-Key nötig.

## Ablauf

1. ÜBERBLICK: `wiki.repo_tree(repo_path)` → schnelle Struktur/Sprachen-Übersicht
   (ohne Modell), um den Umfang zu sehen.
2. DOKU: `wiki.document_repo(repo_path, focus="")` → fertige Markdown-Architektur-Doku
   (Zweck, Hauptkomponenten, Datenfluss, wichtige Module, Einstiegspunkte, Tech-Stack).
3. Bei großen Repos `focus` setzen (z.B. „Datenfluss" oder „API"), um gezielter zu sein.
4. Auf Wunsch das Ergebnis als `ARCHITEKTUR.md` ins Repo schreiben und die Existenz
   danach prüfen (keine Halluzination melden).

## Hinweis
Für tiefere Code-Qualität kombiniere mit `review.scan_repo` (Findings) — Doku + Review
ergeben zusammen ein gutes Bild eines fremden Repos.
