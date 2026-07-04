"""eval/tool_profile.py — Tool-Profile umschalten (Kontextbudget, V14).

Schaltet zwischen schlanken Tool-Profilen (tool_profiles.yaml) um, indem es die
tools.deny-Liste in openclaw.json passend neu schreibt. So lädt der Agent pro Turn
nur die wirklich gebrauchten Tool-Schemas → schnellere, billigere Turns.

Aufruf:
  python tool_profile.py show                # Profile + geschätzte Token-Kosten
  python tool_profile.py current             # welche Server sind aktuell aktiv?
  python tool_profile.py apply core          # Profil setzen (Backup wird angelegt)
  python tool_profile.py apply core --dry-run  # nur zeigen, nichts schreiben

Hinweis: Eine Gateway-Neustart ist nötig, damit die neue deny-Liste greift.
Backup: openclaw.json.toolprofile-bak (letzte Version vor dem Umschalten).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
CATALOG = EVAL_DIR / "tool_catalog.json"
PROFILES_YAML = EVAL_DIR / "tool_profiles.yaml"
CONFIG = ROOT / "openclaw-workspace" / "state" / "openclaw.json"
BACKUP = CONFIG.with_suffix(".json.toolprofile-bak")
NUM_CTX = 32768


def _load_catalog() -> list[dict]:
    if not CATALOG.exists():
        sys.exit("[!] tool_catalog.json fehlt — zuerst `python build_catalog.py`.")
    return json.loads(CATALOG.read_text(encoding="utf-8"))["tools"]


def _profiles() -> dict:
    return yaml.safe_load(PROFILES_YAML.read_text(encoding="utf-8"))["profiles"]


def _server_tokens(active: list[dict]) -> tuple[dict, int]:
    """Grobe Token-Schätzung je Server (Zeichen/4) + Gesamt."""
    chars: dict[str, int] = defaultdict(int)
    for t in active:
        schema = json.dumps({"name": t["name"], "description": t.get("description", ""),
                             "parameters": t.get("input_schema", {})}, ensure_ascii=False)
        chars[t["server"]] += len(schema)
    toks = {s: int(c / 4) for s, c in chars.items()}
    return toks, sum(toks.values())


def cmd_show() -> None:
    active = [t for t in _load_catalog() if not t.get("denied")]
    toks, total = _server_tokens(active)
    profs = _profiles()
    print(f"Aktive Tools gesamt: {len(active)}  (~{total} Tokens/Turn, {total/NUM_CTX*100:.0f}% Kontext)\n")
    print(f"{'Profil':10} {'Server':>6} {'Tools':>5} {'~Tokens':>8} {'Ersparnis':>10}  Beschreibung")
    print("-" * 90)
    for name, p in profs.items():
        srv = set(p["servers"])
        sel = [t for t in active if t["server"] in srv]
        sel_tokens = sum(toks.get(s, 0) for s in srv)
        saving = total - sel_tokens
        print(f"{name:10} {len(srv):>6} {len(sel):>5} {sel_tokens:>8} "
              f"{saving:>9}↓  {p['desc'][:42]}")


def cmd_current() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    deny = set(cfg.get("tools", {}).get("deny", []))
    active = [t for t in _load_catalog() if not t.get("denied")]
    by_server: dict[str, int] = defaultdict(int)
    for t in active:
        by_server[t["server"]] += 1
    print(f"Aktuell: {len(active)} aktive Tools über {len(by_server)} Server, "
          f"tools.deny umfasst {len(deny)} Einträge.")
    print("Aktive Server:", ", ".join(sorted(by_server)))


def cmd_apply(name: str, dry_run: bool) -> None:
    profs = _profiles()
    if name not in profs:
        sys.exit(f"[!] Profil '{name}' unbekannt. Verfügbar: {', '.join(profs)}")
    allowed = set(profs[name]["servers"])
    catalog = _load_catalog()
    active = [t for t in catalog if not t.get("denied")]

    # Alle aktiven Tools, deren Server NICHT im Profil ist -> zusätzlich denyen
    new_denies = sorted({t["name"] for t in active if t["server"] not in allowed})

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    existing = cfg.get("tools", {}).get("deny", [])
    final_deny = sorted(set(existing) | set(new_denies))

    toks, total = _server_tokens(active)
    kept_tokens = sum(toks.get(s, 0) for s in allowed)
    print(f"Profil '{name}': erlaubt {len(allowed)} Server, behält "
          f"{len([t for t in active if t['server'] in allowed])} Tools (~{kept_tokens} Tokens/Turn).")
    print(f"tools.deny: {len(existing)} → {len(final_deny)} Einträge "
          f"(+{len(final_deny)-len(existing)}). Ersparnis ~{total-kept_tokens} Tokens/Turn.")

    if dry_run:
        print("\n[dry-run] Nichts geschrieben. Ohne --dry-run wird openclaw.json aktualisiert.")
        return

    shutil.copy2(CONFIG, BACKUP)
    cfg.setdefault("tools", {})["deny"] = final_deny
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Profil '{name}' angewandt. Backup: {BACKUP.name}")
    print("   → Gateway neu starten (gateway.cmd), damit die deny-Liste greift.")
    print(f"   → Revert: copy /Y \"{BACKUP}\" \"{CONFIG}\"")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tool-Profile umschalten (V14)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="Profile + Token-Kosten anzeigen")
    sub.add_parser("current", help="aktuell aktive Server zeigen")
    pa = sub.add_parser("apply", help="Profil setzen")
    pa.add_argument("name")
    pa.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "show":
        cmd_show()
    elif args.cmd == "current":
        cmd_current()
    elif args.cmd == "apply":
        cmd_apply(args.name, args.dry_run)


if __name__ == "__main__":
    main()
