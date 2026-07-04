from __future__ import annotations

import sys
import logging

from generator.cli.interface import CLI
from generator.llm.base import LLMAdapter, LLMError
from generator.modes.base import GeneratorMode
from generator.config import MAX_FOLLOWUP_QUESTIONS, OUTPUT_DIR, LLM_PROVIDER, LLM_MODEL
from generator.interview.conductor import InterviewConductor
from generator.spec.builder import BotSpecBuilder
from generator.blocks.block1_requirements import Block1Renderer
from generator.blocks.block2_architecture import Block2Renderer
from generator.blocks.block3_prompt_package import Block3Renderer
from generator.blocks.block4_schemas import Block4Renderer
from generator.writer.output_writer import OutputWriter
from generator.agent.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class ClassicModeRunner(GeneratorMode):
    """Executes the classic 5-block bot generation flow."""
    
    def run(self, cli: CLI, llm: LLMAdapter) -> None:
        # Phase 1: Interview
        conductor = InterviewConductor(llm=llm, max_followups=MAX_FOLLOWUP_QUESTIONS)
        result = conductor.run(cli=cli)

        if not result.state.raw_initial_description.strip():
            cli.display_error("Keine Beschreibung eingegeben. Bot Generator beendet.")
            sys.exit(0)

        cli.display("\nDanke! Erstelle jetzt die vollständige Bot-Spezifikation...\n")

        # Phase 2: BotSpec erstellen
        try:
            with cli.status("Erstelle Bot-Spezifikation..."):
                builder = BotSpecBuilder(
                    llm=llm,
                    provider=LLM_PROVIDER,
                    model=LLM_MODEL or "",
                )
                spec = builder.build(result.state)
        except LLMError as exc:
            cli.display_error(f"BotSpec-Erstellung fehlgeschlagen: {exc}")
            sys.exit(1)
        except Exception as exc:
            logger.exception("Unerwarteter Fehler bei BotSpec-Erstellung")
            cli.display_error(f"Unerwarteter Fehler: {exc}")
            sys.exit(1)

        if spec.missing_fields:
            cli.display_progress(
                f"Hinweis: {len(spec.missing_fields)} Felder fehlen und wurden als TODO markiert."
            )

        # Phase 3: Doku-Blöcke rendern (der lauffähige Code kommt aus dem Agent-Build)
        renderers = [
            ("block1", lambda: Block1Renderer(llm).render(spec), "Anforderungen"),
            ("block2", lambda: Block2Renderer(llm).render(spec), "Architektur"),
            ("block3", lambda: Block3Renderer().render(spec), "Prompt-Paket"),
            ("block4", lambda: Block4Renderer().render(spec), "JSON-Schemas"),
        ]

        blocks: dict[str, str] = {}
        for i, (key, render_fn, title) in enumerate(renderers, 1):
            cli.display_section(i, title)
            try:
                blocks[key] = render_fn()
                cli.display_progress(f"{title} generiert.")
            except Exception as exc:
                cli.display_error(f"{title} fehlgeschlagen: {exc}")
                blocks[key] = f"# FEHLER bei der Generierung: {exc}\n"

        # Phase 4: Spezifikation + Doku schreiben
        writer = OutputWriter(output_base_dir=OUTPUT_DIR)
        output_path = writer.write(spec=spec, blocks=blocks)

        # Phase 5: Agent-Build — aus der Spec einen echten, verifizierten Bot bauen
        cli.display(
            "\nBaue jetzt einen echten, verifizierten Bot aus der Spezifikation "
            "(Architekt → Coder → Gates → Fixer)...\n"
        )
        try:
            orchestrator = Orchestrator(llm)
            with cli.status("Agent-Build läuft..."):
                build_result = orchestrator.build(
                    spec=spec,
                    out_dir=output_path,
                    progress=cli.display_progress,
                )
            if build_result.ok:
                cli.display_progress("Bot verifiziert — alle Gates grün.")
            else:
                cli.display_progress(
                    "Bot erstellt, aber mit Einschränkungen (Details in BUILD_REPORT.md)."
                )
            if build_result.final_run_ok:
                cli.display_progress("Finaler Lauf gegen das lokale Modell erfolgreich.")
            elif build_result.final_run_ok is False:
                cli.display_progress(
                    "Hinweis: Finaler echter Lauf nicht erfolgreich (läuft das Modell?)."
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent-Build fehlgeschlagen")
            cli.display_error(
                f"Agent-Build fehlgeschlagen: {exc} — Spezifikation und Doku bleiben erhalten."
            )

        cli.display_success(str(output_path.resolve()))
        cli.display(
            f"\nStarte den Bot mit:\n"
            f'  cd "{output_path.resolve()}"\n'
            f"  pip install -r requirements.txt\n"
            f"  python run.py\n"
        )
