"""Erzeugt BUILD_REPORT.md aus dem Schleifen-Protokoll des Orchestrators."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepLog:
    step: str
    status: str            # ok | fixed | degraded | failed | skipped
    detail: str = ""
    attempts: int = 0


_STATUS_ICON = {
    "ok": "✅",
    "fixed": "🔧",
    "degraded": "⚠️",
    "failed": "❌",
    "skipped": "➖",
}


@dataclass
class BuildResult:
    ok: bool
    files: dict[str, str] = field(default_factory=dict)
    steps: list[StepLog] = field(default_factory=list)
    final_run_output: str = ""
    final_run_ok: bool | None = None
    summary: str = ""


def render_report(spec, result: BuildResult) -> str:
    lines = [
        f"# Build-Report: {spec.name}",
        "",
        f"> Erzeugt am {spec.generated_at}",
        "",
        f"**Gesamtstatus:** {'✅ erfolgreich' if result.ok else '⚠️ mit Einschränkungen'}",
        "",
        "## Verifikations-Schritte",
        "",
        "| Schritt | Status | Versuche | Detail |",
        "|---------|--------|----------|--------|",
    ]
    for s in result.steps:
        icon = _STATUS_ICON.get(s.status, s.status)
        detail = (s.detail or "").replace("\n", " ").replace("|", "\\|")
        if len(detail) > 160:
            detail = detail[:160] + "…"
        lines.append(f"| {s.step} | {icon} {s.status} | {s.attempts or ''} | {detail} |")

    lines += ["", "## Finaler Lauf (echtes Modell)", ""]
    if result.final_run_ok is None:
        lines.append("_Übersprungen (deaktiviert oder kein Modell verfügbar)._")
    elif result.final_run_ok:
        lines += [
            "Der Bot wurde gegen das echte lokale Modell getestet. Beispiel-Antwort:",
            "",
            "```",
            (result.final_run_output or "").strip()[:2000],
            "```",
        ]
    else:
        lines += [
            "⚠️ Der finale echte Lauf war nicht erfolgreich (Modell nicht erreichbar oder Fehler):",
            "",
            "```",
            (result.final_run_output or "").strip()[:2000],
            "```",
        ]

    lines += [
        "",
        "## So startest du den Bot",
        "",
        "```bash",
        "pip install -r requirements.txt",
        "python run.py",
        "```",
        "",
        "Offline-Selbsttest (ohne Modell):",
        "",
        "```bash",
        "python test_smoke.py",
        "```",
        "",
    ]
    return "\n".join(lines)
