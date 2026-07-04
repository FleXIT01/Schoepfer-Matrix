from __future__ import annotations

import json

from ..models.bot_spec import BotSpec
from ._base import get_jinja_env


class Block5Renderer:
    def __init__(self) -> None:
        self._env = get_jinja_env()
        self._env.filters["tojson"] = self._tojson

    def render(self, spec: BotSpec) -> str:
        template = self._env.get_template("block5_code.py.j2")
        return template.render(spec=spec)

    @staticmethod
    def _tojson(value, indent=None) -> str:
        return json.dumps(value, ensure_ascii=False, indent=indent)
