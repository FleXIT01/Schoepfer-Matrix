"""Tool: Bild-/UI-Mockup-Generierung via lokales ComfyUI.

Sendet einen Text-zu-Bild-Workflow an eine laufende ComfyUI-Instanz
(Standard-Port 8188), wartet auf das Ergebnis und speichert das PNG.
Damit kann die Matrix UI-Mockups, Logos und Konzept-Bilder erzeugen.

Voraussetzung: ComfyUI läuft (z.B. via ComfyUI_portable\\run_nvidia_gpu.bat)
und es ist mindestens ein Checkpoint-Modell installiert.

Läuft ComfyUI nicht, gibt das Tool eine klare Startanweisung zurück.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"prompt": "modern minimalist mobile app login screen, clean UI", "width": 768, "height": 768}
DEFINITION = {
    "name": "generate_image",
    "description": (
        "Erzeugt ein Bild aus einem Text-Prompt über das lokale ComfyUI. "
        "Ideal für: UI-Mockups, App-Designs, Logos, Konzeptbilder. "
        "Speichert das Ergebnis als PNG und gibt den Pfad zurück."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Bildbeschreibung (Englisch funktioniert am besten)"},
            "width": {"type": "integer", "description": "Breite in Pixel (Standard: 768)"},
            "height": {"type": "integer", "description": "Höhe in Pixel (Standard: 768)"},
            "checkpoint": {"type": "string", "description": "Name der Modell-Datei (.safetensors), leer = automatisch"},
        },
        "required": ["prompt"],
    },
}

_HOST = "http://127.0.0.1:8188"
_NEGATIVE = "lowres, blurry, distorted, ugly, watermark, text artifacts"


def generate_image(prompt: str, width: int = 768, height: int = 768,
                   checkpoint: str = "") -> str:
    """Generiert ein Bild via ComfyUI und gibt den Dateipfad zurück."""
    import json
    import time
    import httpx

    # 1) Läuft ComfyUI? Und welcher Checkpoint ist verfügbar?
    ckpt = checkpoint
    try:
        info = httpx.get(f"{_HOST}/object_info/CheckpointLoaderSimple", timeout=8)
        if info.status_code != 200:
            return _not_running()
        if not ckpt:
            choices = (info.json().get("CheckpointLoaderSimple", {})
                       .get("input", {}).get("required", {})
                       .get("ckpt_name", [[]]))[0]
            if not choices:
                return ("[ComfyUI läuft, aber es ist kein Checkpoint-Modell installiert.\n"
                        " Lege ein .safetensors-Modell in ComfyUI_portable\\ComfyUI\\models\\checkpoints\\ ab.]")
            ckpt = choices[0]
    except Exception:  # noqa: BLE001
        return _not_running()

    # 2) Workflow zusammenbauen (klassischer txt2img-Graph)
    workflow = _build_workflow(prompt, _NEGATIVE, width, height, ckpt)

    # 3) Auftrag absenden
    try:
        resp = httpx.post(f"{_HOST}/prompt", json={"prompt": workflow}, timeout=15)
        if resp.status_code != 200:
            return f"[ComfyUI lehnte den Auftrag ab: HTTP {resp.status_code} — {resp.text[:200]}]"
        prompt_id = resp.json().get("prompt_id")
    except Exception as exc:  # noqa: BLE001
        return f"[ComfyUI-Auftrag fehlgeschlagen: {exc}]"

    if not prompt_id:
        return "[ComfyUI gab keine prompt_id zurück]"

    # 4) Auf Fertigstellung warten (max ~120s)
    image_info = None
    for _ in range(60):
        time.sleep(2)
        try:
            hist = httpx.get(f"{_HOST}/history/{prompt_id}", timeout=8).json()
        except Exception:  # noqa: BLE001
            continue
        entry = hist.get(prompt_id)
        if not entry:
            continue
        outputs = entry.get("outputs", {})
        for node_out in outputs.values():
            if node_out.get("images"):
                image_info = node_out["images"][0]
                break
        if image_info:
            break

    if not image_info:
        return f"[ComfyUI: Zeitüberschreitung — Bild für prompt_id {prompt_id} nicht fertig]"

    # 5) Bild herunterladen und speichern
    try:
        img = httpx.get(f"{_HOST}/view", params={
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }, timeout=20)
        from pathlib import Path
        out_path = Path(f"C:/Users/Farnberger/Downloads/{image_info['filename']}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img.content)
        return (f"✓ Bild generiert (Modell: {ckpt})\n"
                f"  Prompt: {prompt}\n"
                f"  Gespeichert: {out_path}")
    except Exception as exc:  # noqa: BLE001
        return f"[Bild-Download fehlgeschlagen: {exc}]"


def _build_workflow(positive: str, negative: str, w: int, h: int, ckpt: str) -> dict:
    """Erzeugt den Standard-ComfyUI txt2img-Workflow als API-Graph."""
    import random
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": positive, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": random.randint(0, 2**32 - 1), "steps": 25, "cfg": 7.0,
                         "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                         "model": ["4", 0], "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "omega_matrix", "images": ["8", 0]}},
    }


def _not_running() -> str:
    return ("[ComfyUI läuft nicht auf Port 8188.\n"
            " Starte es mit: ComfyUI_portable\\run_nvidia_gpu.bat\n"
            " (oder run_cpu.bat). Danach ist generate_image einsatzbereit.]")
