"""eval/golden.py — Schnelle Golden-Case-Regressions-Harness (V14).

Prüft per DIREKTEM Ollama-Tool-Calling (umgeht den kaputten `openclaw agent --local`
CLI-Pfad), ob das Modell bei typischen Anfragen das RICHTIGE Tool wählt und korrekt
antwortet. Nutzt die ECHTEN Tool-Schemas (tool_catalog.json) + den echten System-Prompt
(AGENTS.md). Deterministisch (temperature 0), läuft in unter einer Minute.

Damit kann man eine Prompt-/Tool-/AGENTS.md-Änderung in SEKUNDEN gegen den alten Stand
vergleichen (Baseline-Diff) statt manuell durchzuklicken.

Aufruf:
  python golden.py                  # alle Cases, Diff gegen Baseline
  python golden.py g01 g10          # nur diese Cases
  python golden.py --save-baseline  # aktuellen Stand als neue Baseline einfrieren
  python golden.py --json           # Maschinenausgabe

Vorher EINMAL (und nach Tool-Änderungen):  python build_catalog.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
CATALOG = EVAL_DIR / "tool_catalog.json"
CASES_YAML = EVAL_DIR / "golden_cases.yaml"
BASELINE = EVAL_DIR / "golden_baseline.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)
AGENTS_MD = ROOT / "openclaw-workspace" / "agent-workspace" / "AGENTS.md"

OLLAMA = "http://127.0.0.1:11434"
MODEL = "gpt-oss-32k"
NUM_CTX = 32768
SEED = 42  # fester Seed → reproduzierbar; sonst variiert gpt-oss (MoE) trotz temp 0
PER_CASE_TIMEOUT = 90.0


# ─── Laden ──────────────────────────────────────────────────────────────────

def _profile_servers(profile: str | None) -> set[str] | None:
    """Erlaubte Server für ein Tool-Profil (None = alle aktiven)."""
    if not profile:
        return None
    pf = EVAL_DIR / "tool_profiles.yaml"
    profs = yaml.safe_load(pf.read_text(encoding="utf-8")).get("profiles", {})
    if profile not in profs:
        sys.exit(f"[!] Profil '{profile}' unbekannt. Verfügbar: {', '.join(profs)}")
    return set(profs[profile]["servers"])


def _load_tools(profile_servers: set[str] | None = None) -> list[dict]:
    if not CATALOG.exists():
        sys.exit(f"[!] {CATALOG.name} fehlt — zuerst `python build_catalog.py` ausführen.")
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    tools = []
    for t in cat["tools"]:
        if t.get("denied"):
            continue
        if profile_servers is not None and t.get("server") not in profile_servers:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": (t.get("description") or "")[:1024],
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return tools


def _system_prompt() -> str:
    if AGENTS_MD.exists():
        return AGENTS_MD.read_text(encoding="utf-8")
    return ("Du bist die Schöpfer-Matrix, ein lokaler Assistent. Antworte auf Deutsch. "
            "Nutze für jede Aufgabe das passende Tool; triviale Fragen direkt beantworten.")


# ─── Ollama-Call ──────────────────────────────────────────────────────────────

def _chat(system: str, user: str, tools: list[dict]) -> tuple[list[str], str, str, float, str]:
    """Ein Tool-Calling-Turn. Gibt (tool_names, args_json, content, elapsed, error)."""
    payload = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "seed": SEED},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": tools,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=PER_CASE_TIMEOUT) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return [], "", "", time.monotonic() - t0, f"{type(e).__name__}: {str(e)[:120]}"
    elapsed = time.monotonic() - t0
    msg = resp.get("message", {}) or {}
    calls = msg.get("tool_calls") or []
    # Separator normalisieren: Modelle emittieren mal 'server.tool', mal 'server__tool'.
    # OpenClaws Tool-Parser gleicht das ab → wir messen Tool-WAHL, nicht Formatierung.
    names = [(c.get("function", {}) or {}).get("name", "").replace(".", "__") for c in calls]
    args = json.dumps([(c.get("function", {}) or {}).get("arguments", {}) for c in calls],
                      ensure_ascii=False)
    content = msg.get("content", "") or ""
    return names, args, content, elapsed, ""


# ─── Checks ───────────────────────────────────────────────────────────────────

def _eval_case(case: dict, names: list[str], args: str, content: str) -> tuple[bool, list[str]]:
    notes: list[str] = []
    checks: list[bool] = []  # Ergebnisse der vorhandenen Checks
    # expect_any=true -> bestehen, wenn IRGENDEIN Check passt (mehrere ok. Verhalten);
    # sonst müssen ALLE passen.
    any_mode = bool(case.get("expect_any"))

    if "expect_tool" in case:
        pat = case["expect_tool"]
        hit = any(re.search(pat, n, re.IGNORECASE) for n in names)
        notes.append(f"tool~/{pat}/ {'✓' if hit else '✗ (gewählt: ' + (', '.join(names) or 'keins') + ')'}")
        checks.append(hit)

    if "expect_arg" in case:
        pat = case["expect_arg"]
        hit = bool(re.search(pat, args, re.IGNORECASE))
        notes.append(f"arg~/{pat}/ {'✓' if hit else '✗'}")
        checks.append(hit)

    if "expect_text" in case:
        pat = case["expect_text"]
        hit = bool(re.search(pat, content, re.IGNORECASE | re.MULTILINE))
        notes.append(f"text~/{pat}/ {'✓' if hit else '✗'}")
        checks.append(hit)

    if case.get("expect_no_cloud"):
        bad = [n for n in names if re.search(r"cloud_", n, re.IGNORECASE)]
        hit = not bad
        notes.append(f"no_cloud {'✓' if hit else '✗ (' + ', '.join(bad) + ')'}")
        checks.append(hit)

    if case.get("expect_direct"):
        hit = len(names) == 0
        notes.append(f"direct {'✓' if hit else '✗ (rief: ' + ', '.join(names) + ')'}")
        checks.append(hit)

    if not checks:
        return False, ["(kein Check definiert)"]
    ok = any(checks) if any_mode else all(checks)
    if any_mode:
        notes.append(f"[expect_any → {'✓' if ok else '✗'}]")
    return ok, notes


# ─── Baseline ───────────────────────────────────────────────────────────────

def _load_baseline() -> dict:
    if BASELINE.exists():
        return json.loads(BASELINE.read_text(encoding="utf-8")).get("cases", {})
    return {}


def _diff(baseline: dict, current: dict) -> tuple[list[str], list[str], list[str]]:
    regressions, fixed, tool_changed = [], [], []
    for cid, cur in current.items():
        base = baseline.get(cid)
        if not base:
            continue
        if base["status"] == "pass" and cur["status"] == "fail":
            regressions.append(cid)
        elif base["status"] == "fail" and cur["status"] == "pass":
            fixed.append(cid)
        elif base.get("tools") != cur.get("tools") and base["status"] == cur["status"]:
            tool_changed.append(cid)
    return regressions, fixed, tool_changed


# ─── Haupt ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Golden-Case-Regressions-Harness (V14)")
    ap.add_argument("ids", nargs="*", help="nur diese Case-IDs (z.B. g01 g10)")
    ap.add_argument("--save-baseline", action="store_true", help="aktuellen Stand als Baseline speichern")
    ap.add_argument("--profile", default=None, help="nur Tools dieses Profils laden (minimal/core/research/full) — testet Routing unter Kontextbudget")
    ap.add_argument("--json", action="store_true", help="Maschinenausgabe (JSON)")
    args = ap.parse_args()

    tools = _load_tools(_profile_servers(args.profile))
    system = _system_prompt()
    cases = yaml.safe_load(CASES_YAML.read_text(encoding="utf-8")).get("cases", [])
    if args.ids:
        want = {i.lower() for i in args.ids}
        cases = [c for c in cases if c["id"].lower() in want or c["id"].split("-")[0].lower() in want]
    if not cases:
        sys.exit("Keine Cases ausgewählt.")

    if not args.json:
        print("=" * 66)
        prof_note = f" | Profil {args.profile}" if args.profile else ""
        print(f"  GOLDEN CASES — {len(cases)} Fälle | {len(tools)} Tools{prof_note} | Modell {MODEL}")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  (temperature 0)")
        print("=" * 66)

    current: dict[str, dict] = {}
    results = []
    suite_t0 = time.monotonic()
    for case in cases:
        cid = case["id"]
        names, argj, content, elapsed, err = _chat(system, case["prompt"], tools)
        if err:
            ok, notes = False, [f"OLLAMA-FEHLER: {err}"]
        else:
            ok, notes = _eval_case(case, names, argj, content)
        status = "pass" if ok else "fail"
        current[cid] = {"status": status, "tools": names}
        results.append({"id": cid, "status": status, "tools": names,
                        "elapsed": round(elapsed, 1), "notes": notes,
                        "content_snippet": content[:160]})
        if not args.json:
            icon = "✅" if ok else "❌"
            print(f"\n{icon} [{cid}] ({elapsed:.1f}s)  tools: {', '.join(names) or '—'}")
            for n in notes:
                print(f"     {n}")

    suite_elapsed = time.monotonic() - suite_t0
    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)

    # Baseline-Diff
    baseline = _load_baseline()
    regressions, fixed, tool_changed = _diff(baseline, current)

    if args.json:
        print(json.dumps({"passed": passed, "total": total,
                          "regressions": regressions, "fixed": fixed,
                          "tool_changed": tool_changed, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print("\n" + "=" * 66)
        print(f"  ERGEBNIS: {passed}/{total} grün  ({suite_elapsed:.0f}s)")
        if baseline:
            print(f"  vs Baseline:  🔴 {len(regressions)} Regression(en)  "
                  f"🟢 {len(fixed)} gefixt  🔀 {len(tool_changed)} Tool-Wahl geändert")
            if regressions:
                print(f"     REGRESSION: {', '.join(regressions)}")
            if fixed:
                print(f"     GEFIXT:     {', '.join(fixed)}")
            if tool_changed:
                print(f"     TOOL-WAHL:  {', '.join(tool_changed)}")
        else:
            print("  (keine Baseline — mit --save-baseline einfrieren)")
        print("=" * 66)

    # Ergebnis speichern
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / f"golden-{ts}.json").write_text(
        json.dumps({"ts": ts, "passed": passed, "total": total, "results": results},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    if args.save_baseline:
        BASELINE.write_text(json.dumps(
            {"saved": ts, "model": MODEL, "cases": current}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        if not args.json:
            print(f"\n  📌 Baseline gespeichert ({passed}/{total}) → {BASELINE.name}")

    # Exit-Code: Regression = harter Fehler (CI/Retro kann darauf reagieren)
    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
