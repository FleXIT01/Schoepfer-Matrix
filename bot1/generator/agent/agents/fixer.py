"""FixerAgent: repariert fehlerhaften Code anhand eines Tracebacks.

Erweitert: Wenn die AI-OS ServiceRegistry verfügbar ist, nutzt der Fixer
repo-critic-ai für tiefe Code-Analyse und Project Chimera als letzte
Eskalationsstufe (Activation Steering im VRAM), wenn der lokale Fix
wiederholt scheitert.
"""
from __future__ import annotations

import ast
import logging

from ...interview.prompts import CODE_AGENT_SYSTEM_PROMPT, FIXER_PROMPT
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FixerAgent(BaseAgent):
    def __init__(self, llm, *, registry=None) -> None:
        super().__init__(llm, registry=registry)
        self._consecutive_failures: int = 0
        self._chimera_activated: bool = False

    def fix(self, source: str, error: str, *, context: str = "",
            require_function: str | None = None) -> str | None:
        """Gibt korrigierten Code zurück oder None, wenn nicht reparierbar.

        AI-OS Modus:
          1. repo-critic-ai analysiert den Code tiefgehend (AST, Security).
          2. Das Analyse-Ergebnis fließt in den Fix-Prompt ein.
          3. Falls 3+ aufeinanderfolgende Fixes scheitern, wird Chimera
             aktiviert (Activation Steering), um das LLM zu fokussieren.
        """
        # --- AI-OS: Tiefe Code-Analyse über repo-critic-ai ---
        review_hints = self._get_review_hints(source)

        # --- AI-OS: Chimera-Eskalation bei chronischem Versagen ---
        if self._consecutive_failures >= 3 and not self._chimera_activated:
            self._activate_chimera_focus()

        # --- Fix-Prompt zusammenbauen ---
        enriched_context = context or "—"
        if review_hints:
            enriched_context += f"\n\n--- REPO-CRITIC ANALYSE ---\n{review_hints}"

        user = FIXER_PROMPT.format(
            context=enriched_context,
            error=error[-3000:],
            source=source,
        )
        code = self.ask_code(CODE_AGENT_SYSTEM_PROMPT, user)

        if not code:
            self._consecutive_failures += 1
            return None

        try:
            tree = ast.parse(code)
        except SyntaxError:
            self._consecutive_failures += 1
            return None

        if require_function is not None:
            ok = any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == require_function
                for n in tree.body
            )
            if not ok:
                self._consecutive_failures += 1
                return None

        # Erfolg — Reset
        self._consecutive_failures = 0
        if self._chimera_activated:
            self._deactivate_chimera_focus()

        return code.strip()

    def _get_review_hints(self, source: str) -> str:
        """Nutzt repo-critic-ai, um den fehlerhaften Code tief zu analysieren."""
        if not self.has_registry:
            return ""

        reviewer = self.registry.get_service("repo-critic")
        if reviewer is None:
            return ""

        try:
            result = reviewer.execute("review", {
                "source": source,
                "language": "python",
            })
            if result.ok and result.data:
                data = result.data
                if isinstance(data, dict):
                    issues = data.get("issues", [])
                    hints = []
                    for issue in issues[:5]:  # Max 5 Issues
                        if isinstance(issue, dict):
                            hints.append(
                                f"- [{issue.get('severity', '?')}] "
                                f"Zeile {issue.get('line', '?')}: "
                                f"{issue.get('message', '')}"
                            )
                    return "\n".join(hints)
                return str(data)[:1000]
        except Exception as exc:
            logger.debug("repo-critic Analyse fehlgeschlagen (nicht kritisch): %s", exc)

        return ""

    def _activate_chimera_focus(self) -> None:
        """Aktiviert Chimera Activation Steering, um das LLM zu fokussieren."""
        if not self.has_registry:
            return

        chimera = self.registry.get_service("chimera")
        if chimera is None:
            return

        try:
            result = chimera.execute("steer", {
                "vector": "focus_coding",
                "strength": 1.5,
            })
            if result.ok:
                self._chimera_activated = True
                logger.warning(
                    "CHIMERA aktiviert: Steering-Vector 'focus_coding' injiziert "
                    "(nach %d konsekutiven Fehlschlägen).",
                    self._consecutive_failures,
                )
        except Exception as exc:
            logger.debug("Chimera-Aktivierung fehlgeschlagen: %s", exc)

    def _deactivate_chimera_focus(self) -> None:
        """Setzt die Chimera-Steering zurück auf Neutral."""
        if not self.has_registry:
            return

        chimera = self.registry.get_service("chimera")
        if chimera is None:
            return

        try:
            chimera.execute("steer/reset", {})
            self._chimera_activated = False
            logger.info("CHIMERA deaktiviert: Steering zurückgesetzt.")
        except Exception as exc:
            logger.debug("Chimera-Deaktivierung fehlgeschlagen: %s", exc)

