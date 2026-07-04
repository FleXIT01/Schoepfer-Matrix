"""HTTP-basierter Service: Basis für alle REST/API-basierten Services.

Die meisten der 36 Repositories (OpenClaw, MaxKB, agenticSeek, etc.)
kommunizieren über HTTP-APIs. Diese Klasse kapselt die gemeinsame
HTTP-Logik (Retries, Timeouts, Health-Checks).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .base_service import BaseService, ServiceConfig, ServiceResult, ServiceStatus

logger = logging.getLogger(__name__)


class HttpService(BaseService):
    """Basis für alle HTTP/REST-basierten Service-Bridges.

    Stellt httpx-Client-Management, Health-Checks über HTTP und
    eine generische execute()-Methode für POST/GET-Aufrufe bereit.
    """

    def __init__(self, config: ServiceConfig, *, timeout: float = 120.0) -> None:
        super().__init__(config)
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def health_check(self) -> bool:
        """HTTP GET auf den Health-Endpunkt."""
        try:
            resp = self.client.get(self.config.health_endpoint)
            return resp.status_code < 500
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            return False

    def _do_start(self) -> bool:
        """Für HTTP-Services: Prüfe ob erreichbar, starte Docker/Prozess falls nötig."""
        if self.health_check():
            return True

        # Polling-Limit: max 5 Versuche à 1s = 5s
        max_polls = 5

        # Versuche Docker-Start, falls konfiguriert
        if self.config.docker_compose_file and self.config.docker_service_name:
            import subprocess
            try:
                check = subprocess.run(
                    ["docker", "info"], capture_output=True, timeout=2,
                )
                if check.returncode != 0:
                    logger.debug("Docker nicht verfügbar für '%s'", self.name)
                    return False
                subprocess.run(
                    ["docker", "compose", "-f", self.config.docker_compose_file,
                     "up", "-d", self.config.docker_service_name],
                    capture_output=True, text=True, timeout=30,
                )
                for _ in range(max_polls):
                    time.sleep(1)
                    if self.health_check():
                        return True
            except Exception as exc:
                logger.debug("Docker-Start für '%s' fehlgeschlagen: %s", self.name, exc)

        # Versuche direkten Prozess-Start
        if self.config.start_command:
            import subprocess
            try:
                subprocess.Popen(
                    self.config.start_command,
                    shell=True,
                    cwd=self.config.repo_path or None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for _ in range(max_polls):
                    time.sleep(1)
                    if self.health_check():
                        return True
            except Exception as exc:
                logger.debug("Prozess-Start für '%s' fehlgeschlagen: %s", self.name, exc)

        return self.health_check()

    def _do_stop(self) -> bool:
        """Stoppt den Docker-Container oder Prozess."""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None

        if self.config.docker_compose_file and self.config.docker_service_name:
            import subprocess
            try:
                subprocess.run(
                    ["docker", "compose", "-f", self.config.docker_compose_file,
                     "stop", self.config.docker_service_name],
                    capture_output=True, text=True, timeout=30,
                )
                return True
            except Exception as exc:
                logger.warning("Docker-Stop für '%s' fehlgeschlagen: %s", self.name, exc)
        return True

    def execute(self, action: str, payload: dict[str, Any] | None = None) -> ServiceResult:
        """Generische Ausführung: POST auf /{action} mit JSON-Body."""
        return self._timed_execute(action, self._do_execute, action, payload)

    def _do_execute(self, action: str, payload: dict[str, Any] | None) -> Any:
        endpoint = f"/{action.strip('/')}"
        resp = self.client.post(endpoint, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, **params) -> Any:
        """Convenience: GET-Anfrage."""
        resp = self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict | None = None) -> Any:
        """Convenience: POST-Anfrage."""
        resp = self.client.post(path, json=data or {})
        resp.raise_for_status()
        return resp.json()

    def __del__(self):
        if self._client and not self._client.is_closed:
            self._client.close()
