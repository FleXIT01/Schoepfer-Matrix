---
name: zweitmeinung
description: "Rat der Modelle: lokal (gpt-oss) und Cloud-günstig (DeepSeek) antworten unabhängig, ein Richter-Modell führt zusammen und markiert Widersprüche explizit. Killt Single-Model-Blindspots."
metadata:
  {
    "openclaw":
      {
        "emoji": "⚖️",
        "requires": { "mcp": ["llm"] }
      }
  }
---

# Zweitmeinung — Rat der Modelle (I3)

Trigger: „wichtige Entscheidung", „sicher gehen", „Zweitmeinung", „vergleiche Antworten",
„was würde ein anderes Modell sagen", „council".

## Ablauf

1. `llm.council(prompt, judge="local")` aufrufen — das Tool:
   - Befragt gpt-oss (lokal) und DeepSeek V3 (Cloud-günstig, Centbereich) **parallel**.
   - Ein Richter-Modell (default: lokal, bei sehr wichtigen Fragen `judge="cloud"`) führt zusammen.
   - Gibt zurück: Konsens, explizite WIDERSPRÜCHE als Liste, Empfehlung.

2. Die Ausgabe **vollständig** an den Nutzer zeigen — insbesondere Widersprüche nicht verschweigen.

3. Bei Kosten-Bedenken: `judge="local"` benutzt nur Ollama für den Richter-Schritt.

## Wann einsetzen

- Technische Architekturentscheidungen mit Langzeitwirkung
- Sicherheits- oder Datenschutzfragen
- Wenn der Nutzer explizit „sicher gehen" oder „Zweitmeinung" sagt
- Bei Widerspruch zwischen eigenem Wissen und Recherche-Ergebnis

## Kosten

Zählt ins V9-Tageslimit (2 €/Tag). Ein Council-Aufruf kostet ca. 0,01–0,05 €.
Bei DeepSeek-Ausfall fällt der Richter automatisch auf lokal zurück.
