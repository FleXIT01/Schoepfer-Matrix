"""Docker-Control-Service: das 'ai_agent_0' der Matrix.

Steuert die lokalen Docker-Container des Ökosystems (MaxKB, ComfyUI,
SuperAGI, etc.) — auflisten, starten, stoppen. Anders als die anderen
Services ist dies kein HTTP-Server, sondern ein Controller, der die
Docker-CLI bedient. Damit kann der Orchestrator Schwer-Services
bedarfsgerecht hoch- und herunterfahren (Scale-to-Zero auf Infra-Ebene).

Lokaler Pfad: n:\\allinall\\ai_agent_0
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any

from .base_service import BaseService, ServiceConfig, ServiceResult, ServiceStatus

logger = logging.getLogger(__name__)


def create_docker_config(repo_path: str = r"n:\allinall\ai_agent_0") -> ServiceConfig:
    return ServiceConfig(
        name="docker-control",
        display_name="ai_agent_0 (Docker Container Control)",
        auto_start=False,
        scale_to_zero=False,  # ein Controller, kein Verbraucher
        capabilities=[
            "container_management", "docker_ps", "docker_start",
            "docker_stop", "infrastructure", "orchestration",
        ],
        tags=["core", "infrastructure", "docker"],
        repo_path=repo_path,
    )


class DockerControlService(BaseService):
    """Bedient die Docker-CLI, um Container des Ökosystems zu verwalten."""

    def __init__(self, repo_path: str = r"n:\allinall\ai_agent_0") -> None:
        super().__init__(create_docker_config(repo_path))

    # --- Lifecycle ----------------------------------------------------------

    def health_check(self) -> bool:
        """Ist die Docker-Engine erreichbar?"""
        ok = self._docker(["info", "--format", "{{.ServerVersion}}"]).get("ok", False)
        self.status = ServiceStatus.RUNNING if ok else ServiceStatus.STOPPED
        return ok

    def _do_start(self) -> bool:
        # Ein Controller startet keinen eigenen Prozess — er prüft nur die Engine.
        return self.health_check()

    def _do_stop(self) -> bool:
        return True

    # --- Kernaktionen -------------------------------------------------------

    def execute(self, action: str, payload: dict[str, Any] | None = None) -> ServiceResult:
        payload = payload or {}
        self._last_used = __import__("time").time()
        action = action.lower().strip()

        if action in ("ps", "list", "status"):
            return self._wrap(self.list_containers(all_containers=payload.get("all", True)))
        if action in ("start", "up"):
            return self._wrap(self.start_container(payload.get("name", "")))
        if action in ("stop", "down"):
            return self._wrap(self.stop_container(payload.get("name", "")))
        if action == "run":
            return self._wrap(self.run_container(
                payload.get("image", ""),
                name=payload.get("name", ""),
                ports=payload.get("ports", ""),
                detach=payload.get("detach", True),
            ))
        if action in ("logs",):
            return self._wrap(self._docker(["logs", "--tail", "50", payload.get("name", "")]))
        return ServiceResult(ok=False, error=f"Unbekannte Docker-Aktion '{action}'",
                             service_name=self.name)

    # --- High-Level-Helfer --------------------------------------------------

    def list_containers(self, *, all_containers: bool = True) -> dict[str, Any]:
        args = ["ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]
        if all_containers:
            args.append("-a")
        res = self._docker(args)
        if not res["ok"]:
            return res
        containers = []
        for line in res["stdout"].splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                containers.append({
                    "name": parts[0], "image": parts[1],
                    "status": parts[2], "ports": parts[3] if len(parts) > 3 else "",
                })
        return {"ok": True, "containers": containers, "count": len(containers)}

    def start_container(self, name: str) -> dict[str, Any]:
        if not name:
            return {"ok": False, "error": "Kein Container-Name angegeben"}
        return self._docker(["start", name])

    def stop_container(self, name: str) -> dict[str, Any]:
        if not name:
            return {"ok": False, "error": "Kein Container-Name angegeben"}
        return self._docker(["stop", name])

    def run_container(self, image: str, *, name: str = "", ports: str = "",
                      detach: bool = True) -> dict[str, Any]:
        if not image:
            return {"ok": False, "error": "Kein Image angegeben"}
        args = ["run"]
        if detach:
            args.append("-d")
        if name:
            args += ["--name", name]
        if ports:
            args += ["-p", ports]
        args.append(image)
        return self._docker(args, timeout=180)

    # --- Low-Level ----------------------------------------------------------

    @staticmethod
    def _docker(args: list[str], *, timeout: int = 60) -> dict[str, Any]:
        """Führt einen docker-Befehl aus und liefert ein Ergebnis-Dict."""
        try:
            proc = subprocess.run(
                ["docker", *args],
                capture_output=True, text=True, timeout=timeout,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip()[:500],
                "returncode": proc.returncode,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "Docker ist nicht installiert oder nicht im PATH"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Docker-Befehl überschritt {timeout}s Timeout"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def _wrap(self, data: dict[str, Any]) -> ServiceResult:
        return ServiceResult(
            ok=data.get("ok", False),
            data=data,
            error=data.get("error", "") or data.get("stderr", ""),
            service_name=self.name,
        )
