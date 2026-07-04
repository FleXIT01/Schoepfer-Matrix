---
name: ui-audit
description: "Visueller Guardrail für Desktop-Aktionen: nach Klicks, Programmstarts oder ComfyUI-Aktionen per Screenshot + Vision-Modell prüfen, ob es wirklich geklappt hat — statt blind Erfolg zu melden."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔍",
        "requires": { "mcp": ["screenshot", "planner"] }
      }
  }
---

# UI-Audit — Visueller Guardrail (Desktop)

Trigger: „hat das geklappt?", „prüf ob das Fenster offen ist", „schau nach ob …",
und IMMER von selbst nach unsicheren Desktop-Aktionen (Programm gestartet,
Dialog geklickt, ComfyUI-Workflow angestoßen), bevor du Erfolg meldest.

**Grundregel: NIE „erledigt" sagen, wenn du es visuell prüfen könntest und nicht
geprüft hast.** Ein `run_command`-Exit-Code 0 heißt nicht, dass ein Fenster
offen ist.

## Ablauf

1. **GEZIELTE FRAGE formulieren** — nicht „beschreibe den Bildschirm", sondern
   eine Ja/Nein-prüfbare Frage mit Erwartung:
   - „Ist ein Notepad-Fenster mit dem Titel 'test.txt' sichtbar? Antworte JA oder NEIN + 1 Satz."
   - „Zeigt ComfyUI rechts unten ein fertig generiertes Bild oder läuft noch ein Fortschrittsbalken?"

2. **PRÜFEN:** `screenshot.vision_pipeline(question)` — macht Screenshot +
   Vision-Analyse in einem Schritt (qwen3-vl lokal, Cloud-Fallback nur wenn
   lokal nicht verfügbar).
   - Nur ein Bereich relevant? Erst `screenshot.screenshot_take(region_xywh=...)`,
     dann `llm.vision_describe(pfad, frage)` — kleinere Bilder = präzisere Antworten.

3. **VRAM beachten:** qwen3-vl:32b (~20 GB) und gpt-oss-32k passen NICHT
   gleichzeitig in 16 GB. Ollama lagert dann um — die erste Vision-Antwort kann
   ~1–2 min dauern, danach ist der nächste Chat-Turn wieder langsamer.
   Bei Zeitdruck oder vielen Prüfungen hintereinander: `planner.can_load('qwen3-vl:32b')`
   vorher prüfen und den Nutzer über die Wartezeit informieren.

4. **AUSWERTEN:**
   - Erwartung erfüllt → kurz bestätigen („geprüft: Fenster ist offen").
   - NICHT erfüllt → **eine** Korrektur versuchen (z. B. Programm erneut starten,
     richtiges Fenster fokussieren), dann erneut Schritt 1–2.
   - Nach 2 Fehlversuchen: STOPP, Screenshot-Pfad + Vision-Befund an den Nutzer,
     nicht weiterklicken.

## Typische Einsätze

| Aktion davor | Prüffrage |
|---|---|
| `assistant.run_command("notepad …")` | „Ist ein Notepad-Fenster sichtbar?" |
| ComfyUI-Bildgenerierung | „Ist im ComfyUI-Tab ein fertiges Bild zu sehen (kein Fortschrittsbalken)?" |
| Browser-Formular ausgefüllt | „Steht im Feld X der Wert Y?" |
| Installation/Setup gestartet | „Zeigt der Dialog 'Fertigstellen' oder eine Fehlermeldung?" |

## Wann NICHT einsetzen

- Web-Apps aus der Factory → Skill `i2-visual-gate` (headless Screenshot gegen Spec).
- Ergebnisse, die es als Datei/Text gibt (Datei existiert? → `run_command dir`,
  kein Screenshot) — Vision ist das teuerste Prüfwerkzeug, zuletzt greifen.
- Reine Hintergrundprozesse ohne UI.
