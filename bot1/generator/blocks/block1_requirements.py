from __future__ import annotations

import re

from ..llm.base import LLMAdapter, LLMMessage
from ..models.bot_spec import BotSpec
from ..interview.prompts import BLOCK1_GENERATION_TEMPLATE, SPEC_GENERATION_SYSTEM_PROMPT
from ._base import get_jinja_env


class Block1Renderer:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._env = get_jinja_env()

    def render(self, spec: BotSpec) -> str:
        spec_summary = self._spec_to_summary(spec)
        prompt = BLOCK1_GENERATION_TEMPLATE.format(
            spec_summary=spec_summary,
            bot_name=spec.name,
        )
        content = self._llm.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            system=SPEC_GENERATION_SYSTEM_PROMPT,
            temperature=0.3,
        ).strip()

        # Strip any leading H1 heading the LLM added despite instructions
        # (the template wrapper already adds the title)
        content = re.sub(r'^\s*#[^#][^\n]*\n+', '', content)

        template = self._env.get_template("block1_requirements.md.j2")
        return template.render(spec=spec, block1_content=content)

    def _spec_to_summary(self, spec: BotSpec) -> str:
        lines = [
            f"Name: {spec.name}",
            f"Zweck: {spec.description}",
            f"Zielgruppe: {spec.target_users}",
            f"Bot-Typ: {spec.bot_type.value}",
            f"Sprache: {spec.language}",
        ]
        if spec.use_cases:
            lines.append(f"Use Cases: {', '.join(spec.use_cases)}")
        if spec.constraints:
            lines.append(f"Einschränkungen: {', '.join(spec.constraints)}")
        if spec.integration_points:
            lines.append(f"Integrationen: {', '.join(spec.integration_points)}")
        if spec.missing_fields:
            lines.append(f"Fehlende Infos: {', '.join(spec.missing_fields)}")
        return "\n".join(lines)
