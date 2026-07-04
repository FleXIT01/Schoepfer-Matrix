"""profile-mcp — Tool-Profile-Erzwingung fuer die Schoepfer-Matrix (Phase B, V1).

Verwaltet benannte Tool-Profile (coding / research / comms / vision / minimal / full).
Jedes Profil definiert eine Deny-Liste — welche MCP-Tools NICHT angeboten werden.
profile_set() schreibt diese Liste in openclaw.json (tools.deny) + aktives Profil
in active_profile.json. Effektiv nach Gateway-Neustart.

Tools:
  profile_list()              — alle Profile + Beschreibungen
  profile_get()               — aktives Profil (aus active_profile.json)
  profile_set(name)           — Profil anwenden (schreibt openclaw.json + active_profile.json)
  profile_diff(a, b)          — welche Tools unterscheiden sich zwischen zwei Profilen?

Start (stdio):  python server.py
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("profile-mcp")

_PROFILES_FILE   = Path(__file__).parent.parent / "tool_profiles.json"
_OPENCLAW_JSON   = Path(r"n:\allinall\openclaw-workspace\state\openclaw.json")
_ACTIVE_PROFILE  = Path(r"n:\allinall\openclaw-workspace\state\active_profile.json")


# ─── Intern ──────────────────────────────────────────────────────────────────

def _load_profiles() -> dict:
    if not _PROFILES_FILE.exists():
        return {}
    return json.loads(_PROFILES_FILE.read_text(encoding="utf-8")).get("profiles", {})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _active_name() -> str:
    if _ACTIVE_PROFILE.exists():
        try:
            return json.loads(_ACTIVE_PROFILE.read_text(encoding="utf-8")).get("name", "unbekannt")
        except Exception:
            pass
    return "unbekannt (active_profile.json fehlt)"


# ─── MCP Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def profile_list() -> str:
    """Listet alle verfuegbaren Tool-Profile mit Beschreibungen und Deny-Groesse.

    Profile bestimmen, welche MCP-Tools dem Modell angeboten werden.
    Kleineres Profil = kleinere Angriffsflaeche."""
    profiles = _load_profiles()
    if not profiles:
        return "[Fehler: tool_profiles.json nicht gefunden oder leer.]"

    active = _active_name()
    lines = [f"TOOL-PROFILE  (aktiv: {active})\n"]
    for name, pdata in profiles.items():
        deny_count = len(pdata.get("deny", []))
        marker = " ◀ AKTIV" if name == active else ""
        lines.append(f"  {name:12s}  deny={deny_count:3d}  —  {pdata.get('description','')}{marker}")
    lines.append("\nAnwenden: profile_set('<name>')")
    lines.append("Unterschied: profile_diff('<a>', '<b>')")
    return "\n".join(lines)


@mcp.tool()
def profile_get() -> str:
    """Gibt das aktuell aktive Tool-Profil zurueck (aus active_profile.json).

    Das Profil bestimmt, welche Tools dem Modell sichtbar sind.
    Effektiv wird es erst nach einem Gateway-Neustart erzwungen."""
    if not _ACTIVE_PROFILE.exists():
        return ("Kein aktives Profil gesetzt (active_profile.json fehlt).\n"
                "Standard: openclaw.json tools.deny gilt unveraendert.\n"
                "Profil setzen: profile_set('<name>')")
    try:
        data = json.loads(_ACTIVE_PROFILE.read_text(encoding="utf-8"))
    except Exception as e:
        return f"[Fehler beim Lesen von active_profile.json: {e}]"

    profiles = _load_profiles()
    name = data.get("name", "?")
    pdata = profiles.get(name, {})
    deny_count = len(pdata.get("deny", []))
    lines = [
        f"Aktives Profil:  {name}",
        f"Beschreibung:    {pdata.get('description', '—')}",
        f"Deny-Eintraege:  {deny_count}",
        f"Gesetzt am:      {data.get('set_at', '?')}",
        "",
        "Wichtig: Profil wirkt erst nach Gateway-Neustart vollstaendig.",
    ]
    return "\n".join(lines)


@mcp.tool()
def profile_set(name: str) -> str:
    """Setzt ein Tool-Profil: schreibt tools.deny in openclaw.json + active_profile.json.

    name: eines von full | coding | research | comms | vision | minimal

    ACHTUNG: Die Tool-Einschraenkung wird erst nach einem Gateway-Neustart
    erzwungen (OpenClaw liest config beim Start). Bis dahin ist das Profil
    als 'pending restart' vermerkt."""
    profiles = _load_profiles()
    if not profiles:
        return "[Fehler: tool_profiles.json nicht gefunden.]"
    if name not in profiles:
        available = ", ".join(profiles.keys())
        return (f"[Fehler: Profil '{name}' unbekannt. Verfuegbar: {available}]")

    pdata = profiles[name]
    deny_list: list[str] = pdata.get("deny", [])

    # openclaw.json lesen
    if not _OPENCLAW_JSON.exists():
        return f"[Fehler: openclaw.json nicht gefunden unter {_OPENCLAW_JSON}]"
    try:
        cfg = json.loads(_OPENCLAW_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        return f"[Fehler beim Lesen von openclaw.json: {e}]"

    # Backup anlegen (rollt auf .bak.0, .bak.1, ... — max 3 Generationen)
    try:
        bak = _OPENCLAW_JSON.with_suffix(".json.profile-bak")
        shutil.copy2(_OPENCLAW_JSON, bak)
    except Exception:
        pass  # Backup-Fehler blockiert nicht

    # tools.deny ersetzen
    if "tools" not in cfg:
        cfg["tools"] = {}
    old_deny = cfg["tools"].get("deny", [])
    cfg["tools"]["deny"] = deny_list

    # zurueckschreiben
    try:
        _OPENCLAW_JSON.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        return f"[Fehler beim Schreiben von openclaw.json: {e}]"

    # active_profile.json schreiben
    _ACTIVE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_PROFILE.write_text(
        json.dumps({
            "name": name,
            "set_at": _now(),
            "deny_count": len(deny_list),
            "description": pdata.get("description", ""),
            "status": "pending_restart",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        f"Profil '{name}' angewendet.\n"
        f"  Deny-Liste: {len(deny_list)} Eintraege (vorher: {len(old_deny)})\n"
        f"  Beschreibung: {pdata.get('description','')}\n"
        f"\n"
        f"WICHTIG: Gateway-Neustart noetig damit OpenClaw die neue deny-Liste laedt.\n"
        f"  Restart: gateway.cmd erneut starten (oder Ctrl+C + gateway.cmd)"
    )


@mcp.tool()
def profile_diff(profile_a: str, profile_b: str) -> str:
    """Zeigt, welche Tools sich zwischen zwei Profilen unterscheiden.

    profile_a, profile_b: Profilnamen (z.B. 'coding', 'research')

    Nuetzlich um zu verstehen, was ein Profilwechsel freischaltet/sperrt."""
    profiles = _load_profiles()
    missing = [p for p in (profile_a, profile_b) if p not in profiles]
    if missing:
        return f"[Fehler: Unbekannte Profile: {', '.join(missing)}]"

    deny_a = set(profiles[profile_a].get("deny", []))
    deny_b = set(profiles[profile_b].get("deny", []))

    only_in_a = sorted(deny_a - deny_b)   # in A geblockt, in B frei
    only_in_b = sorted(deny_b - deny_a)   # in B geblockt, in A frei
    both = len(deny_a & deny_b)

    lines = [f"PROFIL-DIFF: {profile_a} vs. {profile_b}\n"]
    if only_in_a:
        lines.append(f"In '{profile_a}' geblockt, in '{profile_b}' FREI ({len(only_in_a)}):")
        for t in only_in_a:
            lines.append(f"  + {t}")
        lines.append("")
    if only_in_b:
        lines.append(f"In '{profile_b}' geblockt, in '{profile_a}' FREI ({len(only_in_b)}):")
        for t in only_in_b:
            lines.append(f"  - {t}")
        lines.append("")
    lines.append(f"Gemeinsam geblockt: {both}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
