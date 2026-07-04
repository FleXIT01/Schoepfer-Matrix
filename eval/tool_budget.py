"""eval/tool_budget.py — Was kosten die Tool-Schemas WIRKLICH an Kontext? (V14)

Beantwortet Ziel #2 (Kontextbudget) mit echten Zahlen statt Bauchgefühl:
  • misst die TATSÄCHLICHEN Prompt-Tokens der aktiven Tool-Schemas über Ollamas
    prompt_eval_count (mit/ohne tools), nicht per Schätzung,
  • bricht die Kosten je MCP-Server herunter (welcher frisst am meisten Kontext?),
  • entlarvt Server, die GESTARTET werden, aber 0 aktive Tools liefern (reiner Overhead).

Jedes Tool-Schema wird JEDEN Turn mitgeschickt → die Kosten multiplizieren sich über
tausende Iterationen. Weniger Tools = schnellere, billigere Turns + mehr Platz für Inhalt.

Aufruf:  python tool_budget.py
Vorher:  python build_catalog.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
CATALOG = EVAL_DIR / "tool_catalog.json"
CONFIG = ROOT / "openclaw-workspace" / "state" / "openclaw.json"
OLLAMA = "http://127.0.0.1:11434"
MODEL = "gpt-oss-32k"
NUM_CTX = 32768


def _tools_array(active_only: bool = True) -> list[dict]:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    out = []
    for t in cat["tools"]:
        if active_only and t.get("denied"):
            continue
        out.append({"type": "function", "function": {
            "name": t["name"], "description": (t.get("description") or "")[:1024],
            "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}})
    return out


def _prompt_tokens(tools: list[dict]) -> int | None:
    """Echte Prompt-Tokens via Ollama prompt_eval_count (generiert nur 1 Token)."""
    payload = {"model": MODEL, "stream": False,
               "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": 1},
               "messages": [{"role": "system", "content": "x"}, {"role": "user", "content": "hi"}]}
    if tools:
        payload["tools"] = tools
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/chat",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return int(json.loads(r.read()).get("prompt_eval_count") or 0)
    except Exception as e:  # noqa: BLE001
        print(f"[!] Ollama-Messung fehlgeschlagen: {e}")
        return None


def main() -> None:
    if not CATALOG.exists():
        sys.exit("[!] tool_catalog.json fehlt — zuerst `python build_catalog.py`.")
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    active = [t for t in cat["tools"] if not t.get("denied")]
    tools = _tools_array(active_only=True)

    print("=" * 70)
    print(f"  TOOL-KONTEXTBUDGET — {len(active)} aktive Tools  (Modell {MODEL})")
    print("=" * 70)

    p_base = _prompt_tokens([])
    p_full = _prompt_tokens(tools)
    if p_base is not None and p_full is not None:
        tool_tokens = max(0, p_full - p_base)
        print(f"\n  Prompt-Tokens ohne Tools : {p_base}")
        print(f"  Prompt-Tokens mit Tools  : {p_full}")
        print(f"  → Tool-Schemas kosten     : {tool_tokens} Tokens JEDEN Turn "
              f"({tool_tokens/NUM_CTX*100:.0f}% des {NUM_CTX}-Kontexts)")
    else:
        tool_tokens = 0

    # Per-Server-Aufschlüsselung (Zeichen-basiert, dann auf echte Tokens skaliert)
    chars_by_server: dict[str, int] = defaultdict(int)
    count_by_server: dict[str, int] = defaultdict(int)
    for t in active:
        schema = json.dumps({"name": t["name"], "description": t.get("description", ""),
                             "parameters": t.get("input_schema", {})}, ensure_ascii=False)
        chars_by_server[t["server"]] += len(schema)
        count_by_server[t["server"]] += 1
    total_chars = sum(chars_by_server.values()) or 1
    tok_per_char = (tool_tokens / total_chars) if tool_tokens else (1 / 4)

    print(f"\n  Kosten je Server (≈ Tokens, absteigend):")
    print(f"  {'Server':12} {'Tools':>5} {'≈Tokens':>8} {'%':>5}")
    print("  " + "-" * 36)
    for srv, ch in sorted(chars_by_server.items(), key=lambda kv: -kv[1]):
        toks = int(ch * tok_per_char)
        print(f"  {srv:12} {count_by_server[srv]:>5} {toks:>8} {ch/total_chars*100:>4.0f}%")

    # Verschwendung: Server, die laut Config STARTEN, aber 0 aktive Tools liefern
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    all_servers = set(cfg.get("mcp", {}).get("servers", {}).keys())
    active_servers = set(chars_by_server.keys())
    zero_active = sorted(all_servers - active_servers)
    if zero_active:
        print(f"\n  ⚠️  {len(zero_active)} Server STARTEN, liefern aber 0 aktive Tools "
              f"(reiner Start-/Speicher-Overhead, alle Tools denied):")
        print(f"      {', '.join(zero_active)}")
        print(f"      → Empfehlung: diese Server in openclaw.json/mcp.servers deaktivieren "
              f"(spart Subprozess-Start + RAM).")

    print(f"\n  Hebel: jedes gesparte Tool spart ~{int(tool_tokens/max(1,len(active)))} Tokens/Turn. "
          f"Schlanke Profile via:  python tool_profile.py show")
    print("=" * 70)


if __name__ == "__main__":
    main()
