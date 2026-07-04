from __future__ import annotations

import abc

from generator.cli.interface import CLI
from generator.llm.base import LLMAdapter

class GeneratorMode(abc.ABC):
    """Abstract base class for a generator mode."""
    
    @abc.abstractmethod
    def run(self, cli: CLI, llm: LLMAdapter) -> None:
        """Executes the generator mode."""
        pass
