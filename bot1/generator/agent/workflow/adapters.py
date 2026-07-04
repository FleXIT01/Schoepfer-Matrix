import logging
from abc import ABC, abstractmethod
from typing import Any
from .models import Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

def compress_context(context: dict[str, Any], max_len: int = 2000) -> dict[str, Any]:
    """Komprimiert Kontext zwischen Agents, um wachsende Kontextfenster zu vermeiden."""
    compressed = {}
    for k, v in context.items():
        if isinstance(v, str) and len(v) > max_len:
            compressed[k] = v[:max_len] + "... [truncated]"
        elif isinstance(v, list) and len(v) > 10:
            compressed[k] = v[:10] + ["... [truncated list]"]
        else:
            compressed[k] = v
    return compressed

class BaseAdapter(ABC):
    def __init__(self, registry=None):
        self.registry = registry

    @abstractmethod
    def run(self, task: Task, context: dict[str, Any]) -> TaskResult:
        """Führt den Task aus. Muss ein standardisiertes TaskResult zurückgeben."""
        pass

class ResearchAdapter(BaseAdapter):
    def run(self, task: Task, context: dict[str, Any]) -> TaskResult:
        query = task.input_data.get("query", "Allgemeine Recherche")
        logger.info(f"ResearchAdapter: Recherchiere '{query}'")
        
        # 1. Crash Simulator
        if task.input_data.get("_crash_test") is True:
            logger.error("Absichtlicher Crash im ResearchAdapter!")
            raise RuntimeError("crash test")
            
        # 2. Idempotenz-Check
        # In the real world, this would check a Redis key or DB constraint
        idempotency_key = f"research_{task.id}_{task.retries}"
        
        # 3. Simulate work
        import time
        time.sleep(0.1) # Simulate network call
        
        return TaskResult(
            status=TaskStatus.COMPLETED,
            output=f"Recherche-Ergebnis für: {query} (Key: {idempotency_key})",
            artifacts={"summary.md": f"Dies ist der Bericht für {query}."}
        )

class ReviewAdapter(BaseAdapter):
    def run(self, task: Task, context: dict[str, Any]) -> TaskResult:
        content = task.input_data.get("content", "")
        logger.info("ReviewAdapter: Prüfe Inhalte")
        
        # Crash Simulator
        if task.input_data.get("_crash_test") is True:
            raise RuntimeError("crash test")
            
        import time
        time.sleep(0.1) # Simulate review processing
        
        return TaskResult(
            status=TaskStatus.COMPLETED,
            output="Review erfolgreich bestanden. Inhalt wirkt plausibel."
        )

class BotGenerationAdapter(BaseAdapter):
    def run(self, task: Task, context: dict[str, Any]) -> TaskResult:
        spec_dict = task.input_data.get("spec", {})
        logger.info(f"BotGenerationAdapter: Erzeuge Bot aus Spec {spec_dict.get('name')}")
        
        return TaskResult(
            status=TaskStatus.WAITING_FOR_APPROVAL,
            output="Bot-Plan erstellt. Warte auf Human Approval vor dem Deployment."
        )

class NoopAdapter(BaseAdapter):
    def run(self, task: Task, context: dict[str, Any]) -> TaskResult:
        logger.info(f"NoopAdapter: Führe aus für Task {task.id}")
        return TaskResult(status=TaskStatus.COMPLETED, output="Noop executed")
