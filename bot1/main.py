#!/usr/bin/env python3
"""Bot Generator — Einstiegspunkt."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path when run as script
sys.path.insert(0, str(Path(__file__).parent))

from generator.config import (
    LLM_API_BASE,
    LLM_MODEL,
    LLM_PROVIDER,
    get_api_key_for_provider,
)
from generator.llm import LLMError, create_llm_adapter
from generator.cli.interface import CLI
from generator.modes.classic_mode import ClassicModeRunner
from generator.modes.blueprint_mode import BlueprintModeRunner


_PROVIDER_DISPLAY = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT-4o)",
    "ollama": "Ollama (lokal)",
    "lmstudio": "LM Studio (lokal)",
    "openai-compat": "OpenAI-kompatibel",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot Generator")
    parser.add_argument(
        "mode", 
        nargs="?", 
        choices=["classic", "blueprint"],
        help="Wähle den Generierungsmodus: 'classic' (5 Dateien) oder 'blueprint' (1 Datei)"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "ollama", "lmstudio", "openai-compat"],
        default=None,
        help="LLM-Provider überschreiben (Standard: aus .env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM-Modell überschreiben (Standard: aus .env oder Provider-Default)",
    )
    args = parser.parse_args()

    cli = CLI()
    cli.display_header("Bot Generator")

    # --- Resolve provider ---
    provider = args.provider or LLM_PROVIDER
    model = args.model or LLM_MODEL
    api_key = get_api_key_for_provider(provider)
    display_name = _PROVIDER_DISPLAY.get(provider, provider)

    if provider == "ollama" and not model:
        import subprocess
        import time
        from generator.llm.ollama_adapter import get_available_models

        base_url = LLM_API_BASE or "http://localhost:11434"

        with cli.status("Rufe verfügbare lokale Modelle ab..."):
            models = get_available_models(base_url)

        if not models:
            cli.display("[yellow]Ollama antwortet nicht — öffne neues Terminal mit 'ollama serve'...[/yellow]")
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", "ollama serve"])

            with cli.status("Warte auf Ollama-Start (bis 20 Sek.)..."):
                for _ in range(20):
                    time.sleep(1)
                    models = get_available_models(base_url)
                    if models:
                        break

        if not models:
            cli.display_error("Ollama ist gestartet, hat aber noch keine Modelle.")
            cli.display_error("Im neuen Terminal ausführen: ollama pull llama3.1 — dann nochmal starten.")
            sys.exit(1)
            
        cli.display("Verfügbare Ollama Modelle:", markdown=True)
        for i, m in enumerate(models, 1):
            cli.display(f"[{i}] [cyan]{m}[/cyan]")
            
        while True:
            choice = cli.prompt_input("Wähle ein Modell (Nummer) oder tippe den Modellnamen > ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(models):
                model = models[int(choice) - 1]
                break
            elif choice:
                model = choice
                break
            else:
                cli.display_error("Bitte eine Nummer eingeben oder einen Modellnamen tippen.")

    try:
        llm = create_llm_adapter(
            provider,
            api_key=api_key,
            model=model,
            base_url=LLM_API_BASE,
        )
    except LLMError as exc:
        cli.display_error(str(exc))
        sys.exit(1)

    cli.display(f"Provider: [bold green]{display_name}[/bold green]" + (f" ([cyan]{model}[/cyan])" if model else ""))

    # --- Mode selection ---
    mode_choice = args.mode
    if not mode_choice:
        cli.display("\nKein Modus angegeben. Wähle den Generierungsmodus:", markdown=True)
        cli.display("[1] [cyan]Classic[/cyan] (5 Dateien)")
        cli.display("[2] [cyan]Blueprint[/cyan] (1 Datei)")
        
        while True:
            choice = cli.prompt_input("Wahl (1 oder 2) > ").strip()
            if choice == "1":
                mode_choice = "classic"
                break
            elif choice == "2":
                mode_choice = "blueprint"
                break
            else:
                cli.display_error("Ungültige Eingabe. Bitte '1' oder '2' eingeben.")
    
    if mode_choice == "classic":
        runner = ClassicModeRunner()
    else:
        runner = BlueprintModeRunner()
        
    runner.run(cli=cli, llm=llm)


if __name__ == "__main__":
    main()
