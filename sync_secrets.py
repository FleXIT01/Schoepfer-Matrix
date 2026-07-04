"""sync_secrets.py — liest secrets.env und patcht openclaw.json.

V8 Secrets Hygiene: secrets.env ist die einzige Quelle der Wahrheit fuer
API-Keys / Tokens. Dieses Skript synchronisiert sie nach openclaw.json.

Aufruf:
  python n:\\allinall\\sync_secrets.py           # patcht openclaw.json
  python n:\\allinall\\sync_secrets.py --check   # prueft nur, zeigt Diff

Wird automatisch von gateway.cmd beim Start aufgerufen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ENV_FILE   = Path(__file__).parent / "secrets.env"
_CFG_FILE   = Path(__file__).parent / "openclaw-workspace" / "state" / "openclaw.json"


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _patch(cfg: dict, secrets: dict[str, str]) -> list[str]:
    """Traegt Secrets in cfg ein, gibt Liste der veraenderten Felder zurueck."""
    changed: list[str] = []

    def _set(obj: dict, path: list[str], val: str) -> None:
        for key in path[:-1]:
            obj = obj.setdefault(key, {})
        old = obj.get(path[-1])
        if old != val:
            changed.append(".".join(path))
            obj[path[-1]] = val

    s = secrets

    if "OPENROUTER_API_KEY" in s:
        _set(cfg, ["models", "providers", "openrouter", "apiKey"], s["OPENROUTER_API_KEY"])
        _set(cfg, ["mcp", "servers", "llm", "env", "OPENROUTER_API_KEY"], s["OPENROUTER_API_KEY"])

    if "TELEGRAM_BOT_TOKEN" in s:
        _set(cfg, ["channels", "telegram", "botToken"], s["TELEGRAM_BOT_TOKEN"])
        _set(cfg, ["mcp", "servers", "mail", "env", "TELEGRAM_BOT_TOKEN"], s["TELEGRAM_BOT_TOKEN"])
        _set(cfg, ["mcp", "servers", "assistant", "env", "TELEGRAM_BOT_TOKEN"], s["TELEGRAM_BOT_TOKEN"])

    if "TELEGRAM_DEFAULT_CHAT_ID" in s:
        _set(cfg, ["mcp", "servers", "mail", "env", "TELEGRAM_DEFAULT_CHAT_ID"], s["TELEGRAM_DEFAULT_CHAT_ID"])
        _set(cfg, ["mcp", "servers", "assistant", "env", "TELEGRAM_DEFAULT_CHAT_ID"], s["TELEGRAM_DEFAULT_CHAT_ID"])

    if "WEKNORA_API_KEY" in s:
        _set(cfg, ["mcp", "servers", "kb", "env", "WEKNORA_API_KEY"], s["WEKNORA_API_KEY"])
    if "WEKNORA_BASE_URL" in s:
        _set(cfg, ["mcp", "servers", "kb", "env", "WEKNORA_BASE_URL"], s["WEKNORA_BASE_URL"])
    if "WEKNORA_KB_ID" in s:
        _set(cfg, ["mcp", "servers", "kb", "env", "WEKNORA_KB_ID"], s["WEKNORA_KB_ID"])

    if "OPENCLAW_GATEWAY_TOKEN" in s:
        _set(cfg, ["gateway", "auth", "token"], s["OPENCLAW_GATEWAY_TOKEN"])

    if s.get("GITHUB_TOKEN"):
        _set(cfg, ["mcp", "servers", "github", "env", "GITHUB_TOKEN"], s["GITHUB_TOKEN"])

    return changed


def main() -> None:
    check_only = "--check" in sys.argv

    if not _ENV_FILE.exists():
        print(f"[secrets] FEHLER: {_ENV_FILE} nicht gefunden — Abbruch.")
        sys.exit(1)
    if not _CFG_FILE.exists():
        print(f"[secrets] FEHLER: {_CFG_FILE} nicht gefunden — Abbruch.")
        sys.exit(1)

    secrets = _load_env(_ENV_FILE)
    cfg = json.loads(_CFG_FILE.read_text(encoding="utf-8"))
    changed = _patch(cfg, secrets)

    if not changed:
        print("[secrets] openclaw.json ist bereits aktuell — kein Update noetig.")
        return

    if check_only:
        print(f"[secrets] {len(changed)} Felder wuerden aktualisiert:")
        for f in changed:
            print(f"  - {f}")
        return

    _CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[secrets] {len(changed)} Felder in openclaw.json aktualisiert:")
    for f in changed:
        print(f"  + {f}")


if __name__ == "__main__":
    main()
