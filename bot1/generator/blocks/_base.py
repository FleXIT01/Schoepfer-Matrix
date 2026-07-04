from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape([]),  # No HTML escaping for Python/Markdown
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
