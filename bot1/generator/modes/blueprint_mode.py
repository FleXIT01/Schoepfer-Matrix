from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from generator.cli.interface import CLI
from generator.llm.base import LLMAdapter, LLMError, LLMMessage
from generator.modes.base import GeneratorMode
from generator.interview.prompts import PRINCIPAL_ARCHITECT_SYSTEM_PROMPT
from generator.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


class BlueprintModeRunner(GeneratorMode):
    """Executes the interactive blueprint generation mode."""

    def run(self, cli: CLI, llm: LLMAdapter) -> None:
        cli.display("\nBeschreibe kurz den Bot, den ich für dich generieren soll.", markdown=True)
        initial_answer = cli.prompt_input("> ")

        if not initial_answer.strip():
            cli.display_error("Keine Beschreibung eingegeben. Bot Generator beendet.")
            sys.exit(0)

        messages = [LLMMessage(role="user", content=initial_answer)]

        max_iterations = 4  # max 2 Rückfragen + 1 Force + 1 Blueprint
        final_blueprint = ""
        response = ""

        for i in range(max_iterations):
            try:
                status_text = "Generiere Blueprint..." if i == 0 else "Verarbeite Antwort..."
                with cli.status(status_text):
                    response = llm.chat(
                        messages=messages,
                        system=PRINCIPAL_ARCHITECT_SYSTEM_PROMPT,
                        temperature=0.3,
                    ).strip()
            except LLMError as exc:
                logger.warning("LLM-Aufruf im Blueprint-Modus fehlgeschlagen: %s", exc)
                cli.display_error(f"LLM-Fehler: {exc}")
                if not final_blueprint and not response:
                    cli.display_error("Kein Blueprint generiert. Bitte erneut versuchen.")
                    sys.exit(1)
                break

            if "BOT-BLUEPRINT:" in response:
                final_blueprint = response
                break

            # Rückfrage vom LLM — dem Nutzer zeigen und antworten lassen
            cli.display(f"\n{response}\n", markdown=True)
            messages.append(LLMMessage(role="assistant", content=response))

            user_reply = cli.prompt_input("> ").strip()
            if user_reply.lower() in {"fertig", "weiter", "skip", "überspringen", ""}:
                messages.append(LLMMessage(role="user", content="Bitte generiere jetzt den Blueprint ohne weitere Fragen."))
            else:
                messages.append(LLMMessage(role="user", content=user_reply))

            # Nach 2 Rückfragen Blueprint erzwingen
            if i == max_iterations - 2:
                messages.append(LLMMessage(role="user", content="Generiere jetzt den Blueprint mit den vorhandenen Informationen."))

        if not final_blueprint:
            # Fallback if the LLM never outputs the marker
            final_blueprint = response
            
        # Extract bot name for folder name if possible
        bot_name = "blueprint_bot"
        for line in final_blueprint.split("\n"):
            # Neues Format: "## BOT-BLUEPRINT: BotName"
            if "BOT-BLUEPRINT:" in line:
                parts = line.split("BOT-BLUEPRINT:", 1)
                if len(parts) > 1:
                    extracted = re.sub(r"[^a-zA-Z0-9_]+", "_", parts[1].strip()).strip("_").lower()
                    if extracted:
                        bot_name = extracted[:40]
                break
            
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_dir = Path(OUTPUT_DIR) / f"{bot_name}_{timestamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        blueprint_path = out_dir / "blueprint.md"
        blueprint_path.write_text(final_blueprint, encoding="utf-8")
        
        cli.display_progress("Blueprint generiert.")
        cli.display_success(str(blueprint_path.resolve()))
