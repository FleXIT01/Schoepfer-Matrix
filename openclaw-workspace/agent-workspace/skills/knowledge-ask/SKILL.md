---
name: knowledge-ask
description: "Fragen aus dem lokalen Lern-Korpus beantworten (Architektur, Roadmaps, Coding-Wissen, APIs) — RAG über die indexierten Wissens-Repos."
metadata:
  {
    "openclaw":
      {
        "emoji": "📚",
        "requires": { "config": ["skills.entries.knowledge-ask.enabled"] }
      }
  }
---

# Knowledge Ask — Wissen aus dem Korpus

Trigger: „wie entwerfe ich …", „erklär mir das Konzept …", „welche API für …",
„Roadmap für …". Greift auf die in eine Wissensbasis (MaxKB/WeKnora) indexierten
Repos zu — siehe `knowledge-ingest`.

## Korpus (indexierte Repos)

- system-design-primer ...... Architektur & Skalierung (für PLAN-Phasen)
- developer-roadmap ......... Lernpfade / Technologie-Entscheidungen
- public-apis ............... API-Katalog (für CODE-Phasen)
- build-your-own-x .......... Implementierungs-Vorlagen
- coding-interview-university, freeCodeCamp, free-programming-books,
  project-based-learning, awesome .... allgemeines Coding-Wissen

## Ablauf

1. FRAGE klassifizieren (Architektur? API? Lernpfad? Implementierung?).
2. Wissensbasis abfragen (RAG-Backend, Standard: MaxKB HTTP-API). Wenn die
   Wissensbasis nicht läuft: ehrlich sagen und auf `deep-research` ausweichen.
3. ANTWORTEN mit Quellenangabe (welches Repo/Dokument). Keine erfundenen Belege.
4. Bei Architektur-Fragen `system-design-primer` bevorzugen; bei API-Fragen
   `public-apis`.
