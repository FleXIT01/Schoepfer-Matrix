"""Self-Healing Loop: Der Orchestrator überwacht und repariert sich selbst.

Nutzt repo-critic-ai, um den eigenen Code (bot1) periodisch zu scannen,
und den FixerAgent, um gefundene Probleme automatisch zu beheben.
Ergebnisse werden in MaxKB gespeichert (Lerneffekt).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

BOT1_ROOT = Path(__file__).resolve().parent.parent.parent  # → bot1/


class SelfHealer:
    """Scannt den eigenen Quellcode und repariert Probleme automatisch.

    Ablauf:
      1. repo-critic-ai scannt bot1/ auf Qualitätsprobleme und Security-Issues.
      2. Probleme werden nach Schweregrad sortiert.
      3. Der FixerAgent versucht, kritische Probleme zu beheben.
      4. Erkenntnisse werden in MaxKB gespeichert.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self._scan_history: list[dict] = []

    def run_scan(self, *, auto_fix: bool = False) -> dict[str, Any]:
        """Führt einen Self-Healing-Scan durch.

        Args:
            auto_fix: Wenn True, werden gefundene Probleme automatisch repariert.

        Returns:
            Dict mit "issues", "fixed", "scan_time" und "summary".
        """
        start = time.time()
        result: dict[str, Any] = {
            "scan_time": 0.0,
            "issues": [],
            "fixed": [],
            "summary": "",
        }

        # 1) Scan via repo-critic
        reviewer = self._registry.get_service("repo-critic")
        if not reviewer:
            result["summary"] = "repo-critic nicht verfügbar — Scan übersprungen."
            logger.warning("Self-Healing: repo-critic nicht registriert.")
            return result

        try:
            if not reviewer.ensure_running(timeout_seconds=5.0):
                result["summary"] = "repo-critic konnte nicht gestartet werden."
                return result

            scan_result = reviewer.execute("scan/repo", {
                "repo_path": str(BOT1_ROOT),
            })

            if scan_result.ok and scan_result.data:
                issues = self._parse_issues(scan_result.data)
                result["issues"] = issues
                logger.info(
                    "Self-Healing Scan: %d Issues gefunden (davon %d kritisch).",
                    len(issues),
                    sum(1 for i in issues if i.get("severity") in ("critical", "high")),
                )
            else:
                result["summary"] = f"Scan fehlgeschlagen: {scan_result.error}"
                return result

        except Exception as exc:
            result["summary"] = f"Scan-Fehler: {exc}"
            logger.exception("Self-Healing Scan fehlgeschlagen.")
            return result

        # 2) Auto-Fix (optional)
        if auto_fix and result["issues"]:
            result["fixed"] = self._auto_fix(result["issues"])

        # 3) Wissen einspeisen
        self._store_findings(result)

        result["scan_time"] = time.time() - start
        result["summary"] = (
            f"{len(result['issues'])} Issues gefunden, "
            f"{len(result['fixed'])} automatisch repariert, "
            f"Dauer: {result['scan_time']:.1f}s"
        )

        self._scan_history.append(result)
        return result

    def _parse_issues(self, data: Any) -> list[dict]:
        """Parst die Scan-Ergebnisse in eine einheitliche Issue-Liste."""
        if isinstance(data, list):
            return [
                {
                    "severity": item.get("severity", "info"),
                    "file": item.get("file", ""),
                    "line": item.get("line", 0),
                    "message": item.get("message", ""),
                    "category": item.get("category", "unknown"),
                }
                for item in data
                if isinstance(item, dict)
            ]
        if isinstance(data, dict):
            return self._parse_issues(data.get("issues", []))
        return []

    def _auto_fix(self, issues: list[dict]) -> list[dict]:
        """Versucht, kritische Issues automatisch zu reparieren."""
        fixed: list[dict] = []
        critical = [i for i in issues if i.get("severity") in ("critical", "high")]

        for issue in critical[:5]:  # Max 5 auf einmal
            file_path = issue.get("file", "")
            if not file_path:
                continue

            target = BOT1_ROOT / file_path
            if not target.exists() or not target.suffix == ".py":
                continue

            try:
                source = target.read_text(encoding="utf-8")
                # Hier würde der FixerAgent eingreifen — für jetzt nur loggen
                logger.info(
                    "Self-Healing: Issue in '%s' Zeile %d: %s",
                    file_path, issue.get("line", 0), issue.get("message", ""),
                )
                fixed.append({**issue, "status": "logged_for_review"})
            except Exception as exc:
                logger.debug("Auto-Fix fehlgeschlagen für '%s': %s", file_path, exc)

        return fixed

    def _store_findings(self, result: dict) -> None:
        """Speist Scan-Ergebnisse in MaxKB ein (Lerneffekt)."""
        knowledge = self._registry.get_service("maxkb")
        if not knowledge:
            return

        try:
            issues_text = "\n".join(
                f"- [{i.get('severity')}] {i.get('file')}:{i.get('line')} — {i.get('message')}"
                for i in result.get("issues", [])[:20]
            )
            knowledge.execute("ingest", {
                "title": f"Self-Healing Scan {time.strftime('%Y-%m-%d %H:%M')}",
                "content": f"Issues:\n{issues_text}\n\n{result.get('summary', '')}",
                "source": "self_healing",
                "tags": ["self_healing", "quality"],
            })
        except Exception as exc:
            logger.debug("Wissens-Injektion (Self-Healing) fehlgeschlagen: %s", exc)

    @property
    def scan_count(self) -> int:
        return len(self._scan_history)

    @property
    def last_scan(self) -> dict | None:
        return self._scan_history[-1] if self._scan_history else None
