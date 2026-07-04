"""Media Service-Bridge: Das kreative Auge.

Koppelt ComfyUI (Bildgenerierung, Bildanalyse) und PDFMathTranslate
(PDF-Übersetzung ohne Layoutverlust) als multimediale Worker.

Lokale Pfade:
  - n:\\allinall\\ComfyUI_portable       (Stable Diffusion Pipeline)
  - n:\\allinall\\PDFMathTranslate-main  (PDF-Übersetzer)
"""
from __future__ import annotations

import logging
from typing import Any

from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_comfyui_config(repo_path: str = r"n:\allinall\ComfyUI_portable") -> ServiceConfig:
    return ServiceConfig(
        name="comfyui",
        display_name="ComfyUI (Image Generation & Analysis)",
        port=8188,
        health_endpoint="/",
        start_command="call run_nvidia_gpu.bat",
        auto_start=False,          # VRAM-hungrig — nur bei Bedarf starten
        scale_to_zero=True,         # Sehr VRAM-hungrig, unbedingt on-demand
        idle_timeout_seconds=120,    # Nach 2 Min sofort stoppen
        capabilities=[
            "image_generation", "image_analysis", "logo_design",
            "ui_mockup", "style_transfer",
        ],
        tags=["media", "image", "gpu", "worker"],
        repo_path=repo_path,
    )


def create_pdftranslate_config(repo_path: str = r"n:\allinall\PDFMathTranslate-main") -> ServiceConfig:
    return ServiceConfig(
        name="pdf-translate",
        display_name="PDFMathTranslate (Wissenschaftliche PDF-Übersetzung)",
        port=7860,
        health_endpoint="/",
        auto_start=False,
        scale_to_zero=True,
        idle_timeout_seconds=180,
        capabilities=[
            "pdf_translation", "document_processing", "math_preservation",
            "scientific_translation",
        ],
        tags=["media", "document", "translation", "worker"],
        repo_path=repo_path,
    )


class MediaService(HttpService):
    """Einheitlicher Zugriff auf multimediale Werkzeuge (Bilder, PDFs).

    Wird vom Orchestrator gerufen, wenn:
      - Bilder/Logos/UI-Mockups generiert werden sollen (ComfyUI)
      - PDFs übersetzt werden müssen (PDFMathTranslate)
    """

    def __init__(self, repo_path: str = r"n:\allinall\ComfyUI_portable") -> None:
        config = create_comfyui_config(repo_path)
        super().__init__(config, timeout=300.0)

    def generate_image(self, prompt: str, *, negative_prompt: str = "",
                       width: int = 1024, height: int = 1024,
                       style: str = "default") -> ServiceResult:
        """Generiert ein Bild via Stable Diffusion / ComfyUI Workflow."""
        return self.execute("generate", {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "style": style,
        })

    def analyze_image(self, image_path: str, *, question: str = "") -> ServiceResult:
        """Analysiert ein Bild (Vision-Modell über ComfyUI)."""
        return self.execute("analyze", {
            "image_path": image_path,
            "question": question,
        })


class PDFTranslateService(HttpService):
    """Bridge zu PDFMathTranslate: PDF-Übersetzung mit Layout-Erhalt."""

    def __init__(self, repo_path: str = r"n:\allinall\PDFMathTranslate-main") -> None:
        config = create_pdftranslate_config(repo_path)
        super().__init__(config, timeout=600.0)

    def translate_pdf(self, file_path: str, *, target_language: str = "de",
                      preserve_math: bool = True) -> ServiceResult:
        """Übersetzt ein PDF und behält Formeln/Layout bei."""
        return self.execute("translate", {
            "file_path": file_path,
            "target_language": target_language,
            "preserve_math": preserve_math,
        })
