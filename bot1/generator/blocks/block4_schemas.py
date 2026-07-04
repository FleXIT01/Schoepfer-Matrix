from __future__ import annotations

import json

from ..models.bot_spec import BotSpec
from ._base import get_jinja_env


class Block4Renderer:
    def __init__(self) -> None:
        self._env = get_jinja_env()
        # Add tojson filter
        self._env.filters["tojson"] = self._tojson

    def render(self, spec: BotSpec) -> str:
        template = self._env.get_template("block4_schemas.json.j2")
        raw = template.render(spec=spec)
        # Validate JSON and pretty-print
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # Return raw if JSON is invalid (template issue) with comment
            return raw

    @staticmethod
    def _tojson(value, indent=None) -> str:
        return json.dumps(value, ensure_ascii=False, indent=indent)
