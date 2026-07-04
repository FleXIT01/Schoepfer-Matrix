"""Abstrakte Basisklasse für alle Service-Bridges.

Jeder Service (OpenClaw, agenticSeek, MaxKB, ComfyUI, etc.) erbt von
BaseService und implementiert:
  - health_check(): Ist der Service erreichbar?
  - start() / stop(): Hochfahren/Herunterfahren (Scale-to-Zero)
  - execute(): Die eigentliche Aufgabe ausführen
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ServiceStatus(enum.Enum):
    """Zustand eines Service-Containers / -Prozesses."""
    UNKNOWN = "unknown"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    DEGRADED = "degraded"  # läuft, aber mit Einschränkungen


@dataclass
class ServiceConfig:
    """Konfiguration für einen einzelnen externen Service."""
    name: str
    display_name: str = ""
    # Netzwerk
    host: str = "localhost"
    port: int = 0
    base_url: str = ""
    # Docker / Prozess
    docker_image: str = ""
    docker_compose_file: str = ""
    docker_service_name: str = ""
    start_command: str = ""
    # Verhalten
    auto_start: bool = False          # Beim Orchestrator-Start mitfahren
    scale_to_zero: bool = True        # Nach Nutzung herunterfahren
    idle_timeout_seconds: int = 300   # Nach 5 Min Inaktivität stoppen
    health_endpoint: str = "/health"
    # Kategorien (für Intent-Routing)
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    # Pfad zum lokalen Repository
    repo_path: str = ""


@dataclass
class ServiceResult:
    """Ergebnis eines Service-Aufrufs."""
    ok: bool
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    service_name: str = ""


class BaseService(ABC):
    """Abstrakte Basis für alle Service-Bridges.

    Jeder Service verwaltet seinen eigenen Lebenszyklus und bietet eine
    einheitliche Schnittstelle für den Orchestrator.
    """

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.status = ServiceStatus.UNKNOWN
        self._last_used: float = 0.0
        self._start_time: float = 0.0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def display_name(self) -> str:
        return self.config.display_name or self.config.name

    @property
    def base_url(self) -> str:
        if self.config.base_url:
            return self.config.base_url.rstrip("/")
        if self.config.port:
            return f"http://{self.config.host}:{self.config.port}"
        return f"http://{self.config.host}"

    @property
    def idle_seconds(self) -> float:
        """Wie lange der Service schon untätig ist."""
        if self._last_used <= 0:
            return 0.0
        return time.time() - self._last_used

    @property
    def uptime_seconds(self) -> float:
        """Wie lange der Service schon läuft."""
        if self._start_time <= 0:
            return 0.0
        return time.time() - self._start_time

    # --- Lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        """Startet den Service (Docker-Container, Prozess, etc.)."""
        logger.debug("Service '%s' wird gestartet…", self.name)
        self.status = ServiceStatus.STARTING
        try:
            ok = self._do_start()
            if ok:
                self.status = ServiceStatus.RUNNING
                self._start_time = time.time()
                logger.info("Service '%s' läuft.", self.name)
            else:
                self.status = ServiceStatus.ERROR
                logger.debug("Service '%s' nicht verfügbar (nicht kritisch).", self.name)
            return ok
        except Exception as exc:
            self.status = ServiceStatus.ERROR
            logger.exception("Fehler beim Starten von '%s': %s", self.name, exc)
            return False

    def stop(self) -> bool:
        """Fährt den Service herunter (Scale-to-Zero)."""
        logger.info("Service '%s' wird gestoppt…", self.name)
        try:
            ok = self._do_stop()
            self.status = ServiceStatus.STOPPED
            self._start_time = 0.0
            return ok
        except Exception as exc:
            logger.exception("Fehler beim Stoppen von '%s': %s", self.name, exc)
            return False

    def ensure_running(self, timeout_seconds: float = 20.0) -> bool:
        """Stellt sicher, dass der Service läuft. Startet ihn bei Bedarf.

        Args:
            timeout_seconds: Maximale Wartezeit für den Start (0 = sofort aufgeben).
        """
        if self.status == ServiceStatus.RUNNING and self.health_check():
            self._last_used = time.time()
            return True
        if timeout_seconds <= 0:
            return self.health_check()
        # Starte mit Timeout-Wächter
        import threading
        result = [False]
        def _start_and_check():
            result[0] = self.start()
        t = threading.Thread(target=_start_and_check, daemon=True)
        t.start()
        t.join(timeout=timeout_seconds)
        return self.status == ServiceStatus.RUNNING

    def maybe_stop_if_idle(self) -> bool:
        """Stoppt den Service, wenn er zu lange untätig war (Scale-to-Zero)."""
        if not self.config.scale_to_zero:
            return False
        if self.status != ServiceStatus.RUNNING:
            return False
        if self.idle_seconds > self.config.idle_timeout_seconds:
            logger.info(
                "Service '%s' ist seit %.0fs untätig → wird gestoppt.",
                self.name, self.idle_seconds,
            )
            return self.stop()
        return False

    # --- Kernfunktionen (von Subklassen implementiert) -----------------------

    @abstractmethod
    def health_check(self) -> bool:
        """Prüft, ob der Service erreichbar und funktionsfähig ist."""
        ...

    @abstractmethod
    def _do_start(self) -> bool:
        """Interne Start-Logik (Docker, Prozess, etc.)."""
        ...

    @abstractmethod
    def _do_stop(self) -> bool:
        """Interne Stop-Logik."""
        ...

    @abstractmethod
    def execute(self, action: str, payload: dict[str, Any] | None = None) -> ServiceResult:
        """Führt eine Aktion auf dem Service aus.

        Args:
            action: Name der Aktion (z.B. "generate_code", "search", "analyze").
            payload: Daten für die Aktion.

        Returns:
            ServiceResult mit dem Ergebnis.
        """
        ...

    # --- Hilfsmethoden -------------------------------------------------------

    def _timed_execute(self, action: str, fn, *args, **kwargs) -> ServiceResult:
        """Wrapper, der die Ausführungsdauer misst und Fehler abfängt."""
        self._last_used = time.time()
        start = time.time()
        try:
            result = fn(*args, **kwargs)
            duration = (time.time() - start) * 1000
            return ServiceResult(
                ok=True, data=result, duration_ms=duration,
                service_name=self.name,
            )
        except Exception as exc:
            duration = (time.time() - start) * 1000
            logger.debug("Service '%s' nicht erreichbar für '%s': %s", self.name, action, exc)
            return ServiceResult(
                ok=False, error=str(exc), duration_ms=duration,
                service_name=self.name,
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialisierung für die Registry und Debugging."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self.status.value,
            "base_url": self.base_url,
            "capabilities": self.config.capabilities,
            "tags": self.config.tags,
            "idle_seconds": round(self.idle_seconds, 1),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "scale_to_zero": self.config.scale_to_zero,
            "repo_path": self.config.repo_path,
        }

    def __repr__(self) -> str:
        return f"<{type(self).__name__} '{self.name}' [{self.status.value}]>"
