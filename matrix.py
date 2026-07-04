"""matrix.py — zentrales CLI der Schöpfer-Matrix (V24).

Ein Einstiegspunkt statt verstreuter .cmd/.ps1-Aufrufe. Die Befehle delegieren
bewusst an die getesteten Skripte (kein Duplikat der Logik):

    python matrix.py up          # alles starten (gateway.cmd)
    python matrix.py stop        # alles stoppen (stop_all.ps1)
    python matrix.py status      # Gesamtstatus (health.ps1)
    python matrix.py eval        # Golden-Suite gegen Baseline (run_eval.cmd)
    python matrix.py backup      # Sofort-Backup (backup.cmd)
    python matrix.py briefing    # Morgenbriefing jetzt senden
    python matrix.py retro       # Wochen-Retro jetzt ausführen
    python matrix.py budget      # Tool-Kontextbudget messen
    python matrix.py logs        # die wichtigsten Logs (letzte Zeilen)

Nur Python-Standardbibliothek. Windows-only (wie das Gesamtsystem).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str], **kw) -> int:
    """Startet einen Befehl im ROOT und reicht Ein-/Ausgabe durch."""
    return subprocess.call(cmd, cwd=str(ROOT), **kw)


def _cmd_script(name: str, *args: str) -> int:
    return _run(["cmd", "/c", str(ROOT / name), *args])


def _ps_script(name: str, *args: str) -> int:
    return _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ROOT / name), *args])


def cmd_up(_: argparse.Namespace) -> int:
    # Eigenes Fenster: gateway.cmd blockiert (Supervisor-Loop) und gehört sichtbar.
    subprocess.Popen(["cmd", "/c", "start", "Schoepfer-Matrix",
                      str(ROOT / "gateway.cmd")], cwd=str(ROOT))
    print("[matrix] gateway.cmd in eigenem Fenster gestartet — Bot in ~1 Minute online.")
    print("[matrix] Stoppen: Strg+C im Gateway-Fenster oder `python matrix.py stop`.")
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    return _ps_script("stop_all.ps1")


def cmd_status(_: argparse.Namespace) -> int:
    return _ps_script("health.ps1")


def cmd_eval(ns: argparse.Namespace) -> int:
    return _cmd_script("run_eval.cmd", *ns.args)


def cmd_backup(_: argparse.Namespace) -> int:
    return _cmd_script("backup.cmd")


def cmd_briefing(_: argparse.Namespace) -> int:
    return _cmd_script("briefing.cmd")


def cmd_retro(_: argparse.Namespace) -> int:
    return _cmd_script("retro.cmd")


def cmd_budget(_: argparse.Namespace) -> int:
    return _run([sys.executable, str(ROOT / "eval" / "tool_budget.py")])


def cmd_logs(_: argparse.Namespace) -> int:
    out = ROOT / "openclaw-workspace" / "output"
    logs = [
        ("Watchdog", out / "watchdog.log", 6),
        ("Backup", out / "backup.log", 4),
        ("Golden-Eval", ROOT / "eval" / "results" / "nightly_golden.log", 8),
        ("Retro", out / "retro.log", 6),
    ]
    for title, path, n in logs:
        print(f"\n── {title} ({path.name}) " + "─" * max(1, 46 - len(title)))
        if not path.exists():
            print("  (noch kein Log)")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-n:]:
            print("  " + line)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="matrix", description="Schöpfer-Matrix — zentrales CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("up", help="alles starten (Gateway + Stack)").set_defaults(fn=cmd_up)
    sub.add_parser("stop", help="alles stoppen").set_defaults(fn=cmd_stop)
    sub.add_parser("status", help="Gesamtstatus anzeigen").set_defaults(fn=cmd_status)
    p_eval = sub.add_parser("eval", help="Golden-Suite gegen Baseline")
    p_eval.add_argument("args", nargs="*", help="z.B. g01 g02 oder --profile core")
    p_eval.set_defaults(fn=cmd_eval)
    sub.add_parser("backup", help="Sofort-Backup").set_defaults(fn=cmd_backup)
    sub.add_parser("briefing", help="Morgenbriefing jetzt senden").set_defaults(fn=cmd_briefing)
    sub.add_parser("retro", help="Wochen-Retro jetzt ausführen").set_defaults(fn=cmd_retro)
    sub.add_parser("budget", help="Tool-Kontextbudget messen").set_defaults(fn=cmd_budget)
    sub.add_parser("logs", help="wichtigste Logs anzeigen").set_defaults(fn=cmd_logs)

    ns = ap.parse_args()
    sys.exit(ns.fn(ns))


if __name__ == "__main__":
    main()
