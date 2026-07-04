"""Dynamische Service-Registry: der ClawHub-Ersatz.

Ersetzt die statische `library.py` (6 hartcodierte Tools) durch ein
dynamisches System, das:
  1. Lokale Tool-Bibliotheken (read_file, run_python, etc.) registriert.
  2. Externe Services (OpenClaw, agenticSeek, MaxKB, etc.) registriert.
  3. Services nach Capability/Tag/Name auflöst (Intent-Routing).
  4. Scale-to-Zero für alle Services verwaltet.
  5. Sich selbst erweitert: neue Skills werden zur Laufzeit registriert.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base_service import BaseService, ServiceConfig, ServiceResult, ServiceStatus

logger = logging.getLogger(__name__)


@dataclass
class SkillEntry:
    """Ein registrierter Skill (lokal oder remote).

    Skills sind die atomaren Fähigkeiten des Systems. Sie können
    direkte Python-Funktionen (wie die alte library.py), API-Endpunkte
    auf externen Services, oder generierte Agenten-Fähigkeiten sein.
    """
    name: str
    description: str = ""
    # Quelle
    source_type: str = "local"    # "local" | "service" | "generated"
    service_name: str = ""        # Name des zugehörigen Service
    action: str = ""              # API-Action auf dem Service
    # Für lokale Tools
    func_source: str = ""         # Python-Quelltext
    func_ref: Any = None          # Direkte Funktionsreferenz
    # Metadaten
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    sample_input: dict = field(default_factory=dict)
    definition: dict = field(default_factory=dict)
    # Statistik
    call_count: int = 0
    last_used: float = 0.0
    avg_duration_ms: float = 0.0


class ServiceRegistry:
    """Zentrales Verzeichnis aller Services und Skills.

    Fungiert als der „ClawHub" des Systems. Der Orchestrator fragt:
    „Wer kann X?" und bekommt den besten Service/Skill zurück.
    """

    def __init__(self) -> None:
        self._services: dict[str, BaseService] = {}
        self._skills: dict[str, SkillEntry] = {}
        self._lock = threading.Lock()
        self._idle_checker_running = False

    # ─── Service-Management ──────────────────────────────────────────────

    def register_service(self, service: BaseService) -> None:
        """Registriert einen externen Service (z.B. OpenClaw, ComfyUI)."""
        with self._lock:
            self._services[service.name] = service
            logger.debug(
                "Service registriert: '%s' (%s) — Capabilities: %s",
                service.name, service.display_name,
                ", ".join(service.config.capabilities) or "keine",
            )

    def unregister_service(self, name: str) -> None:
        """Entfernt einen Service und alle zugehörigen Skills."""
        with self._lock:
            if name in self._services:
                del self._services[name]
            # Zugehörige Skills entfernen
            to_remove = [
                k for k, v in self._skills.items() if v.service_name == name
            ]
            for k in to_remove:
                del self._skills[k]

    def get_service(self, name: str) -> BaseService | None:
        """Holt einen Service by Name."""
        return self._services.get(name)

    def get_services_by_capability(self, capability: str) -> list[BaseService]:
        """Findet alle Services, die eine bestimmte Fähigkeit haben."""
        return [
            s for s in self._services.values()
            if capability in s.config.capabilities
        ]

    def get_services_by_tag(self, tag: str) -> list[BaseService]:
        """Findet alle Services mit einem bestimmten Tag."""
        return [
            s for s in self._services.values()
            if tag in s.config.tags
        ]

    @property
    def all_services(self) -> list[BaseService]:
        return list(self._services.values())

    @property
    def running_services(self) -> list[BaseService]:
        return [
            s for s in self._services.values()
            if s.status == ServiceStatus.RUNNING
        ]

    # ─── Skill-Management ────────────────────────────────────────────────

    def register_skill(self, skill: SkillEntry) -> None:
        """Registriert einen Skill (lokal, remote, oder generiert)."""
        with self._lock:
            self._skills[skill.name] = skill
            logger.debug(
                "Skill registriert: '%s' [%s] — %s",
                skill.name, skill.source_type, skill.description[:80],
            )

    def unregister_skill(self, name: str) -> None:
        with self._lock:
            self._skills.pop(name, None)

    def get_skill(self, name: str) -> SkillEntry | None:
        return self._skills.get(name)

    def find_skills(
        self,
        *,
        capability: str | None = None,
        tag: str | None = None,
        source_type: str | None = None,
    ) -> list[SkillEntry]:
        """Findet Skills nach Kriterien."""
        results = list(self._skills.values())
        if capability:
            results = [s for s in results if capability in s.capabilities]
        if tag:
            results = [s for s in results if tag in s.tags]
        if source_type:
            results = [s for s in results if s.source_type == source_type]
        return results

    @property
    def all_skills(self) -> list[SkillEntry]:
        return list(self._skills.values())

    def skill_catalog(self) -> str:
        """Menschenlesbarer Katalog aller Skills (für Agent-Prompts)."""
        lines: list[str] = []
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            source = f"[{skill.source_type}]"
            if skill.service_name:
                source += f" via {skill.service_name}"
            lines.append(f"- {skill.name} {source} — {skill.description}")
        return "\n".join(lines) or "(keine Skills registriert)"

    # ─── Execution Pipeline ──────────────────────────────────────────────

    def execute_skill(self, name: str, payload: dict[str, Any] | None = None) -> ServiceResult:
        """Führt einen Skill aus — unabhängig davon, ob lokal oder remote.

        Für lokale Skills: Direkte Funktionsausführung.
        Für Service-Skills: Stellt sicher, dass der Service läuft, dann API-Call.
        """
        skill = self._skills.get(name)
        if skill is None:
            return ServiceResult(
                ok=False, error=f"Skill '{name}' nicht gefunden.",
                service_name="registry",
            )

        start = time.time()

        if skill.source_type == "local" and skill.func_ref is not None:
            # Lokaler Aufruf (wie die alte library.py)
            try:
                result = skill.func_ref(**(payload or {}))
                duration = (time.time() - start) * 1000
                self._update_skill_stats(name, duration)
                return ServiceResult(
                    ok=True, data=result, duration_ms=duration,
                    service_name="local",
                )
            except Exception as exc:
                duration = (time.time() - start) * 1000
                return ServiceResult(
                    ok=False, error=str(exc), duration_ms=duration,
                    service_name="local",
                )

        if skill.service_name:
            # Remote-Aufruf über den zugehörigen Service
            service = self._services.get(skill.service_name)
            if service is None:
                return ServiceResult(
                    ok=False,
                    error=f"Service '{skill.service_name}' für Skill '{name}' nicht registriert.",
                    service_name=skill.service_name,
                )
            if not service.ensure_running(timeout_seconds=5.0):
                return ServiceResult(
                    ok=False,
                    error=f"Service '{skill.service_name}' konnte nicht gestartet werden.",
                    service_name=skill.service_name,
                )
            result = service.execute(skill.action or name, payload)
            duration = (time.time() - start) * 1000
            self._update_skill_stats(name, duration)
            return result

        return ServiceResult(
            ok=False,
            error=f"Skill '{name}' hat weder func_ref noch service_name.",
            service_name="registry",
        )

    def _update_skill_stats(self, name: str, duration_ms: float) -> None:
        skill = self._skills.get(name)
        if skill:
            skill.call_count += 1
            skill.last_used = time.time()
            # Gleitender Durchschnitt
            if skill.avg_duration_ms <= 0:
                skill.avg_duration_ms = duration_ms
            else:
                skill.avg_duration_ms = 0.8 * skill.avg_duration_ms + 0.2 * duration_ms

    # ─── Scale-to-Zero Management ────────────────────────────────────────

    def check_idle_services(self) -> list[str]:
        """Prüft alle Services und stoppt diejenigen, die zu lange untätig sind."""
        stopped: list[str] = []
        for service in list(self._services.values()):
            if service.maybe_stop_if_idle():
                stopped.append(service.name)
        return stopped

    def start_idle_checker(self, interval_seconds: int = 60) -> None:
        """Startet einen Hintergrund-Thread für Scale-to-Zero."""
        if self._idle_checker_running:
            return

        def _checker():
            self._idle_checker_running = True
            while self._idle_checker_running:
                stopped = self.check_idle_services()
                if stopped:
                    logger.info("Idle-Checker hat gestoppt: %s", ", ".join(stopped))
                time.sleep(interval_seconds)

        t = threading.Thread(target=_checker, daemon=True, name="idle-checker")
        t.start()

    def stop_idle_checker(self) -> None:
        self._idle_checker_running = False

    # ─── Legacy-Kompatibilität (library.py) ──────────────────────────────

    def load_legacy_library(self) -> None:
        """Importiert die bestehenden 6 Tools aus der alten library.py als Skills."""
        try:
            from ..tools import library
            for cap_key, entry in library.LIBRARY.items():
                self.register_skill(SkillEntry(
                    name=entry.name,
                    description=entry.definition.get("description", ""),
                    source_type="local",
                    func_source=entry.func_source,
                    capabilities=[cap_key],
                    tags=["legacy", "library"],
                    sample_input=dict(entry.sample_input),
                    definition=dict(entry.definition),
                ))
            logger.info(
                "Legacy-Bibliothek geladen: %d Tools", len(library.LIBRARY),
            )
        except ImportError:
            logger.warning("Legacy-Bibliothek konnte nicht geladen werden.")

    # ─── Introspection ───────────────────────────────────────────────────

    def status_report(self) -> dict[str, Any]:
        """Vollständiger Status-Report für Monitoring/Debugging."""
        return {
            "services": {
                "total": len(self._services),
                "running": len(self.running_services),
                "details": [s.to_dict() for s in self._services.values()],
            },
            "skills": {
                "total": len(self._skills),
                "by_source": {
                    "local": len([s for s in self._skills.values() if s.source_type == "local"]),
                    "service": len([s for s in self._skills.values() if s.source_type == "service"]),
                    "generated": len([s for s in self._skills.values() if s.source_type == "generated"]),
                },
                "most_used": sorted(
                    [{"name": s.name, "calls": s.call_count, "avg_ms": round(s.avg_duration_ms, 1)}
                     for s in self._skills.values() if s.call_count > 0],
                    key=lambda x: x["calls"], reverse=True,
                )[:10],
            },
        }

    def __repr__(self) -> str:
        return (
            f"<ServiceRegistry services={len(self._services)} "
            f"skills={len(self._skills)} "
            f"running={len(self.running_services)}>"
        )
