---
name: i2-visual-gate
description: "Fabrik mit Augen: gebaute Web-App starten → headless Screenshot → visuelles Review gegen Spezifikation → Findings. Das Completion-Gate bekommt Augen (I2)."
metadata:
  {
    "openclaw":
      {
        "emoji": "👁️",
        "requires": { "mcp": ["factory", "review", "planner"] }
      }
  }
---

# Fabrik mit Augen — Visuelles Gate (I2)

Trigger: „schau dir die App an", „prüf das visuell", „mach einen Screenshot",
„sieht das richtig aus", „visuelle Überprüfung".

Voraussetzung für Screenshots: `playwright` + Chromium installiert.
Installation (einmalig): `pip install playwright && playwright install chromium`

## Ablauf

**VRAM-Regel: qwen3-vl:32b (~20 GB) und gpt-oss-32k (~16 GB) passen NICHT gleichzeitig
in 16 GB VRAM. Vor visual_review: `planner.can_load('qwen3-vl:32b')` prüfen.**

1. VRAM PRÜFEN:
   - `planner.can_load('qwen3-vl:32b')` → passt es?
   - Wenn NEIN: Nutzer informieren, kein visuelles Review möglich bis gpt-oss entladen.
   - Wenn JA: weiter.

2. APP STARTEN:
   - `factory.start_webapp(path, port=8765)` → URL zurück
   - Fehlschlag? → `factory.build_bot(...)` zuerst ausführen.

3. SCREENSHOT:
   - `factory.screenshot_webapp(url)` → PNG-Pfad
   - Fehlschlag mit "playwright nicht installiert"? → Installationsanleitung ausgeben, STOPP.

4. VISUELLES REVIEW:
   - `review.visual_review(screenshot_path, spec)` → Findings (KORREKT / FEHLER / FAZIT)
   - `spec` = die ursprüngliche Spezifikation des Bots/der App.

5. ERGEBNIS:
   - BESTANDEN: Nutzer informieren + Screenshot-Pfad nennen.
   - NICHT BESTANDEN: Findings ausgeben, Fix-Runde anbieten.

## Fix-Iterationen (max. 3)

Wenn NICHT BESTANDEN:
1. Findings als Korrektur-Spec an `factory.build_bot(...)` übergeben.
2. Dann start_webapp → screenshot_webapp → visual_review erneut.
3. Nach 3 Runden ohne Erfolg: Nutzer direkt einschalten mit konkreten Findings.

## Fehlerfälle

- `playwright not installed` → Installationsanleitung und STOPP
- VRAM zu knapp → `planner.can_load` Ergebnis zeigen, STOPP
- App startet nicht → Build-Report prüfen, build_bot erneut mit anderem Modell
- visual_review timeout → qwen3-vl noch nicht geladen, kurz warten und retry

## Wann NICHT einsetzen

- Reine CLI-Tools (kein Web-Frontend) → stattdessen review.scan_repo
- VRAM < 20 GB freier Platz → verzichten bis Modell entladen
