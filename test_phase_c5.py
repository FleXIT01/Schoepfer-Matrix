"""test_phase_c5.py - C5: Erster echter Browser-Workflow (End-to-End).

Beweis der Read-then-act-Disziplin mit echtem TOTP:
  1. httpbin.org/forms/post headless laden
  2. Screenshot + DOM-Tree (beobachten)
  3. browser_type [TOTP-gated] -> Feld ausfuellen
  4. browser_submit [TOTP-gated] -> Formular absenden
  5. Session-Log: 4 Screenshots (vor+nach je Aktion)
  6. Browser schliessen

Ausfuehren: python n:\\allinall\\test_phase_c5.py
"""
import sys
import time
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

# Pfade (portabel: Ordner dieser Datei = Matrix-Root)
ROOT = Path(__file__).resolve().parent
MCP_DIR = ROOT / "mcp-servers"
sys.path.insert(0, str(MCP_DIR))
sys.path.insert(0, str(MCP_DIR / "browser_mcp"))


def _load_totp_secret() -> str:
    """TOTP-Secret aus secrets.env (NIE im Code hartkodieren — GitHub!)."""
    import os
    if os.environ.get("TOTP_SECRET"):
        return os.environ["TOTP_SECRET"]
    env = ROOT / "secrets.env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TOTP_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


_TOTP_SECRET = _load_totp_secret()
_TEST_URL = "https://httpbin.org/forms/post"
_FIELD = "[name='custname']"
_TEXT = "Matrix-Test-2026"

_OK = "OK"
_FAIL = "FAIL"
_WARN = "WARN"
_results: list[tuple[str, str, str]] = []


def _record(name: str, status: str, detail: str = "") -> None:
    mark = "+" if status == _OK else ("?" if status == _WARN else "-")
    _results.append((name, status, detail))
    suffix = f": {detail}" if detail else ""
    print(f"  [{mark}] {name}{suffix}")


def _totp_now() -> str:
    import pyotp
    return pyotp.TOTP(_TOTP_SECRET).now()


def _extract_gate(pending_msg: str) -> str | None:
    """Gate-ID aus PENDING-Nachricht extrahieren."""
    if "PENDING" not in pending_msg:
        return None
    try:
        return pending_msg.split("PENDING")[1].split()[0].strip()
    except IndexError:
        return None


# --- Modul laden -------------------------------------------------------------

print("=" * 62)
print("  C5 - Erster echter Browser-Workflow (End-to-End)")
print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 62)
print()

spec = importlib.util.spec_from_file_location(
    "browser_server",
    MCP_DIR / "browser_mcp" / "server.py",
)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

browser_open = _mod.browser_open
browser_screenshot = _mod.browser_screenshot
browser_dom_tree = _mod.browser_dom_tree
browser_get_text = _mod.browser_get_text
browser_find_element = _mod.browser_find_element
browser_type = _mod.browser_type
browser_submit = _mod.browser_submit
browser_confirm_action = _mod.browser_confirm_action
browser_close = _mod.browser_close
browser_get_url = _mod.browser_get_url
SESSION_LOG = _mod._SESSION_LOG_DIR

shots_start = set(SESSION_LOG.glob("*.png")) if SESSION_LOG.exists() else set()

# --- C5.1 Browser oeffnen ----------------------------------------------------

print("-- C5.1 Browser oeffnen (headless) -------------------------")
r = browser_open(_TEST_URL, headless=True)
if "Browser geöffnet" in r or "httpbin.org" in r.lower():
    _record("C5.1 browser_open httpbin.org/forms/post", _OK, "Browser geladen")
else:
    _record("C5.1 browser_open", _FAIL, r[:120])

# --- C5.2 Screenshot ---------------------------------------------------------

print()
print("-- C5.2 Screenshot -----------------------------------------")
r = browser_screenshot()
if "Screenshot:" in r:
    shot_line = next((l for l in r.splitlines() if l.startswith("Screenshot:")), "")
    p = Path(shot_line.replace("Screenshot:", "").strip())
    if p.exists() and p.stat().st_size > 5_000:
        _record("C5.2 Screenshot", _OK, f"{p.stat().st_size // 1024} KB - {p.name}")
    else:
        _record("C5.2 Screenshot", _FAIL, "Datei fehlt oder < 5 KB")
else:
    _record("C5.2 Screenshot", _FAIL, r[:80])

# --- C5.3 DOM-Tree -----------------------------------------------------------

print()
print("-- C5.3 DOM-Tree -------------------------------------------")
dom = browser_dom_tree()
has_input = any(kw in dom.lower() for kw in ["input", "custname", "textbox", "button", "submit"])
if len(dom) > 100 and has_input:
    _record("C5.3 DOM-Tree (Form-Elemente sichtbar)", _OK, f"{len(dom)} Zeichen")
elif len(dom) > 100:
    _record("C5.3 DOM-Tree", _WARN, f"{len(dom)} Zeichen, Form-Elemente unklar")
else:
    _record("C5.3 DOM-Tree", _FAIL, dom[:80])

# --- C5.4 Seitentext ---------------------------------------------------------

print()
print("-- C5.4 Seitentext -----------------------------------------")
txt = browser_get_text()
has_form_text = any(kw in txt.lower() for kw in ["customer", "name", "order", "submit", "pizza"])
_record(
    "C5.4 Seitentext",
    _OK if has_form_text else _WARN,
    f"{len(txt)} Zeichen, Formular-Woerter={'ja' if has_form_text else 'unklar'}",
)

# --- C5.5 Element finden -----------------------------------------------------

print()
print("-- C5.5 Element finden -------------------------------------")
found = browser_find_element(_FIELD)
if "Gefunden: 0" in found or "nicht gefunden" in found.lower():
    # Fallback: nach Label suchen
    found2 = browser_find_element("label=Customer name")
    if "Gefunden: 0" in found2 or "nicht gefunden" in found2.lower():
        _record("C5.5 Element finden", _WARN, f"'{_FIELD}' nicht gefunden - weiter mit CSS")
    else:
        _FIELD = "label=Customer name"
        _record("C5.5 Element finden", _OK, f"via label=Customer name")
else:
    _record("C5.5 Element finden", _OK, f"via {_FIELD}")

# --- C5.6 browser_type - Gate anlegen ----------------------------------------

print()
print("-- C5.6 browser_type - Gate anlegen ------------------------")
r = browser_type(_FIELD, _TEXT)
gate_type = _extract_gate(r)
if gate_type and "[SCHARF]" in r:
    _record("C5.6 browser_type Gate (SCHARF)", _OK, f"Gate={gate_type}")
elif gate_type:
    _record("C5.6 browser_type Gate", _WARN, f"Gate={gate_type} (kein SCHARF-Flag - TOTP ggf. nicht eingerichtet)")
else:
    _record("C5.6 browser_type Gate", _FAIL, r[:100])

# --- C5.7 TOTP-Genehmigung type ----------------------------------------------

print()
print("-- C5.7 TOTP-Genehmigung type ------------------------------")
if gate_type:
    code = _totp_now()
    exec_r = browser_confirm_action(gate_type, code)
    if "AUSGEFÜHRT" in exec_r:
        _record("C5.7 TOTP-Approve type", _OK, f"Code={code} -> Eingetippt")
    elif "TOTP-Code falsch" in exec_r:
        _record("C5.7 TOTP-Approve type", _FAIL, f"TOTP falsch: Code={code}")
    elif "TOTP erforderlich" in exec_r:
        _record("C5.7 TOTP-Approve type", _FAIL, "TOTP-Code fehlt (Gate erwartet Code)")
    else:
        _record("C5.7 TOTP-Approve type", _FAIL, exec_r[:100])
else:
    _record("C5.7 TOTP-Approve type", _FAIL, "Kein Gate (C5.6 fehlgeschlagen)")

time.sleep(0.3)  # Screenshots landen auf Disk

# --- C5.8+9 Session-Log Vorher+Nachher Screenshot type -----------------------

print()
print("-- C5.8+9 Session-Log Screenshots (pre+post type) ----------")
shots_now = set(SESSION_LOG.glob("*.png")) if SESSION_LOG.exists() else set()
new_shots = shots_now - shots_start
pre_type = [s for s in new_shots if "pre_type" in s.name]
post_type = [s for s in new_shots if "post_type" in s.name]
_record("C5.8 Session-Log pre_type", _OK if pre_type else _FAIL,
        pre_type[0].name if pre_type else "FEHLT")
_record("C5.9 Session-Log post_type", _OK if post_type else _FAIL,
        post_type[0].name if post_type else "FEHLT")

# --- C5.10 browser_submit - Gate anlegen -------------------------------------

print()
print("-- C5.10 browser_submit - Gate anlegen ---------------------")
r = browser_submit("")  # Enter-Taste nach fill() — universell fuer alle Forms
gate_submit = _extract_gate(r)
if gate_submit and "[SCHARF]" in r:
    _record("C5.10 browser_submit Gate (SCHARF)", _OK, f"Gate={gate_submit}")
elif gate_submit:
    _record("C5.10 browser_submit Gate", _WARN, f"Gate={gate_submit}")
else:
    _record("C5.10 browser_submit Gate", _FAIL, r[:100])

# --- C5.11 TOTP-Genehmigung submit -------------------------------------------

print()
print("-- C5.11 TOTP-Genehmigung submit ---------------------------")
if gate_submit:
    code = _totp_now()
    exec_r = browser_confirm_action(gate_submit, code)
    if "AUSGEFÜHRT" in exec_r:
        _record("C5.11 TOTP-Approve submit", _OK, f"Code={code} -> Abgesendet")
    elif "TOTP-Code falsch" in exec_r:
        _record("C5.11 TOTP-Approve submit", _FAIL, f"TOTP falsch: Code={code}")
    else:
        _record("C5.11 TOTP-Approve submit", _FAIL, exec_r[:100])
else:
    _record("C5.11 TOTP-Approve submit", _FAIL, "Kein Gate (C5.10 fehlgeschlagen)")

time.sleep(0.3)

# --- C5.12 URL nach Submit ----------------------------------------------------

print()
print("-- C5.12 URL nach Submit ------------------------------------")
url_r = browser_get_url()
if "httpbin.org/post" in url_r:
    _record("C5.12 URL nach Submit", _OK, url_r.split("\n")[0])
elif "httpbin.org" in url_r:
    _record("C5.12 URL nach Submit", _WARN, url_r.split("\n")[0] + " (nicht /post)")
else:
    _record("C5.12 URL nach Submit", _FAIL, url_r[:80])

# --- C5.13 Final-Screenshot --------------------------------------------------

print()
print("-- C5.13 Final-Screenshot -----------------------------------")
r = browser_screenshot()
if "Screenshot:" in r:
    shot_line = next((l for l in r.splitlines() if l.startswith("Screenshot:")), "")
    p = Path(shot_line.replace("Screenshot:", "").strip())
    _record("C5.13 Final-Screenshot", _OK, f"{p.stat().st_size // 1024} KB - {p.name}")
else:
    _record("C5.13 Final-Screenshot", _FAIL, r[:80])

# --- C5.14 Session-Log Gesamtzahl ---------------------------------------------

print()
print("-- C5.14 Session-Log Gesamtzahl -----------------------------")
time.sleep(0.3)
shots_end = set(SESSION_LOG.glob("*.png")) if SESSION_LOG.exists() else set()
new_total = shots_end - shots_start
n_new = len(new_total)
_record(
    "C5.14 Session-Log >= 4 neue Dateien",
    _OK if n_new >= 4 else (_WARN if n_new >= 2 else _FAIL),
    f"{n_new} neue PNGs in {SESSION_LOG}",
)

# --- C5.15 Browser schliessen -------------------------------------------------

print()
print("-- C5.15 Browser schliessen ---------------------------------")
r = browser_close()
_record("C5.15 browser_close", _OK if "geschlossen" in r.lower() else _FAIL,
        r.split("\n")[0])

# --- Ergebnis -----------------------------------------------------------------

print()
print("=" * 62)
n_ok = sum(1 for _, s, _ in _results if s == _OK)
n_fail = sum(1 for _, s, _ in _results if s == _FAIL)
n_warn = sum(1 for _, s, _ in _results if s == _WARN)
total = len(_results)
print(f"  ERGEBNIS: {n_ok}/{total} OK  |  {n_warn} WARN  |  {n_fail} FAIL")
print()
for name, status, detail in _results:
    mark = "OK  " if status == _OK else ("WARN" if status == _WARN else "FAIL")
    suffix = f" -- {detail}" if detail else ""
    print(f"  [{mark}] {name}{suffix}")
print("=" * 62)
if n_fail == 0:
    grun = "GRUEN" if n_warn == 0 else "GRUEN (mit WARN)"
    print(f"  C5 BESTANDEN ({grun}) -- Phase C vollstaendig bewiesen!")
else:
    print(f"  C5 FEHLGESCHLAGEN -- {n_fail} FAIL(s) behoben notwenig")
print()
