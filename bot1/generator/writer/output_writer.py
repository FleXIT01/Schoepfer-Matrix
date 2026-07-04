from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..models.bot_spec import BotSpec


class OutputWriter:
    def __init__(self, output_base_dir: Path) -> None:
        self._base = output_base_dir

    def write(self, spec: BotSpec, blocks: dict[str, str]) -> Path:
        """
        Creates timestamped output directory and writes all files.
        Returns the path to the created directory.
        """
        slug = self._make_slug(spec.name)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_dir = self._base / f"{slug}_{ts}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Doku-Blöcke. Der lauffähige Bot-Code (bot/) wird vom Agent-Build
        # (Orchestrator) in dasselbe Verzeichnis geschrieben.
        file_map = {
            "block1": ("requirements.md", "utf-8"),
            "block2": ("architecture.md", "utf-8"),
            "block3": ("prompt_package.md", "utf-8"),
            "block4": ("schemas.json", "utf-8"),
        }

        for key, (filename, encoding) in file_map.items():
            if key not in blocks:
                continue
            (output_dir / filename).write_text(blocks[key], encoding=encoding)

        (output_dir / "bot_spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )

        return output_dir

    @staticmethod
    def _make_slug(name: str) -> str:
        import re
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
        return slug[:40] or "bot"
