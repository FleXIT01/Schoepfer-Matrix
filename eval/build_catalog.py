"""eval/build_catalog.py — Extrahiert den ECHTEN Tool-Katalog der Schöpfer-Matrix.

Spricht jeden in openclaw.json/mcp.servers konfigurierten MCP-Server per stdio an
(initialize -> list_tools), wendet die tools.deny-Liste an (damit der Katalog genau
das abbildet, was der Agent wirklich sieht) und schreibt:

  eval/tool_catalog.json  — [{server, name, description, input_schema}, ...]

Dient ZWEI Zielen:
  • Eval-Harness (golden.py) bekommt die echten Tool-Schemas für Ollama-Tool-Calling.
  • Kontextbudget (tool_budget.py) misst die Token-Kosten dieser Schemas.

Aufruf:  python build_catalog.py            (alle Server)
         python build_catalog.py --raw     (auch denied Tools mit aufnehmen, markiert)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
CONFIG = ROOT / "openclaw-workspace" / "state" / "openclaw.json"
OUT = EVAL_DIR / "tool_catalog.json"
PER_SERVER_TIMEOUT = 40.0  # s — manche Server (science/browser) importieren schwer


def _load_config() -> tuple[dict, set[str]]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    servers = cfg.get("mcp", {}).get("servers", {})
    deny = set(cfg.get("tools", {}).get("deny", []))
    return servers, deny


async def _probe_server(name: str, command: str, args: list[str]) -> list[dict]:
    """initialize + list_tools für EINEN Server. Gibt [] bei Fehler/Timeout zurück."""
    params = StdioServerParameters(command=command, args=args, env=dict(os.environ))
    out: list[dict] = []
    try:
        async with asyncio.timeout(PER_SERVER_TIMEOUT):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    for t in tools.tools:
                        out.append({
                            "server": name,
                            "name": f"{name}__{t.name}",
                            "bare_name": t.name,
                            "description": (t.description or "").strip(),
                            "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                        })
    except (TimeoutError, asyncio.TimeoutError):
        print(f"  [skip] {name}: Timeout nach {PER_SERVER_TIMEOUT:.0f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] {name}: {type(exc).__name__}: {str(exc)[:80]}")
    return out


async def _build(include_denied: bool) -> dict:
    servers, deny = _load_config()
    print(f"Probe {len(servers)} MCP-Server  (deny-Liste: {len(deny)} Tools)\n")
    all_tools: list[dict] = []
    denied_count = 0
    ok_servers = 0
    for name, scfg in servers.items():
        if scfg.get("enabled", True) is False:
            print(f"  [off]  {name:12} (enabled:false — übersprungen)")
            continue
        command = scfg.get("command", sys.executable)
        args = scfg.get("args", [])
        tools = await _probe_server(name, command, args)
        if tools:
            ok_servers += 1
        for t in tools:
            is_denied = t["name"] in deny
            if is_denied:
                denied_count += 1
                if not include_denied:
                    continue
                t["denied"] = True
            all_tools.append(t)
        if tools:
            shown = sum(1 for t in tools if include_denied or t["name"] not in deny)
            print(f"  [ok]   {name:12} {len(tools):>2} Tools ({shown} aktiv)")
    print(f"\nServer erreichbar: {ok_servers}/{len(servers)}  |  "
          f"Tools aktiv: {len(all_tools) - (denied_count if include_denied else 0)}  |  "
          f"denied: {denied_count}")
    return {
        "generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "servers_ok": ok_servers,
        "servers_total": len(servers),
        "active_tools": len([t for t in all_tools if not t.get("denied")]),
        "tools": all_tools,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Tool-Katalog der Schöpfer-Matrix extrahieren")
    ap.add_argument("--raw", action="store_true", help="auch denied Tools aufnehmen (markiert)")
    args = ap.parse_args()
    catalog = asyncio.run(_build(include_denied=args.raw))
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nKatalog geschrieben: {OUT}  ({catalog['active_tools']} aktive Tools)")


if __name__ == "__main__":
    main()
