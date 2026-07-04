from __future__ import annotations

from ..models.bot_spec import BotSpec
from ._base import get_jinja_env


class Block3Renderer:
    def __init__(self) -> None:
        self._env = get_jinja_env()

    def render(self, spec: BotSpec) -> str:
        # system_prompt, developer_notes, example_conversations already in spec
        template = self._env.get_template("block3_prompts.md.j2")
        return template.render(spec=spec)
