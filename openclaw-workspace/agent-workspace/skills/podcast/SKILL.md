---
name: podcast
description: "Thema oder PDF(s) → ~5-Minuten-Sprechtext → Piper TTS → Telegram-Sprachnachricht."
metadata:
  {
    "openclaw":
      {
        "emoji": "🎙️",
        "requires": { "mcp": ["research", "pdf", "voice", "mail"] }
      }
  }
---

# Podcast-Skill (I5) — Berichte zum Anhören

Trigger: „als Podcast", „als Audio", „zum Anhören", „Sprachnachricht darüber",
„hör dir das an", „podcast über …".

## Ablauf

### 1. Inhalt holen

- **Thema:** `research.deep_research(topic)` → Bericht + Quellen.
- **Einzelne PDF(s):** `pdf.pdf_extract(path)` je Datei, dann zusammenfassen.
- Bei „aktuell/heute" immer Web nutzen — nie aus dem Gedächtnis.

### 2. Sprechtext schreiben (SELBST erledigen, kein Tool)

Transformiere den Bericht **direkt** in Sprechtext — das ist deine eigene Aufgabe,
kein Tool-Aufruf. Regeln:

- **Gesprochene Sprache:** keine Aufzählungen, keine Markdown-Formatierung,
  keine Klammern, keine URLs.
- **Länge:** 700–850 Wörter (≈ 5 Minuten bei normaler Sprechgeschwindigkeit).
- **Struktur:** kurze Eröffnung (Thema + 1 Satz Bedeutung) → 3–4 Hauptpunkte
  als natürliche Absätze → kurzer Abschluss.
- **Stil:** klar, informell, direkt — wie ein Freund, der etwas Interessantes
  erklärt. Keine Fachgesten-Sprache.
- Fange NICHT mit „Hallo" oder „Willkommen" an.

### 3. Sprachsynthese

```
voice.speak(sprechtext)
```
→ gibt den ABSOLUTEN WAV-Pfad zurück (z.B. `n:\allinall\openclaw-workspace\output\speech_1234.wav`).

### 4. Als Telegram-Sprachnachricht senden

```
mail.telegram_send_voice(file_path=<wav-pfad>, caption=<kurzer Titel>)
```
WAV wird automatisch zu OGG/Opus konvertiert. Eigener Chat → sofort, kein Gate.

### 5. Bestätigen

Melde: Thema, Wortanzahl (ungefähr), WAV-Pfad, ob Telegram-Versand OK war.

---

## Kür: Zwei-Stimmen-Dialog (optional, wenn Nutzer es wünscht)

Falls der Nutzer „als Dialog" oder „Host und Experte" sagt:

1. Sprechtext als abwechselnde Turns schreiben: `[HOST] Frage …` / `[EXPERTE] Antwort …`
2. Je Turn `voice.speak()` aufrufen (beide Male selbe Stimme — Piper hat derzeit nur eine).
3. WAV-Dateien mit ffmpeg verketten:
   `assistant.run_command("ffmpeg -y -i concat:... -c copy output.wav")`
4. Ergebnis versenden wie in Schritt 4.

---

## Fehlerfälle

- `voice.speak()` meldet „Piper nicht gefunden" → `n:\allinall\piper\piper.exe` prüfen.
- `telegram_send_voice` meldet ffmpeg-Fehler → `winget install ffmpeg` ausführen,
  Gateway neu starten.
- Bericht zu lang (>1000 Wörter) → auf Kernpunkte kürzen, bevor `speak()` aufgerufen wird.
