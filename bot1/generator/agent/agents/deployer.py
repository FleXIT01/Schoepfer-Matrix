"""DeployAgent: bringt generierte Projekte live.

Nutzt shell_gpt für Docker/CLI-Operationen, das firebase-Plugin für
Cloud-Deployment, das android-cli-Plugin für mobile Apps und die
Messenger-Services für Benachrichtigungen nach erfolgreicher Auslieferung.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DeployAgent(BaseAgent):
    """Agent für Deployment, DevOps und Auslieferung.

    Wird vom Orchestrator aufgerufen, wenn:
      - Ein fertiges Projekt in Docker verpackt werden muss
      - Eine Web-App auf Firebase deployt werden soll
      - Eine Android-APK kompiliert werden muss
      - Der Nutzer über das Ergebnis benachrichtigt werden soll
    """

    def deploy_local(self, project_dir: str, *, port: int = 8080) -> dict[str, Any]:
        """Deployt ein Projekt lokal via Docker."""
        if not self.has_registry:
            return self._deploy_via_llm(project_dir, "docker")

        # 1) Prüfe Ressourcen über local-llm-planner
        planner = self.registry.get_service("llm-planner")
        if planner:
            try:
                resources = planner.execute("check", {"model": "deployment"})
                if resources.ok:
                    logger.info("Ressourcen-Check: %s", resources.data)
            except Exception:
                pass

        # 2) Generiere Dockerfile via LLM, falls keins existiert
        dockerfile_path = Path(project_dir) / "Dockerfile"
        if not dockerfile_path.exists():
            dockerfile_content = self._generate_dockerfile(project_dir)
            if dockerfile_content:
                dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
                logger.info("Dockerfile generiert: %s", dockerfile_path)

        # 3) Baue und starte den Container via shell_gpt
        return self._run_shell_command(
            f"docker build -t omega-deploy {project_dir} && "
            f"docker run -d -p {port}:{port} omega-deploy"
        )

    def deploy_firebase(self, project_dir: str, *, project_id: str = "") -> dict[str, Any]:
        """Deployt eine Web-App auf Firebase Hosting."""
        if not self.has_registry:
            return {"error": "Firebase-Deployment benötigt AI-OS Registry."}

        # Firebase CLI Befehle generieren und ausführen
        commands = [
            f"cd {project_dir}",
            "npm run build" if (Path(project_dir) / "package.json").exists() else "echo 'Kein npm-Projekt'",
            f"firebase deploy --project {project_id}" if project_id else "firebase deploy",
        ]
        return self._run_shell_command(" && ".join(commands))

    def deploy_android(self, project_dir: str) -> dict[str, Any]:
        """Kompiliert eine Android-APK via android-cli-plugin."""
        if not self.has_registry:
            return {"error": "Android-Deployment benötigt AI-OS Registry."}

        return self._run_shell_command(
            f"cd {project_dir} && ./gradlew assembleDebug"
        )

    def notify_completion(self, task_name: str, result: str, *,
                          platforms: list[str] | None = None) -> bool:
        """Benachrichtigt den Nutzer über die Fertigstellung."""
        if not self.has_registry:
            logger.info("Task '%s' abgeschlossen: %s", task_name, result[:200])
            return True

        messenger = self.registry.get_service("langbot")
        if messenger and messenger.ensure_running(timeout_seconds=3.0):
            try:
                notify_result = messenger.execute("notify", {
                    "task_name": task_name,
                    "result_summary": result[:500],
                    "platforms": platforms or ["whatsapp"],
                })
                return notify_result.ok
            except Exception as exc:
                logger.debug("Benachrichtigung fehlgeschlagen: %s", exc)

        return False

    def _generate_dockerfile(self, project_dir: str) -> str:
        """Generiert ein Dockerfile via LLM basierend auf dem Projektinhalt."""
        from ...llm.base import LLMMessage

        # Sammle Projektinfo
        project_path = Path(project_dir)
        files = [f.name for f in project_path.iterdir() if f.is_file()][:20]

        messages = [LLMMessage(
            role="user",
            content=(
                f"Erstelle ein minimales, produktionsreifes Dockerfile für dieses Projekt.\n"
                f"Dateien im Projekt: {', '.join(files)}\n"
                f"Gib NUR das Dockerfile zurück, keine Erklärung."
            ),
        )]
        try:
            raw = self._llm.chat(messages=messages, temperature=0.1)
            # Extrahiere Dockerfile-Inhalt
            if "FROM " in raw:
                start = raw.index("FROM ")
                return raw[start:].strip()
            return raw.strip()
        except Exception as exc:
            logger.warning("Dockerfile-Generierung fehlgeschlagen: %s", exc)
            return ""

    def _run_shell_command(self, command: str) -> dict[str, Any]:
        """Führt einen Shell-Befehl aus (via shell_gpt oder subprocess)."""
        import subprocess
        try:
            proc = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=120,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout[-2000:],
                "stderr": proc.stderr[-1000:],
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout nach 120s"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _deploy_via_llm(self, project_dir: str, target: str) -> dict[str, Any]:
        """Fallback: LLM generiert Deployment-Anweisungen."""
        from ...llm.base import LLMMessage
        messages = [LLMMessage(
            role="user",
            content=f"Erstelle Deployment-Befehle für {target}, Projekt in: {project_dir}",
        )]
        try:
            raw = self._llm.chat(messages=messages, temperature=0.2)
            return {"instructions": raw, "automated": False}
        except Exception as exc:
            return {"error": str(exc)}
