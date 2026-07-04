---
name: deep-research
description: "Ein Thema umfassend recherchieren: mehrere Quellen sammeln, abgleichen und einen strukturierten Bericht mit Belegen erstellen."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔎",
        "requires": { "mcp": ["research", "science"] }
      }
  }
---

# Deep Research — fundierte Recherche

Trigger: „recherchiere …", „erstelle einen Bericht über …", „was ist der Stand zu …".

## Ablauf

1. QUELLEN sammeln (mehrgleisig):
   - Komplettrecherche in EINEM Schritt: `research.deep_research(topic)` —
     zerlegt das Thema, sucht im Web (DuckDuckGo), liest Top-Seiten und liefert
     einen strukturierten Bericht MIT Quellen (lokal, ohne Cloud-Key).
   - Einzelne Faktenfrage: `research.web_lookup(query)`.
   - Wissenschaft: `science.openalex_search`, `science.arxiv_search`,
     `science.pubmed_search`, `science.europepmc_search`.
   - Eigenes Wissen: Skill `knowledge-ask` (Lern-Korpus).

2. ABGLEICHEN: Aussagen über mehrere Quellen prüfen; Widersprüche benennen.
   Keine Behauptung ohne Beleg.

3. BERICHT: ## Zusammenfassung / ## Kernpunkte / ## Details / ## Quellen (mit Links).
   Auf Wunsch als Datei speichern und die Existenz danach verifizieren.

4. LERNEN: Den fertigen Bericht in die Wissensbasis/Memory zurückschreiben,
   damit künftige Anfragen davon profitieren.
