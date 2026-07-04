---
name: neugier
description: "Neugier-Schleife: erkennt Wissenslücken in kb_search und stellt automatisch einen Recherche-Job in die Queue — das System lernt selbstständig dazu. Max. 3 Auto-Jobs/Tag als Schutz."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔍",
        "requires": { "mcp": ["kb", "jobs", "research"] }
      }
  }
---

# Neugier-Schleife (I4)

**Automatisch:** Tritt in Kraft wenn `kb_search` `KONFIDENZ: NIEDRIG` oder
`KONFIDENZ: KEINE_TREFFER` zurückgibt.

**Manuell:** Trigger „lerne über …", „ingestiere das", „speichere das in der Wissensbasis".

## Ablauf (automatisch bei kb_search-Lücke)

**Regel:** Nur ausführen wenn das Thema für den Nutzer relevant ist und KEIN
trivialer Smalltalk (Namen, Witze, persönliche Meinungen etc.)

1. KONTINGENT PRÜFEN:
   - `jobs.auto_research_quota()` → ist Kapazität frei (< 3 Auto-Jobs heute)?
   - Wenn NEIN: Nutzer informieren, kein Auto-Job einreichen.

2. JOB EINREICHEN (wenn frei):
   - `jobs.job_submit('[AUTO] deep_research: <query>', priority=7)` → Job-ID
   - Nutzer kurz informieren: „Ich habe eine Wissenslücke erkannt und stelle eine
     Hintergrundrecherche zu ‹Thema› in die Queue (läuft im Hintergrund)."

3. JOB AUSFÜHREN (sofort oder bei nächster Gelegenheit):
   - `jobs.job_start(id)` → Status running
   - `research.deep_research(query)` → Bericht
   - `kb.kb_ingest(bericht, title=query)` → in Wissensbasis einpflegen
   - `jobs.job_complete(id, zusammenfassung)` → sendet Telegram-Alarm

4. NÄCHSTES MAL: gleiche Frage → direkte Antwort aus kb_search, kein Auto-Job mehr.

## Schutzregeln (I4)

- **Max. 3 Auto-Jobs pro Tag** — immer `auto_research_quota()` prüfen.
- **Nur kostenlose Quellen:** SearXNG/DDG/Web — niemals Cloud ohne GO des Nutzers.
- **Kein Auto-Research** für: persönliche Meinungsfragen, Smalltalk, reine Rechenaufgaben.
- Auto-Jobs im Hintergrund — der Chat bleibt responsive.

## Beispiele wann NICHT Auto-Research

- „Was denkst du über X?" → Meinungsfrage, kein Faktum
- „Was ist 2+2?" → kein Wissensbasis-Thema
- „Wie heißt du?" → Smalltalk

## Manuell ingestieren

Wenn der Nutzer sagt „merk dir das" / „speichere das in der Wissensbasis":
- `kb.kb_ingest(text, title)` direkt aufrufen
- Kein auto_research_quota-Check nötig (manuell ≠ automatisch)
