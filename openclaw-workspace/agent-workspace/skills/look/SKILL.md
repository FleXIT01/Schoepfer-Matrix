---
name: look
description: "Bild/Screenshot/Foto analysieren, Text extrahieren (OCR), Diagramme erklären, Fehlermeldungen aus Screenshots lesen."
metadata:
  {
    "openclaw":
      {
        "emoji": "👁️",
        "requires": { "mcp": ["llm"] }
      }
  }
---

# look (N3) — Vision-Skill

Trigger: „schau dir das an", „was siehst du", „lies den Screenshot", „OCR", „erkläre das Bild",
„was steht da", „beschreib das Foto", „was ist auf dem Bild", „Fehler im Screenshot".

---

## Sicherheitsregeln

- VRAM prüfen bevor das VL-Modell geladen wird (planner.can_load).
- Nur lokale Dateipfade oder vom Nutzer bereitgestellte Pfade — nie URLs
  direkt als Image-Pfad weitergeben.
- Ergebnis ist eine Beschreibung/Extraktion, kein ausführbarer Code.

---

## Ablauf

### 1. VRAM-Check (immer)

```
planner.can_load(model="qwen3-vl:32b")
```

→ Kann es laden? Wenn NEIN: Nutzer informieren, kein Vision-Call.
→ Wenn JA: weiter zu Schritt 2.

Hinweis: qwen3-vl:32b braucht ~16 GB VRAM. Läuft kein anderes großes Modell
gleichzeitig, passt es auf die 16-GB-GPU.

### 2. Bild analysieren

```
llm.vision_describe(
    image_path="<absoluter Pfad zur Bilddatei>",
    question="<was der Nutzer wissen will>"
)
```

Standard-Fragen je Kontext:
- Screenshot/UI: „Beschreibe präzise, was auf diesem Screenshot zu sehen ist,
  insbesondere alle lesbaren Texte, Buttons und Fehlermeldungen."
- OCR/Dokument: „Extrahiere allen lesbaren Text aus diesem Bild. Behalte die
  Formatierung bei, wo erkennbar."
- Diagramm/Grafik: „Erkläre dieses Diagramm: was zeigt es, welche Beschriftungen
  gibt es, was ist die Kernaussage?"
- Foto: „Beschreibe dieses Foto detailliert: Objekte, Personen (ohne Namen),
  Umgebung, Farben, Aktivitäten."

### 3. Antwort formulieren

Antwort direkt aus dem Vision-Ergebnis zurückgeben.
Bei OCR-Aufgaben: Extrahierten Text klar formatiert zurückgeben.
Bei Fehler-Screenshots: Fehlermeldung zitieren + kurze Deutung.

---

## Fehlerfälle

- `Bilddatei nicht gefunden` → Nutzer nach korrektem Pfad fragen.
- VRAM zu knapp → „qwen3-vl benötigt ~16 GB VRAM. Bitte zuerst andere große
  Modelle in Ollama entladen (`ollama stop <modell>`), dann nochmal."
- Modell nicht installiert → `ollama pull qwen3-vl:32b` empfehlen.
- Bild zu groß (> 20 MB) → Empfehlung: Bild vorher skalieren.

---

## Beispielaufrufe

„Schau dir diesen Screenshot an: C:\Users\Farnberger\Desktop\fehler.png"
→ vision_describe(image_path="C:\\Users\\Farnberger\\Desktop\\fehler.png",
    question="Was zeigt dieser Screenshot, insbesondere Fehlermeldungen?")

„Lies den Text auf diesem Foto: n:\\allinall\\docs\\notiz.jpg"
→ vision_describe(image_path="n:\\allinall\\docs\\notiz.jpg",
    question="Extrahiere allen lesbaren Text aus diesem Bild.")
