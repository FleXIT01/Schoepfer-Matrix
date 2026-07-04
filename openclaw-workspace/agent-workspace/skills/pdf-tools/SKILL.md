---
name: pdf-tools
description: "PDF-Dateien lesen, zusammenfassen und übersetzen (lokal, ohne Cloud)."
metadata:
  {
    "openclaw":
      {
        "emoji": "📄",
        "requires": { "mcp": ["pdf"] }
      }
  }
---

# PDF Tools — PDFs lesen, zusammenfassen, übersetzen

Trigger: „fasse diese PDF zusammen", „worum geht es in <datei.pdf>", „übersetze die PDF".

Alles lokal über das `pdf`-MCP (pypdf + lokales Modell), kein Cloud-Key.

## Ablauf

1. EXTRAHIEREN: `pdf.pdf_extract(pdf_path)` für den Rohtext (prüft, ob es ein
   gescanntes Bild-PDF ist — dann ist OCR nötig).
2. ZUSAMMENFASSEN: `pdf.pdf_summarize(pdf_path, focus="")` → deutsche
   Strukturzusammenfassung (Kurzfazit + Kernpunkte).
3. ÜBERSETZEN: `pdf.pdf_translate(pdf_path, target_lang="Deutsch", max_pages=10)`
   — übersetzungsintensiv, daher seitenweise/klein halten.
4. Bei langen Dokumenten `max_pages` schrittweise erhöhen statt alles auf einmal.

## Hinweis
Für tiefe wissenschaftliche Analyse die Ergebnisse mit `science.*` (z.B.
`pubmed_search`) oder `research.deep_research` kombinieren.
