"""Test-Harness: spricht jeden MCP-Server per echtem stdio-Client an.

Beweist MCP-Konformität: initialize -> list_tools -> call_tool.
Aufruf:  python test_mcp.py <server>        (server: science|factory|review|planner|all)
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_HERE = Path(__file__).resolve().parent
_PY = sys.executable

SERVERS = {
    "science": _HERE / "science_mcp" / "server.py",
    "factory": _HERE / "factory_mcp" / "server.py",
    "review": _HERE / "review_mcp" / "server.py",
    "planner": _HERE / "planner_mcp" / "server.py",
    "knowledge": _HERE / "knowledge_mcp" / "server.py",
    "trace": _HERE / "trace_mcp" / "server.py",
}

# Pro Server: (tool_name, args) als konkreter Live-Aufruf zum Testen
PROBES = {
    "science": ("chembl_search", {"query": "aspirin", "max_results": 1}),
    "factory": ("list_capabilities", {}),
    "review": ("review_code", {"code": "def f(x):\n  return x+1\n", "filename": "f.py"}),
    "planner": ("get_resources", {}),
    "knowledge": ("knowledge_stats", {}),
    "trace": ("log_turn", {"channel": "cli", "model": "gpt-oss-32k", "tools": "knowledge_stats",
                           "summary": "MCP-Test: trace_mcp Probe-Aufruf.", "status": "ok"}),
}


async def test_server(name: str, script: Path) -> bool:
    print(f"\n{'='*60}\n  MCP-SERVER: {name}  ({script.name})\n{'='*60}")
    if not script.exists():
        print(f"  ❌ Datei fehlt: {script}")
        return False
    params = StdioServerParameters(command=_PY, args=[str(script)], env=dict(os.environ))
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                print(f"  ✓ initialize OK")
                print(f"  ✓ {len(names)} Tools: {', '.join(names)}")

                probe = PROBES.get(name)
                if probe and probe[0] in names:
                    tool, args = probe
                    print(f"  → Live-Aufruf: {tool}({args})")
                    res = await session.call_tool(tool, args)
                    text = res.content[0].text if res.content else "(leer)"
                    print(f"  ✓ Antwort ({len(text)} Zeichen):")
                    for line in text.splitlines()[:6]:
                        print(f"      {line[:90]}")
                print(f"  ✅ {name}-mcp FUNKTIONIERT")
                return True
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"  ❌ FEHLER: {exc}")
        traceback.print_exc()
        return False


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = list(SERVERS) if which == "all" else [which]
    results = {}
    for name in targets:
        results[name] = await test_server(name, SERVERS[name])
    print(f"\n{'='*60}\n  ERGEBNIS\n{'='*60}")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}-mcp")
    all_ok = all(results.values())
    print(f"\n  {'🎉 ALLE MCP-SERVER OK' if all_ok else '⚠️  Es gibt Fehler'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
