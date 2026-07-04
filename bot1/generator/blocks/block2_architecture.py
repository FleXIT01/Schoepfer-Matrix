from __future__ import annotations

import re

from ..llm.base import LLMAdapter, LLMMessage
from ..models.bot_spec import BotSpec
from ..interview.prompts import BLOCK2_GENERATION_TEMPLATE, SPEC_GENERATION_SYSTEM_PROMPT
from ._base import get_jinja_env


class Block2Renderer:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._env = get_jinja_env()

    def render(self, spec: BotSpec) -> str:
        spec_summary = self._spec_to_summary(spec)

        # Pre-compute tool and integration sections deterministically — no LLM
        if spec.tools:
            rows = ["| Tool | Zweck | Input | Output |", "|------|-------|-------|--------|"]
            for t in spec.tools:
                rows.append(f"| **{t.name}** | {t.description} | `query: str` | `str` |")
            tool_section = "\n".join(rows)
        else:
            tool_section = "Keine Tools spezifiziert."

        if spec.integration_points:
            integration_section = "\n".join(
                f"- **{ip}**" for ip in spec.integration_points
            )
        else:
            integration_section = "Keine externen Integrationen spezifiziert."

        # Hints injected directly into the LLM prompt
        tool_flow_hint = " → Tools (wenn aufgerufen)" if spec.tools else ""
        if spec.tools:
            error_handling_hint = (
                "Dokumentiere NUR diese Fehlerszenarien:\n"
                "- LLM-Fehler: Retry-Logik und Fallback-Text\n"
                "- Tool-Fehler: Fehlermeldung an Nutzer\n"
                "- Eingabefehler: Validierung vor Tool-Aufruf"
            )
        else:
            error_handling_hint = (
                "Dokumentiere NUR LLM-Fehler: Retry-Logik und Fallback-Text "
                "wenn das LLM nicht antwortet."
            )

        prompt = BLOCK2_GENERATION_TEMPLATE.format(
            spec_summary=spec_summary,
            provider=spec.llm.provider,
            model=spec.llm.model or "(Provider-Default)",
            memory_strategy=spec.memory_strategy.value,
            tool_flow_hint=tool_flow_hint,
            error_handling_hint=error_handling_hint,
        )
        content = self._llm.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            system=SPEC_GENERATION_SYSTEM_PROMPT,
            temperature=0.3,
        ).strip()

        # Strip any leading H1 heading the LLM added despite instructions
        content = re.sub(r'^\s*#[^#][^\n]*\n+', '', content)

        template = self._env.get_template("block2_architecture.md.j2")
        return template.render(
            spec=spec,
            block2_content=content,
            tool_section=tool_section,
            integration_section=integration_section,
        )

    def _spec_to_summary(self, spec: BotSpec) -> str:
        lines = [
            f"Name: {spec.name}",
            f"Typ: {spec.bot_type.value}",
            f"Zweck: {spec.description}",
            f"Zielgruppe: {spec.target_users}",
            f"Memory-Strategie: {spec.memory_strategy.value}",
            f"LLM: {spec.llm.provider}/{spec.llm.model or 'Provider-Default'}",
        ]
        if spec.use_cases:
            lines.append(f"Use Cases: {', '.join(spec.use_cases)}")
        if spec.constraints:
            lines.append(f"Constraints: {', '.join(spec.constraints)}")
        return "\n".join(lines)
