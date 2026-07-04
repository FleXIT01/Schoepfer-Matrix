"""eval/runner.py — Eval-Suite für die Schöpfer-Matrix (V10).

Führt die Tests aus eval/tests.yaml durch, indem es jeden Prompt als
lokalen Agent-Turn über matrix.cmd schickt. Prüft die Antwort gegen
die definierten Checks. Sendet am Ende einen Telegram-Bericht.

Nutzung:
  python runner.py                  # alle Tests
  python runner.py t01 t07         # nur diese Tests-IDs
  python runner.py --full-only      # nur Tests die require_full=true brauchen
  python runner.py --no-telegram    # kein Telegram-Bericht
  python runner.py --dry-run        # Prompts ausgeben, nichts ausführen
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ─── Pfade ────────────────────────────────────────────────────────────────────

EVAL_DIR = Path(__file__).parent
ROOT = EVAL_DIR.parent
TESTS_YAML = EVAL_DIR / "tests.yaml"
MATRIX_CMD = ROOT / "matrix.cmd"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Telegram (aus Umgebung oder Fallback)
_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")

# ANSI-Strip-Regex
_ANSI = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


# ─── Telegram-Versand ─────────────────────────────────────────────────────────

def _tg_send(text: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        import urllib.parse
        import urllib.request
        payload = urllib.parse.urlencode({"chat_id": _TG_CHAT, "text": text[:4096]}).encode()
        url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
        req = urllib.request.Request(url, data=payload)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[warn] Telegram-Versand fehlgeschlagen: {e}", file=sys.stderr)


# ─── Matrix-Turn ──────────────────────────────────────────────────────────────

def _run_turn(prompt: str, timeout_sec: int) -> tuple[str, float]:
    """Führt einen Agent-Turn via matrix.cmd aus. Gibt (stdout, elapsed_sec) zurück."""
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            ["cmd", "/c", str(MATRIX_CMD), prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        raw = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT nach {timeout_sec}s]", time.monotonic() - t0
    except Exception as e:
        return f"[FEHLER: {e}]", time.monotonic() - t0
    # ANSI-Codes und Node-Progress-Noise entfernen
    clean = _ANSI.sub("", raw)
    elapsed = time.monotonic() - t0
    return clean, elapsed


# ─── Check-Ausführung ────────────────────────────────────────────────────────

def _run_check(check: dict[str, Any], response: str, test_start: float) -> tuple[bool, str]:
    ctype = check.get("type", "")
    target = check.get("in", "response")
    text = response if target == "response" else response

    if ctype == "regex":
        pattern = check.get("pattern", "")
        match = bool(re.search(pattern, text, re.IGNORECASE | re.MULTILINE))
        return match, f"regex /{pattern}/ {'gefunden' if match else 'NICHT GEFUNDEN'}"

    elif ctype == "not_regex":
        pattern = check.get("pattern", "")
        found = bool(re.search(pattern, text, re.IGNORECASE | re.MULTILINE))
        ok = not found
        return ok, f"not_regex /{pattern}/ {'korrekt nicht gefunden' if ok else 'UNERWARTET GEFUNDEN'}"

    elif ctype == "file_newer":
        dir_path = Path(check.get("dir", "."))
        glob = check.get("pattern", "*.pdf")
        matches = list(dir_path.glob(glob))
        newer = [f for f in matches if f.stat().st_mtime >= test_start - 1]
        ok = len(newer) > 0
        return ok, f"file_newer {dir_path}/{glob}: {'gefunden (' + newer[0].name + ')' if ok else 'keine neue Datei'}"

    elif ctype == "file_exists":
        fpath = Path(check.get("path", ""))
        ok = fpath.exists()
        return ok, f"file_exists {fpath}: {'✅' if ok else '❌ nicht gefunden'}"

    return False, f"Unbekannter Check-Typ: {ctype}"


# ─── Einzel-Test ─────────────────────────────────────────────────────────────

def run_test(test: dict, dry_run: bool = False) -> dict:
    tid = test["id"]
    desc = test["desc"]
    prompt = test["prompt"]
    timeout = int(test.get("timeout_sec", 60))
    checks = test.get("checks", [])

    print(f"\n[{tid}] {desc}")
    print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    if dry_run:
        print("  [dry-run] übersprungen")
        return {"id": tid, "desc": desc, "status": "skipped", "elapsed": 0, "details": []}

    test_start = time.time()
    response, elapsed = _run_turn(prompt, timeout)

    print(f"  Antwort ({elapsed:.1f}s): {response[:120].strip()!r}{'...' if len(response) > 120 else ''}")

    check_results = []
    all_pass = True
    for check in checks:
        ok, detail = _run_check(check, response, test_start)
        check_results.append({"ok": ok, "detail": detail})
        icon = "✅" if ok else "❌"
        print(f"  {icon} {detail}")
        if not ok:
            all_pass = False

    status = "pass" if all_pass else "fail"
    return {
        "id": tid,
        "desc": desc,
        "status": status,
        "elapsed": elapsed,
        "response_snippet": response[:300],
        "checks": check_results,
    }


# ─── Haupt-Runner ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Schöpfer-Matrix Eval-Runner (V10)")
    parser.add_argument("ids", nargs="*", help="Test-IDs filtern (z.B. t01 t07)")
    parser.add_argument("--full-only", action="store_true",
                        help="Nur Tests mit require_full=true")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Kein Telegram-Bericht am Ende")
    parser.add_argument("--dry-run", action="store_true",
                        help="Prompts ausgeben, nichts ausführen")
    args = parser.parse_args()

    # Tests laden
    with open(TESTS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    all_tests: list[dict] = data.get("tests", [])

    # Filter
    tests = all_tests
    if args.ids:
        ids_lower = [i.lower() for i in args.ids]
        tests = [t for t in tests if t["id"].lower() in ids_lower]
    if args.full_only:
        tests = [t for t in tests if t.get("require_full")]

    if not tests:
        print("Keine Tests ausgewählt.")
        sys.exit(0)

    print("=" * 60)
    print(f"  SCHÖPFER-MATRIX EVAL-SUITE  —  {len(tests)} Tests")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    suite_start = time.monotonic()
    for test in tests:
        if not test.get("require_full") or args.full_only or not args.ids:
            r = run_test(test, dry_run=args.dry_run)
            results.append(r)

    suite_elapsed = time.monotonic() - suite_start

    # Zusammenfassung
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    total = len(results)

    print("\n" + "=" * 60)
    print(f"  ERGEBNIS: {passed}/{total} grün  |  {failed} rot  |  {skipped} übersprungen")
    print(f"  Dauer: {suite_elapsed:.1f}s")
    print("=" * 60)

    if failed:
        print("\nFehlgeschlagene Tests:")
        for r in results:
            if r["status"] == "fail":
                print(f"  ❌  [{r['id']}] {r['desc']}")
                for c in r.get("checks", []):
                    if not c.get("ok"):
                        print(f"       → {c['detail']}")

    # Ergebnis-Datei speichern
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    result_file = RESULTS_DIR / f"eval-{ts}.yaml"
    with open(result_file, "w", encoding="utf-8") as f:
        yaml.dump(
            {"ts": ts, "passed": passed, "failed": failed, "total": total,
             "elapsed_sec": round(suite_elapsed, 1), "results": results},
            f, allow_unicode=True, sort_keys=False,
        )
    print(f"\n  Protokoll: {result_file}")

    # Telegram-Bericht
    if not args.no_telegram and not args.dry_run:
        icon = "✅" if failed == 0 else ("⚠️" if failed <= 2 else "❌")
        lines = [
            f"{icon} EVAL-SUITE: {passed}/{total} grün  ({suite_elapsed:.0f}s)",
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ]
        if failed:
            fail_list = [f"  • [{r['id']}] {r['desc']}" for r in results if r["status"] == "fail"]
            lines.append("Fehlgeschlagen:")
            lines.extend(fail_list[:5])
            if len(fail_list) > 5:
                lines.append(f"  … und {len(fail_list)-5} weitere")
        _tg_send("\n".join(lines))
        print("  Telegram-Bericht gesendet.")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
