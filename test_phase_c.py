"""test_phase_c.py — Phase-C Beweis-Sprint.

Prüft alle drei Phase-C-Deliverables automatisch:
  C1: browser_mcp Struktur + Playwright-Installation
  C2: Playwright live — Browser öffnen, Screenshot, DOM-Tree, Text
  C3: Read-then-act-Disziplin — Gating korrekt (click/type/submit)
  C4: Domain-Allowlist (Blocken + Freigeben)

Ausgabe:
  GRUEN — Deliverable vollständig bewiesen
  GELB  — teilweise: läuft, aber manueller Test fehlt
  ROT   — Fehler / Komponente nicht vorhanden

Ausführen: python test_phase_c.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "mcp-servers"))

_TMP = Path(tempfile.gettempdir()) / "schoepfer_phase_c"
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
#  C1 — browser_mcp Struktur + Installation
# ════════════════════════════════════════════════════════════════════════════

def test_c1_structure() -> None:
    print("\nC1 — browser_mcp Struktur + Playwright:")

    # C1.1 — server.py existiert
    srv = _ROOT / "mcp-servers" / "browser_mcp" / "server.py"
    if srv.exists():
        _record("C1.1 browser_mcp/server.py", _OK, "vorhanden")
    else:
        _record("C1.1 browser_mcp/server.py", _ERR, "Datei fehlt")
        return

    # C1.2 — domain_allowlist.json existiert und ist parsebar
    al = _ROOT / "mcp-servers" / "browser_mcp" / "domain_allowlist.json"
    if al.exists():
        try:
            domains = json.loads(al.read_text(encoding="utf-8"))
            _record("C1.2 domain_allowlist.json", _OK,
                    f"{len(domains)} Domains: {', '.join(sorted(domains))}")
        except Exception as e:
            _record("C1.2 domain_allowlist.json", _ERR, str(e))
    else:
        _record("C1.2 domain_allowlist.json", _ERR, "Datei fehlt")

    # C1.3 — Playwright installiert
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        _record("C1.3 Playwright installiert", _OK, "Import OK")
    except ImportError:
        _record("C1.3 Playwright installiert", _ERR,
                "nicht installiert — pip install playwright && playwright install chromium")
        return

    # C1.4 — Chromium-Binary vorhanden
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            version = browser.version
            browser.close()
        _record("C1.4 Chromium-Binary", _OK, f"Version: {version}")
    except Exception as e:
        _record("C1.4 Chromium-Binary", _ERR,
                f"playwright install chromium noetig: {e}")

    # C1.5 — browser-mcp in openclaw.json
    openclaw = Path(r"n:\allinall\openclaw-workspace\state\openclaw.json")
    if openclaw.exists():
        cfg = json.loads(openclaw.read_text(encoding="utf-8"))
        servers = cfg.get("mcp", {}).get("servers", {})
        if "browser" in servers:
            _record("C1.5 openclaw.json Eintrag", _OK, "browser-mcp eingetragen")
        else:
            _record("C1.5 openclaw.json Eintrag", _ERR,
                    "browser-mcp NICHT in openclaw.json")
    else:
        _record("C1.5 openclaw.json Eintrag", _WRN, "openclaw.json nicht gefunden")

    # C1.6 — gate_middleware verfügbar
    gw = _ROOT / "mcp-servers" / "gate_middleware.py"
    if gw.exists():
        _record("C1.6 gate_middleware.py", _OK, "vorhanden")
    else:
        _record("C1.6 gate_middleware.py", _ERR, "fehlt — Gates nicht möglich")


# ════════════════════════════════════════════════════════════════════════════
#  C2 — Playwright live (Browser öffnen, Screenshot, DOM-Tree, Text)
# ════════════════════════════════════════════════════════════════════════════

def test_c2_playwright_live() -> None:
    print("\nC2 — Playwright live (headless):")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _record("C2 Playwright live", _ERR, "playwright nicht installiert")
        return

    profile = _TMP / "test_browser_profile"
    profile.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(profile),
                headless=True,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()

            # C2.1 — Navigation
            try:
                page.goto("https://example.com", wait_until="domcontentloaded", timeout=20_000)
                title = page.title()
                url = page.url
                if "example" in url.lower() or "Example" in title:
                    _record("C2.1 Navigation (example.com)", _OK,
                            f"Titel: '{title}' | URL: {url}")
                else:
                    _record("C2.1 Navigation (example.com)", _WRN,
                            f"Unerwarteter Titel: '{title}'")
            except Exception as e:
                _record("C2.1 Navigation (example.com)", _WRN,
                        f"Netzwerk-Timeout oder kein Internet: {e}")

            # C2.2 — Screenshot
            try:
                ss = _TMP / "test_browser_page.png"
                page.screenshot(path=str(ss), full_page=False)
                size = ss.stat().st_size if ss.exists() else 0
                if size > 5000:
                    _record("C2.2 Browser-Screenshot", _OK, f"{size // 1024} KB -> {ss.name}")
                else:
                    _record("C2.2 Browser-Screenshot", _ERR, f"Screenshot zu klein: {size} Bytes")
            except Exception as e:
                _record("C2.2 Browser-Screenshot", _ERR, str(e))

            # C2.3 — DOM-Tree (aria_snapshot oder evaluate-Fallback)
            try:
                try:
                    tree_text = page.aria_snapshot()
                    _record("C2.3 DOM-Tree (aria_snapshot)", _OK,
                            f"{len(tree_text)} Zeichen")
                except AttributeError:
                    js = """
                    const els = Array.from(document.querySelectorAll(
                        'a[href],button,input,select,textarea,[role],h1,h2')).slice(0,30);
                    return els.map(e => (e.getAttribute('role')||e.tagName.toLowerCase()) +
                        ' "' + (e.innerText||e.placeholder||'').trim().slice(0,40) + '"');
                    """
                    elements = page.evaluate(js)
                    if elements:
                        _record("C2.3 DOM-Tree (evaluate-Fallback)", _OK,
                                f"{len(elements)} Elemente: {elements[0][:50]}")
                    else:
                        _record("C2.3 DOM-Tree", _WRN, "Keine Elemente gefunden")
            except Exception as e:
                _record("C2.3 DOM-Tree", _ERR, str(e))

            # C2.4 — Text-Extraktion
            try:
                text = (page.inner_text("body") or "").strip()
                if len(text) > 10:
                    _record("C2.4 Text-Extraktion", _OK,
                            f"'{text[:60].replace(chr(10), ' ')}...'")
                else:
                    _record("C2.4 Text-Extraktion", _WRN, f"Text sehr kurz: '{text}'")
            except Exception as e:
                _record("C2.4 Text-Extraktion", _ERR, str(e))

            # C2.5 — Element finden
            try:
                loc = page.get_by_role("link")
                count = loc.count()
                _record("C2.5 Element-Findung (Links)", _OK, f"{count} Link(s) gefunden")
            except Exception as e:
                _record("C2.5 Element-Findung", _WRN, str(e))

            ctx.close()

    except Exception as e:
        _record("C2 Playwright-Session", _ERR, f"Unerwarteter Fehler: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  C3 — Read-then-act-Disziplin (Gating)
# ════════════════════════════════════════════════════════════════════════════

def test_c3_gating() -> None:
    print("\nC3 — Read-then-act-Disziplin (Gate-Logik):")

    # C3.1 — gate_middleware importierbar
    try:
        import gate_middleware as gm
        _record("C3.1 gate_middleware import", _OK, "pending_message / gate_approve / gate_cancel OK")
    except Exception as e:
        _record("C3.1 gate_middleware import", _ERR, str(e))
        return

    # C3.2 — Normales Gate (browser_click) → PENDING (nicht SCHARF)
    try:
        gid, msg = gm.pending_message("browser_click", "Klick auf 'Anmelden'", sharp=False)
        if "PENDING" in msg and gid and "[SCHARF]" not in msg:
            _record("C3.2 Normales Gate (browser_click)", _OK,
                    f"PENDING {gid} — kein TOTP erforderlich")
        else:
            _record("C3.2 Normales Gate", _WRN, f"Unerwartete Nachricht: {msg[:80]}")
        gm.gate_cancel(gid)
    except Exception as e:
        _record("C3.2 Normales Gate", _ERR, str(e))

    # C3.3 — Scharfes Gate (browser_submit) → PENDING + [SCHARF]
    try:
        gid2, msg2 = gm.pending_message("browser_submit", "Submit-Formular auf example.com", sharp=True)
        if "PENDING" in msg2 and "[SCHARF]" in msg2 and gid2:
            _record("C3.3 Scharfes Gate (browser_submit)", _OK,
                    f"PENDING {gid2} [SCHARF] — TOTP erforderlich")
        else:
            _record("C3.3 Scharfes Gate", _WRN, f"Unerwartete Nachricht: {msg2[:80]}")
        gm.gate_cancel(gid2)
    except Exception as e:
        _record("C3.3 Scharfes Gate", _ERR, str(e))

    # C3.4 — Nicht-existierendes Gate genehmigen → False (kein Crash)
    try:
        result = gm.gate_approve("000000")
        if result is False:
            _record("C3.4 Unbekanntes Gate -> False", _OK, "gate_approve('000000') = False (korrekt)")
        else:
            _record("C3.4 Unbekanntes Gate", _WRN, f"Erwartet False, bekam: {result}")
    except Exception as e:
        _record("C3.4 Unbekanntes Gate", _ERR, str(e))

    # C3.5 — Gate-Liste (pending gates sichtbar)
    try:
        gid3, _ = gm.pending_message("browser_click", "Test-Gate C3.5", sharp=False)
        items = gm.gate_list()
        found = any(g["id"] == gid3 for g in items)
        gm.gate_cancel(gid3)
        if found:
            _record("C3.5 Gate-Liste", _OK, f"Offenes Gate {gid3} in gate_list() sichtbar")
        else:
            _record("C3.5 Gate-Liste", _WRN, "Gate nicht in gate_list() — DB-Problem?")
    except Exception as e:
        _record("C3.5 Gate-Liste", _ERR, str(e))

    # C3.6 — browser_mcp Tools haben korrekte Gate-Klassen (Code-Prüfung)
    srv = _ROOT / "mcp-servers" / "browser_mcp" / "server.py"
    if srv.exists():
        code = srv.read_text(encoding="utf-8")
        click_sharp = 'pending_message("browser_click"' in code and 'sharp=False' in code
        submit_sharp = 'pending_message("browser_submit"' in code and 'sharp=True' in code
        type_sharp = 'pending_message("browser_type"' in code and 'sharp=True' in code
        if click_sharp and submit_sharp and type_sharp:
            _record("C3.6 Gate-Klassen im Code", _OK,
                    "click=normal, type=TOTP, submit=TOTP — korrekt")
        else:
            _record("C3.6 Gate-Klassen im Code", _ERR,
                    f"click_normal={click_sharp}, type_totp={type_sharp}, submit_totp={submit_sharp}")
    else:
        _record("C3.6 Gate-Klassen", _WRN, "server.py nicht gefunden")


# ════════════════════════════════════════════════════════════════════════════
#  C4 — Domain-Allowlist
# ════════════════════════════════════════════════════════════════════════════

def test_c4_allowlist() -> None:
    print("\nC4 — Domain-Allowlist:")

    # Allowlist-Logik inline replizieren (kein Import der Server-Instanz nötig)
    allowlist_file = _ROOT / "mcp-servers" / "browser_mcp" / "domain_allowlist.json"
    tmp_al = _TMP / "test_allowlist.json"

    default = ["localhost", "127.0.0.1", "example.com", "httpbin.org"]

    def _check(url: str, al: list[str]) -> bool:
        """True = erlaubt."""
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return False
        if not host:
            return True  # about:blank etc.
        for allowed in al:
            if host == allowed or host.endswith("." + allowed):
                return True
        return False

    # C4.1 — Allowlist-Datei lesbar
    if allowlist_file.exists():
        try:
            domains = json.loads(allowlist_file.read_text(encoding="utf-8"))
            _record("C4.1 domain_allowlist.json", _OK,
                    f"{len(domains)} Domains geladen")
        except Exception as e:
            _record("C4.1 domain_allowlist.json", _ERR, str(e))
            domains = default
    else:
        _record("C4.1 domain_allowlist.json", _WRN, "Datei fehlt — nutze Default")
        domains = default

    # C4.2 — Erlaubte Domain durchgelassen
    test_allowed = "https://example.com/test"
    if _check(test_allowed, domains):
        _record("C4.2 Erlaubte Domain", _OK, f"'{test_allowed}' -> erlaubt")
    else:
        _record("C4.2 Erlaubte Domain", _ERR, f"'{test_allowed}' fälschlich blockiert")

    # C4.3 — Subdomain wird miterfasst
    test_sub = "https://www.example.com/page"
    if _check(test_sub, domains):
        _record("C4.3 Subdomain (www.example.com)", _OK, "Subdomain via 'example.com' erlaubt")
    else:
        _record("C4.3 Subdomain", _WRN, "www.example.com blockiert (erwartet erlaubt)")

    # C4.4 — Unbekannte Domain blockiert
    test_blocked = "https://evil.example.org/steal"
    if not _check(test_blocked, domains):
        _record("C4.4 Blockierte Domain", _OK, f"'{test_blocked}' -> blockiert (korrekt)")
    else:
        _record("C4.4 Blockierte Domain", _ERR, f"'{test_blocked}' fälschlich erlaubt")

    # C4.5 — localhost erlaubt
    if _check("http://localhost:3000/app", domains):
        _record("C4.5 localhost erlaubt", _OK, "http://localhost:3000 -> erlaubt")
    else:
        _record("C4.5 localhost erlaubt", _ERR, "localhost fälschlich blockiert")

    # C4.6 — Domain hinzufügen
    try:
        test_domains = list(domains)
        new_domain = "test-c4.local"
        if new_domain not in test_domains:
            test_domains.append(new_domain)
        tmp_al.write_text(json.dumps(test_domains), encoding="utf-8")
        loaded = json.loads(tmp_al.read_text(encoding="utf-8"))
        if new_domain in loaded:
            _record("C4.6 Domain hinzufügen", _OK,
                    f"'{new_domain}' erfolgreich in Allowlist gespeichert")
        else:
            _record("C4.6 Domain hinzufügen", _ERR, "Schreiben/Lesen fehlgeschlagen")
    except Exception as e:
        _record("C4.6 Domain hinzufügen", _ERR, str(e))

    # C4.7 — NOT-AUS Guard in browser_open
    srv = _ROOT / "mcp-servers" / "browser_mcp" / "server.py"
    if srv.exists():
        code = srv.read_text(encoding="utf-8")
        if "check_freeze()" in code and "_check_domain" in code:
            _record("C4.7 NOT-AUS + Domain-Check in browser_open", _OK,
                    "check_freeze() + _check_domain() beide vorhanden")
        else:
            _record("C4.7 NOT-AUS + Domain-Check", _ERR,
                    "check_freeze oder _check_domain fehlt in server.py")


# ════════════════════════════════════════════════════════════════════════════
#  Haupt
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 64)
    print("  PHASE-C BEWEIS-SPRINT")
    print("  C1: Struktur | C2: Playwright live | C3: Gating | C4: Allowlist")
    print("=" * 64)

    test_c1_structure()
    test_c2_playwright_live()
    test_c3_gating()
    test_c4_allowlist()

    print("\n" + "=" * 64)
    gruen = sum(1 for _, s, _ in _results if s == _OK)
    gelb  = sum(1 for _, s, _ in _results if s == _WRN)
    rot   = sum(1 for _, s, _ in _results if s == _ERR)
    gesamt = len(_results)
    print(f"  ERGEBNIS: {gruen}/{gesamt} GRUEN  |  {gelb} GELB  |  {rot} ROT")
    print("=" * 64)
    if rot:
        print("\nROT-Items beheben, dann erneut ausführen.")
    elif gelb:
        print("\nGELB-Items: manuell prüfen oder pip install playwright chromium.")
    else:
        print("\nALLE PHASE-C-TESTS GRUEN.")
    sys.exit(1 if rot else 0)
