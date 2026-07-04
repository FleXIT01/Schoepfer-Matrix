---
name: rag-optimize
description: "Wissensbasis-Pflege: Duplikate zusammenführen, Konflikte auflösen, Index-Gesundheit prüfen und berichten."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧹",
        "requires": { "mcp": ["kb", "status"] }
      }
  }
---

# RAG-Optimize — Wissensbasis pflegen

Trigger: `/rag-optimize`, „optimiere die Wissensbasis", „räum die Wissensbasis auf",
„RAG-Pflege", „Wissensbasis-Check".

## Ablauf (in dieser Reihenfolge)

### 1. Bestandsaufnahme

```
kb.kb_stats()
```
→ Anzahl Dokumente/Chunks notieren (Vorher-Stand für den Bericht).

### 2. Duplikate zusammenführen

```
kb.kb_dedup()
```
Archiviert doppelte Einträge (löscht NIE — D19-Regel).

### 3. Konflikte auflösen

```
kb.kb_resolve_conflicts()
```
Widersprüchliche/veraltete Playbooks werden markiert und archiviert.

### 4. Stichproben-Qualitätstest

Drei `kb.kb_search`-Abfragen zu Kernthemen des Nutzers ausführen
(z.B. aus den letzten Traces oder Briefing-Themen). Je Treffer prüfen:
- Kommt eine Antwort mit KONFIDENZ HOCH/MITTEL?
- Ist der Treffer inhaltlich passend zur Anfrage?

KONFIDENZ NIEDRIG bei einem Kernthema → als Lücke in den Bericht aufnehmen
(Kandidat für die Neugier-Schleife I4, aber NICHT automatisch recherchieren).

### 5. Bericht an den Nutzer

Kompakt melden: Dokumente vorher/nachher, Anzahl archivierter Duplikate/Konflikte,
Stichproben-Ergebnis, gefundene Lücken. KEINE Rückfragen nötig — der Skill ist
rein lesend/archivierend und immer erlaubt.

## Wann automatisch?

Sonntags im Rahmen der Gedächtnis-Pflege (V3:G2, neben dem Retro) — sonst
nur auf Zuruf. Ergebnis fließt ins nächste Morgenbriefing.
