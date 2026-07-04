---
name: image-create
description: "Aus einer Textbeschreibung ein Bild erzeugen (lokale Bildgenerierung mit ComfyUI/SDXL, ohne Cloud)."
metadata:
  {
    "openclaw":
      {
        "emoji": "🎨",
        "requires": { "providers": ["comfy"] }
      }
  }
---

# Image Create — lokale Bildgenerierung

Trigger: „erstelle ein Bild von …", „generiere ein Bild …", „male/zeichne …".

Bilder werden lokal über **ComfyUI** (SDXL) erzeugt — der OpenClaw-`comfy`-Provider
ist eingerichtet (Workflow: `openclaw-workspace/comfy-workflow-sdxl.json`).

## Ablauf

1. VORAUSSETZUNG prüfen: ComfyUI muss laufen (Port 8188). Falls die Bildanfrage
   fehlschlägt, den Nutzer bitten, **`comfy.cmd`** im Repo-Root zu starten.
2. VRAM (16 GB): Das große LLM (gpt-oss-32k, 14 GB) und das Bildmodell passen
   nicht gleichzeitig komplett in die GPU. Vor reiner Bildarbeit ggf.
   `ollama stop gpt-oss-32k` empfehlen, oder mit etwas langsamerer Generierung
   (ComfyUI lagert dann auf CPU aus) rechnen.
3. ERZEUGEN: Den Prompt an den `comfy`-Bild-Provider geben (Text → Bild).
   Stil-/Detailwünsche in den Prompt aufnehmen (z.B. „photorealistisch", „16:9").
4. LIEFERN: Das erzeugte Bild über den Kanal zurücksenden.

## Hinweis
Für Bildbearbeitung (Bild + Anweisung) unterstützt der comfy-Provider auch `edit`
(ein Referenzbild). Andere Modelle (qwen_image, wan2.2, z_image_turbo …) liegen in
ComfyUI bereit; dafür den Workflow in `comfy-workflow-sdxl.json` anpassen.
