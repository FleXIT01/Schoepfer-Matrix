"""Pydantic-Modelle für den Build-Plan, den der ArchitectAgent erzeugt."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ToolTask(BaseModel):
    """Ein vom Bot benötigtes Tool — entweder aus der Bibliothek oder zu generieren."""

    name: str                              # gültiger Python-Identifier
    description: str
    capability: str | None = None          # Bibliotheks-Key falls Treffer, z.B. "read_file"
    signature: str = ""                    # z.B. "def berechne(self, a: int, b: int) -> str"
    sample_input: dict = Field(default_factory=dict)   # für tool_gate
    needs_generation: bool = True          # True = CoderAgent, False = aus Bibliothek


class FileTask(BaseModel):
    """Eine zu erzeugende Datei des Bot-Pakets."""

    path: str                              # relativ, z.B. "bot/tools.py"
    purpose: str = ""
    depends_on: list[str] = Field(default_factory=list)


class BuildPlan(BaseModel):
    package_name: str = "bot"
    files: list[FileTask] = Field(default_factory=list)
    tools: list[ToolTask] = Field(default_factory=list)
    entrypoint: str = "bot/runner.py"

    def ordered_files(self) -> list[FileTask]:
        """Topologische Sortierung nach depends_on (stabil, zyklus-tolerant)."""
        by_path = {f.path: f for f in self.files}
        visited: set[str] = set()
        order: list[FileTask] = []

        def visit(task: FileTask, stack: set[str]) -> None:
            if task.path in visited:
                return
            stack.add(task.path)
            for dep in task.depends_on:
                dep_task = by_path.get(dep)
                if dep_task is not None and dep_task.path not in stack:
                    visit(dep_task, stack)
            stack.discard(task.path)
            visited.add(task.path)
            order.append(task)

        for f in self.files:
            visit(f, set())
        return order
