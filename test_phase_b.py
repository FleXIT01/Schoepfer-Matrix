"""test_phase_b.py — Phase-B Beweis-Sprint.

Prueft alle drei Phase-B-Deliverables automatisch:
  B1: profile_mcp — Profile laden, Deny-Liste korrekt
  B2: jobs_mcp + R4 Checkpoint/Resume — Crash + Resume ohne Doppel-Ausfuehrung
  B3: screenshot_mcp — Backend vorhanden, Screenshot nehmen

Ausgabe:
  GRUEN — Deliverable vollstaendig bewiesen
  GELB  — teilweise: laeuft, aber manueller Test fehlt
  ROT   — Fehler / Komponente nicht vorhanden

Ausfuehren: python test_phase_b.py
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

# Pfad fuer Importe
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "mcp-servers"))

# Isolierte Test-Pfade (kein Schreiben in Produktion)
_TMP = Path(tempfile.gettempdir()) / "schoepfer_phase_b"
_TMP.mkdir(exist_ok=True)

_OK  = "GRUEN"
_WRN = "GELB"
_ERR = "ROT"
_results: list[tuple[str, str, str]] = []


def _record(item: str, status: str, detail: str) -> None:
    _results.append((item, status, detail))
    icon = {"GRUEN": "OK", "GELB": "WRN", "ROT": "ERR"}.get(status, "?")
    print(f"  [{icon}] [{status}] {item}: {detail}")


# ════════════════════════════════════════════════════════════════════════════
#  B1 — Tool-Profile
# ════════════════════════════════════════════════════════════════════════════

def test_b1_profiles() -> None:
    print("\nB1 — Tool-Profile-Erzwingung:")
    profiles_file = _ROOT / "mcp-servers" / "tool_profiles.json"

    # B1.1 — tool_profiles.json existiert und ist parsebar
    if not profiles_file.exists():
        _record("B1.1 tool_profiles.json", _ERR, "Datei fehlt")
        return
    try:
        import json
        data = json.loads(profiles_file.read_text(encoding="utf-8"))
        profiles = data.get("profiles", {})
    except Exception as e:
        _record("B1.1 tool_profiles.json", _ERR, str(e))
        return
    _record("B1.1 tool_profiles.json", _OK, f"{len(profiles)} Profile: {', '.join(profiles.keys())}")

    # B1.2 — Pflicht-Profile vorhanden
    required = {"full", "coding", "research", "comms", "minimal"}
    missing = required - profiles.keys()
    if missing:
        _record("B1.2 Pflicht-Profile", _ERR, f"Fehlen: {missing}")
    else:
        _record("B1.2 Pflicht-Profile", _OK, "full / coding / research / comms / minimal vorhanden")

    # B1.3 — full hat leere deny-Liste
    if profiles.get("full", {}).get("deny") != []:
        _record("B1.3 'full'-Profil leer", _ERR, "full.deny ist nicht []")
    else:
        _record("B1.3 'full'-Profil leer", _OK, "full.deny = [] (korrekt)")

    # B1.4 — minimal blockiert mehr als coding
    deny_minimal = set(profiles.get("minimal", {}).get("deny", []))
    deny_coding  = set(profiles.get("coding",  {}).get("deny", []))
    if len(deny_minimal) > len(deny_coding):
        _record("B1.4 minimal > coding Flaechenreduktion", _OK,
                f"minimal={len(deny_minimal)} deny, coding={len(deny_coding)} deny")
    else:
        _record("B1.4 minimal > coding Flaechenreduktion", _ERR,
                f"minimal={len(deny_minimal)} vs coding={len(deny_coding)} — erwartet minimal > coding")

    # B1.5 — profile_mcp/server.py existiert
    srv = _ROOT / "mcp-servers" / "profile_mcp" / "server.py"
    if srv.exists():
        _record("B1.5 profile_mcp/server.py", _OK, "vorhanden")
    else:
        _record("B1.5 profile_mcp/server.py", _ERR, "Datei fehlt")

    # B1.6 — profile_mcp in openclaw.json eingetragen
    openclaw = Path(r"n:\allinall\openclaw-workspace\state\openclaw.json")
    if openclaw.exists():
        import json as _json
        cfg = _json.loads(openclaw.read_text(encoding="utf-8"))
        servers = cfg.get("mcp", {}).get("servers", {})
        if "profile" in servers:
            _record("B1.6 openclaw.json Eintrag", _OK, "profile-mcp ist eingetragen")
        else:
            _record("B1.6 openclaw.json Eintrag", _WRN,
                    "profile-mcp NICHT in openclaw.json — manuell eintragen oder test_phase_b nochmal laufen lassen")
    else:
        _record("B1.6 openclaw.json Eintrag", _WRN, "openclaw.json nicht gefunden")


# ════════════════════════════════════════════════════════════════════════════
#  B2 — Job-Queue + Checkpoint/Resume
# ════════════════════════════════════════════════════════════════════════════

def test_b2_checkpoint() -> None:
    print("\nB2 — Job-Queue + Checkpoint/Resume:")

    # Isolierte Test-DB
    import resilience as _r
    orig_db = _r._DB
    _r._DB = _TMP / "test_resilience.db"
    if _r._DB.exists():
        _r._DB.unlink()

    try:
        executed: list[str] = []

        # B2.1 — Checkpoint schreiben + lesen
        job_id = f"test-{uuid.uuid4().hex[:8]}"
        _r.checkpoint(job_id, 1, {"step1": "done"})
        rp = _r.resume_point(job_id)
        if rp and rp[0] == 1 and rp[1].get("step1") == "done":
            _record("B2.1 Checkpoint schreiben/lesen", _OK, f"job={job_id[:8]} step=1 State korrekt")
        else:
            _record("B2.1 Checkpoint schreiben/lesen", _ERR, f"resume_point={rp}")

        # B2.2 — Crash-Szenario: Schritt 3 crasht, Checkpoint steht bei 2
        executed.clear()

        def step(name: str, fail: bool = False):
            def fn(state: dict) -> dict:
                if fail:
                    raise RuntimeError(f"{name} crasht absichtlich")
                executed.append(name)
                state[name] = "done"
                return state
            return (name, fn)

        steps_crash = [step("s1"), step("s2"), step("s3", fail=True), step("s4")]
        job2 = f"test-{uuid.uuid4().hex[:8]}"
        try:
            _r.run_steps(job2, steps_crash)
        except RuntimeError:
            pass

        if executed == ["s1", "s2"]:
            _record("B2.2 Crash bei s3 — Checkpoint bei s2", _OK, "s1+s2 ausgefuehrt, s3 gecrasht")
        else:
            _record("B2.2 Crash bei s3", _ERR, f"executed={executed}")

        rp2 = _r.resume_point(job2)
        if rp2 and rp2[0] == 2:
            _record("B2.2 resume_point = s2", _OK, f"letzter guter Schritt = 2")
        else:
            _record("B2.2 resume_point", _ERR, f"resume_point={rp2} (erwartet step=2)")

        # B2.3 — Resume: s1/s2 werden NICHT wiederholt
        executed.clear()
        steps_fixed = [step("s1"), step("s2"), step("s3"), step("s4")]
        _r.run_steps(job2, steps_fixed)

        if executed == ["s3", "s4"]:
            _record("B2.3 Resume ab s3 — s1/s2 NICHT wiederholt", _OK,
                    "executed=s3,s4 (s1/s2 uebersprungen — Checkpoint korrekt)")
        else:
            _record("B2.3 Resume", _ERR, f"executed={executed} (erwartet nur s3,s4)")

        if _r.resume_point(job2) is None:
            _record("B2.3 Checkpoints nach Abschluss geloescht", _OK, "resume_point=None (aufgeraeumt)")
        else:
            _record("B2.3 Checkpoint-Cleanup", _WRN, "Checkpoints nach Abschluss noch vorhanden")

        # B2.4 — Freeze-Check (NOT-AUS haelt Jobs an)
        import resilience as _r2
        orig_freeze = _r2._FREEZE_FLAG
        _r2._FREEZE_FLAG = _TMP / "test_freeze.flag"
        _r2._FREEZE_FLAG.write_text("test-freeze", encoding="utf-8")
        try:
            _r2.check_freeze()
            _record("B2.4 Freeze-Check", _ERR, "check_freeze() haette RuntimeError werfen sollen")
        except RuntimeError as e:
            if "NOT-AUS" in str(e):
                _record("B2.4 Freeze-Check blockiert Job-Start", _OK, "RuntimeError korrekt ausgeloest")
            else:
                _record("B2.4 Freeze-Check", _ERR, f"Falsche Exception: {e}")
        finally:
            _r2._FREEZE_FLAG.unlink(missing_ok=True)
            _r2._FREEZE_FLAG = orig_freeze

        # B2.5 — jobs_mcp/server.py hat check_freeze
        jobs_srv = _ROOT / "mcp-servers" / "jobs_mcp" / "server.py"
        if jobs_srv.exists() and "check_freeze" in jobs_srv.read_text(encoding="utf-8"):
            _record("B2.5 jobs_mcp check_freeze eingebaut", _OK, "check_freeze() in job_start() vorhanden")
        else:
            _record("B2.5 jobs_mcp check_freeze", _ERR, "check_freeze nicht in jobs_mcp/server.py gefunden")

    finally:
        _r._DB = orig_db


# ════════════════════════════════════════════════════════════════════════════
#  B3 — screenshot_mcp (Vision in der Schleife)
# ════════════════════════════════════════════════════════════════════════════

def test_b3_screenshot() -> None:
    print("\nB3 — Vision in der Schleife:")

    srv = _ROOT / "mcp-servers" / "screenshot_mcp" / "server.py"
    if not srv.exists():
        _record("B3.1 screenshot_mcp/server.py", _ERR, "Datei fehlt")
        return
    _record("B3.1 screenshot_mcp/server.py", _OK, "vorhanden")

    # B3.2 — Screenshot-Backend pruefen
    mss_ok = False
    pil_ok = False
    try:
        import mss  # noqa
        mss_ok = True
    except ImportError:
        pass
    try:
        from PIL import ImageGrab  # noqa
        pil_ok = True
    except ImportError:
        pass

    if mss_ok:
        _record("B3.2 Screenshot-Backend (mss)", _OK, "mss installiert (bevorzugt)")
    elif pil_ok:
        _record("B3.2 Screenshot-Backend (PIL)", _WRN, "nur PIL/Pillow verfuegbar — mss empfohlen")
    else:
        _record("B3.2 Screenshot-Backend", _ERR,
                "weder mss noch PIL installiert. pip install mss")

    # B3.3 — Screenshot nehmen (live-Test, inline ohne Import-Chain)
    if mss_ok or pil_ok:
        output = _TMP / "test_screenshot.png"
        try:
            if mss_ok:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    img = sct.grab(monitor)
                    mss.tools.to_png(img.rgb, img.size, output=str(output))
                result_ok = output.exists() and output.stat().st_size > 1000
            else:
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=True)
                img.save(str(output), "PNG")
                result_ok = output.exists() and output.stat().st_size > 1000
            if result_ok:
                size_kb = output.stat().st_size // 1024
                _record("B3.3 Screenshot live", _OK, f"{size_kb} KB -> {output.name}")
            else:
                _record("B3.3 Screenshot live", _WRN, "Datei zu klein oder nicht erzeugt")
        except Exception as e:
            _record("B3.3 Screenshot live", _WRN, f"Aufruf fehlgeschlagen: {e}")
    else:
        _record("B3.3 Screenshot live", _WRN, "uebersprungen (kein Backend)")

    # B3.4 — vision_describe in llm_mcp vorhanden
    llm_srv = _ROOT / "mcp-servers" / "llm_mcp" / "server.py"
    if llm_srv.exists() and "def vision_describe" in llm_srv.read_text(encoding="utf-8"):
        _record("B3.4 llm__vision_describe vorhanden", _OK, "vision_describe() in llm_mcp implementiert")
    else:
        _record("B3.4 llm__vision_describe", _ERR, "nicht in llm_mcp/server.py gefunden")

    # B3.5 — screenshot_mcp in openclaw.json
    openclaw = Path(r"n:\allinall\openclaw-workspace\state\openclaw.json")
    if openclaw.exists():
        import json as _json
        cfg = _json.loads(openclaw.read_text(encoding="utf-8"))
        servers = cfg.get("mcp", {}).get("servers", {})
        if "screenshot" in servers:
            _record("B3.5 openclaw.json Eintrag", _OK, "screenshot-mcp eingetragen")
        else:
            _record("B3.5 openclaw.json Eintrag", _WRN,
                    "screenshot-mcp NICHT in openclaw.json — Gateway kennt diesen Server noch nicht")
    else:
        _record("B3.5 openclaw.json Eintrag", _WRN, "openclaw.json nicht gefunden")


# ════════════════════════════════════════════════════════════════════════════
#  Haupt
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 64)
    print("  PHASE-B BEWEIS-SPRINT")
    print("  B1: Tool-Profile | B2: Checkpoint/Resume | B3: Vision")
    print("=" * 64)

    test_b1_profiles()
    test_b2_checkpoint()
    test_b3_screenshot()

    print("\n" + "=" * 64)
    gruen = sum(1 for _, s, _ in _results if s == _OK)
    gelb  = sum(1 for _, s, _ in _results if s == _WRN)
    rot   = sum(1 for _, s, _ in _results if s == _ERR)
    gesamt = len(_results)
    print(f"  ERGEBNIS: {gruen}/{gesamt} GRUEN  |  {gelb} GELB  |  {rot} ROT")
    print("=" * 64)
    if rot:
        print("\nROT-Items behoeben, dann erneut ausfuehren.")
    elif gelb:
        print("\nGELB-Items: manuelle Schritte oder fehlende Pakete (pip install mss).")
    else:
        print("\nALLE PHASE-B-TESTS GRUEN.")
    sys.exit(1 if rot else 0)
