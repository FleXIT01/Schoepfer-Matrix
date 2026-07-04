"""eval/shadow.py — F1: Auto-Tuning mit Schatten-Lauf & Rollback (V3 Phase 13).

Schließt die Schleife der Wochen-Retro (N9): ein Änderungs-VORSCHLAG
(Prompt / Skill-Beschreibung / Config) wird erst gegen die Eval-Suite (V10)
bewiesen, bevor er übernommen wird. Jede Übernahme ist versioniert und
jederzeit zurückrollbar.

D17: GO-PFLICHT — `propose` führt nur den Schatten-Lauf durch und speichert
das Ergebnis. Übernommen wird NICHTS ohne explizites `apply <id>`.

Regressionssperre: sinkt auch nur EIN vorher grüner Test auf rot, wird der
Vorschlag als REGRESSION markiert — apply verweigert dann (Override nur mit
--force, bewusst hässlich).

Nutzung:
  python shadow.py propose <ziel-datei> <kandidat-datei> --reason "..."
        [--tests t01 t02]      # Teilmenge statt ganzer Suite (schneller)
  python shadow.py list                       # alle Vorschläge + Status
  python shadow.py apply <id>                 # nach GO: Kandidat übernehmen
  python shadow.py rollback <id>              # Übernahme rückgängig machen
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
SHADOW_DIR = EVAL_DIR / "shadow"
PROPOSALS = SHADOW_DIR / "proposals.json"
VERSIONS_DIR = SHADOW_DIR / "versions"
PYTHON = sys.executable

SHADOW_DIR.mkdir(exist_ok=True)
VERSIONS_DIR.mkdir(exist_ok=True)


# ─── Vorschlags-Store ────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if PROPOSALS.exists():
        return json.loads(PROPOSALS.read_text(encoding="utf-8"))
    return []


def _save(props: list[dict]) -> None:
    PROPOSALS.write_text(json.dumps(props, indent=2, ensure_ascii=False),
                         encoding="utf-8")


def _find(props: list[dict], pid: str) -> dict | None:
    for p in props:
        if p["id"].startswith(pid):
            return p
    return None


# ─── Eval-Lauf ───────────────────────────────────────────────────────────────────

def _run_suite(test_ids: list[str]) -> dict:
    """Fährt die Eval-Suite (oder Teilmenge) und gibt {passed, total, by_test} zurück."""
    cmd = [PYTHON, str(EVAL_DIR / "runner.py"), "--no-telegram"] + test_ids
    print(f"  Eval-Lauf: {' '.join(cmd[1:])}")
    subprocess.run(cmd, cwd=str(EVAL_DIR), timeout=3600)
    # Neuestes Ergebnis-File lesen
    results = sorted(RESULTS_DIR.glob("eval-*.yaml"))
    if not results:
        raise RuntimeError("Kein Eval-Ergebnis gefunden — runner.py fehlgeschlagen?")
    data = yaml.safe_load(results[-1].read_text(encoding="utf-8"))
    by_test = {r["id"]: r["status"] for r in data.get("results", [])}
    return {"passed": data["passed"], "total": data["total"], "by_test": by_test}


# ─── Kommandos ───────────────────────────────────────────────────────────────────

def cmd_propose(target: str, candidate: str, reason: str, tests: list[str]) -> None:
    target_p, cand_p = Path(target), Path(candidate)
    if not target_p.exists():
        sys.exit(f"[!] Ziel-Datei fehlt: {target_p}")
    if not cand_p.exists():
        sys.exit(f"[!] Kandidat-Datei fehlt: {cand_p}")

    original = target_p.read_text(encoding="utf-8")
    cand_text = cand_p.read_text(encoding="utf-8")
    if original == cand_text:
        sys.exit("[!] Kandidat ist identisch mit dem Ziel — nichts zu testen.")

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), cand_text.splitlines(keepends=True),
        fromfile=str(target_p), tofile=f"{cand_p} (Kandidat)"))

    pid = uuid.uuid4().hex[:8]
    backup = VERSIONS_DIR / f"{pid}-original{target_p.suffix}"
    candidate_store = VERSIONS_DIR / f"{pid}-candidate{target_p.suffix}"
    shutil.copy2(target_p, backup)
    shutil.copy2(cand_p, candidate_store)

    print(f"\n[1/3] BASELINE-Lauf (aktuelle Datei) ...")
    baseline = _run_suite(tests)

    print(f"\n[2/3] SCHATTEN-Lauf (Kandidat eingesetzt) ...")
    target_p.write_text(cand_text, encoding="utf-8")
    try:
        shadow = _run_suite(tests)
    finally:
        # Schatten-Lauf ist IMMER nur temporär — Original zurück (D17: GO-Pflicht)
        target_p.write_text(original, encoding="utf-8")
        print(f"\n[3/3] Original wiederhergestellt (Übernahme nur via apply nach GO).")

    # Regressionssperre: jeder Einzeltest, der von grün auf rot kippt
    regressions = [t for t, st in baseline["by_test"].items()
                   if st == "pass" and shadow["by_test"].get(t) == "fail"]

    verdict = ("REGRESSION" if regressions
               else "WIN" if shadow["passed"] > baseline["passed"]
               else "TIE" if shadow["passed"] == baseline["passed"]
               else "LOSS")

    props = _load()
    props.append({
        "id": pid,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target": str(target_p),
        "reason": reason,
        "tests": tests or ["(alle)"],
        "baseline": f"{baseline['passed']}/{baseline['total']}",
        "shadow": f"{shadow['passed']}/{shadow['total']}",
        "regressions": regressions,
        "verdict": verdict,
        "status": "proposed",
        "backup": str(backup),
        "candidate": str(candidate_store),
        "diff": diff[:10000],
    })
    _save(props)

    print(f"\n{'='*60}")
    print(f"  VORSCHLAG {pid}  —  {verdict}")
    print(f"  Baseline: {baseline['passed']}/{baseline['total']}  "
          f"Kandidat: {shadow['passed']}/{shadow['total']}")
    if regressions:
        print(f"  REGRESSION in: {', '.join(regressions)} — apply ist GESPERRT.")
    elif verdict in ("WIN", "TIE"):
        print(f"  Übernahme nach GO:  python shadow.py apply {pid}")
    else:
        print(f"  Kandidat ist SCHLECHTER — Übernahme nicht empfohlen.")
    print(f"{'='*60}")


def cmd_list() -> None:
    props = _load()
    if not props:
        print("Keine Vorschläge.")
        return
    for p in props:
        icon = {"proposed": "📋", "applied": "✅", "rolled_back": "↩️"}.get(p["status"], "?")
        print(f"{icon} [{p['id']}] {p['created']}  {p['verdict']:10}  "
              f"{p['baseline']} -> {p['shadow']}  {Path(p['target']).name}")
        print(f"     Grund: {p['reason']}  |  Status: {p['status']}")
        if p.get("regressions"):
            print(f"     Regressionen: {', '.join(p['regressions'])}")


def cmd_apply(pid: str, force: bool) -> None:
    props = _load()
    p = _find(props, pid)
    if not p:
        sys.exit(f"[!] Vorschlag '{pid}' nicht gefunden.")
    if p["status"] == "applied":
        sys.exit(f"[!] Vorschlag {p['id']} ist bereits übernommen.")
    if p["verdict"] == "REGRESSION" and not force:
        sys.exit(f"[!] GESPERRT: Regression in {', '.join(p['regressions'])}. "
                 f"(Override: --force, nicht empfohlen.)")
    if p["verdict"] == "LOSS" and not force:
        sys.exit(f"[!] Kandidat war SCHLECHTER ({p['shadow']} vs {p['baseline']}). "
                 f"(Override: --force, nicht empfohlen.)")
    target = Path(p["target"])
    shutil.copy2(p["candidate"], target)
    p["status"] = "applied"
    p["applied_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(props)
    print(f"✅ Vorschlag {p['id']} übernommen -> {target}")
    print(f"   Rollback jederzeit: python shadow.py rollback {p['id']}")


def cmd_rollback(pid: str) -> None:
    props = _load()
    p = _find(props, pid)
    if not p:
        sys.exit(f"[!] Vorschlag '{pid}' nicht gefunden.")
    if p["status"] != "applied":
        sys.exit(f"[!] Vorschlag {p['id']} ist nicht 'applied' (Status: {p['status']}).")
    target = Path(p["target"])
    shutil.copy2(p["backup"], target)
    p["status"] = "rolled_back"
    p["rolled_back_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(props)
    print(f"↩️  Rollback fertig: {target} ist wieder auf dem Stand vor {p['id']}.")


# ─── CLI ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="F1 Shadow-Eval (V3)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prop = sub.add_parser("propose", help="Kandidat im Schatten-Lauf bewerten")
    p_prop.add_argument("target", help="Ziel-Datei (z.B. SKILL.md, AGENTS.md)")
    p_prop.add_argument("candidate", help="Kandidat-Datei mit der Änderung")
    p_prop.add_argument("--reason", required=True, help="Begründung der Änderung")
    p_prop.add_argument("--tests", nargs="*", default=[],
                        help="Nur diese Test-IDs fahren (leer = ganze Suite)")

    sub.add_parser("list", help="Vorschläge anzeigen")

    p_apply = sub.add_parser("apply", help="Vorschlag übernehmen (nach GO)")
    p_apply.add_argument("id")
    p_apply.add_argument("--force", action="store_true",
                         help="Regression/LOSS-Sperre überstimmen (nicht empfohlen)")

    p_rb = sub.add_parser("rollback", help="Übernahme rückgängig machen")
    p_rb.add_argument("id")

    args = ap.parse_args()
    if args.cmd == "propose":
        cmd_propose(args.target, args.candidate, args.reason, args.tests)
    elif args.cmd == "list":
        cmd_list()
    elif args.cmd == "apply":
        cmd_apply(args.id, args.force)
    elif args.cmd == "rollback":
        cmd_rollback(args.id)


if __name__ == "__main__":
    main()
