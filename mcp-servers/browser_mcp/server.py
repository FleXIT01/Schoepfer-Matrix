"""browser-mcp — Phase C Computer-Steuerung (kontrollierter, sicherer Browser).

SICHERHEITS-DESIGN:
  - Eigenes Chromium-Profil (NULL Passwörter, NULL Sync, KEIN Haupt-Profil)
  - Domain-Allowlist: Agent darf nur freigegebene Domains öffnen
  - Read-then-act: Navigation/Sehen = ungated; Klick/Tippen/Submit = GO-gated
  - Schärfste Klasse (Submit) = TOTP-gated (zweiter Faktor, Phase A4)
  - Session-Log: Screenshot vor+nach jeder gated Aktion
  - NOT-AUS (check_freeze()) vor JEDER Aktion
  - Injection-Quarantäne: Seiteninhalt = Daten, nie Befehle (V7)
  - Idempotenz: jedes Gate kann nur einmal genehmigt werden (R3)

TOOLS (ungated — nur beobachten):
  browser_open(url, headless)     — Browser öffnen + URL laden (+ Allowlist-Check)
  browser_navigate(url)           — Navigation in bestehendem Tab (+ Allowlist-Check)
  browser_screenshot()            — Screenshot der aktuellen Seite -> PNG-Pfad
  browser_dom_tree()              — Accessibility-Tree (interaktive Elemente)
  browser_get_text()              — Sichtbarer Seitentext
  browser_get_url()               — Aktuelle URL + Titel
  browser_find_element(query)     — Element suchen (ohne zu klicken)
  browser_close()                 — Browser schliessen
  browser_list_pending()          — Offene GO-Gates anzeigen
  browser_cancel_action(gate_id)  — Gate abbrechen
  domain_allowlist_list()         — Freigegebene Domains anzeigen
  domain_allowlist_add(domain)    — Domain freigeben

TOOLS (GO-gated — verändern die Welt):
  browser_click(target)           — Element klicken  [GO]
  browser_type(target, text)      — Text eintippen   [GO + TOTP]
  browser_submit(target)          — Formular absenden [GO + TOTP]
  browser_confirm_action(gate_id, totp_code?)  — Gate genehmigen + Aktion ausführen

ABLAUF (Read-then-act, Phase C Kerndisziplin):
  1. browser_open("https://...")         → Seite laden
  2. browser_screenshot()                → Seite sehen
  3. browser_dom_tree()                  → Elemente identifizieren
  4. browser_click("text=Anmelden")      → PENDING abc123
     User: GO abc123
  5. browser_confirm_action("abc123")    → Klick ausgeführt
  6. browser_screenshot()                → Ergebnis prüfen
"""
from __future__ import annotations

import concurrent.futures
import functools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import check_freeze, audit_log  # noqa: E402  (NOT-AUS + Audit)
from gate_middleware import pending_message, gate_approve, gate_cancel, gate_list  # noqa: E402

mcp = FastMCP("browser-mcp")

# ─── Konfiguration ────────────────────────────────────────────────────────────

_PROFILE_DIR = Path(os.environ.get(
    "BROWSER_PROFILE_DIR",
    r"n:\allinall\openclaw-workspace\browser-profile"
))
_SESSION_LOG_DIR = Path(os.environ.get(
    "BROWSER_SESSION_LOG_DIR",
    r"n:\allinall\openclaw-workspace\output\browser-sessions"
))
_ALLOWLIST_FILE = Path(__file__).parent / "domain_allowlist.json"

_DEFAULT_ALLOWLIST = [
    "localhost",
    "127.0.0.1",
    "example.com",
    "httpbin.org",
    "playwright.dev",
    "testingplayground.com",
    "the-internet.herokuapp.com",
]

# ─── Playwright-Zustand (ein Browser pro MCP-Prozess) ─────────────────────────

_pw = None
_context = None
_page = None

# Pending-Aktionen (in-memory; Gate-ID → Aktions-Dict)
_pending_actions: dict[str, dict] = {}

# ─── Playwright-Worker-Thread (KRITISCH für FastMCP) ──────────────────────────
# FastMCP fuehrt sync-Tools ueber einen asyncio-Threadpool aus. Die Playwright
# Sync-API darf NICHT in einem Thread mit laufender asyncio-Loop benutzt werden
# ("Sync API inside the asyncio loop"), und Playwright-Objekte sind zudem
# thread-gebunden. Loesung: ALLE Playwright-Aufrufe laufen ueber EINEN
# dedizierten Worker-Thread (max_workers=1, keine asyncio-Loop). Das garantiert
# Thread-Affinitaet ueber mehrere Tool-Calls hinweg und vermeidet die Loop-Kollision.
_pw_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="playwright"
)


def _pw_bound(fn):
    """Fuehrt die dekorierte Funktion auf dem dedizierten Playwright-Thread aus."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return _pw_executor.submit(fn, *args, **kwargs).result()
    return wrapper


def _ensure_playwright():
    global _pw
    if _pw is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
    return _pw


def _get_page() -> tuple:
    """(page, None) oder (None, Fehlertext)."""
    if _page is None:
        return None, "[Browser nicht geöffnet — browser_open(url='...') zuerst aufrufen.]"
    return _page, None


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _load_allowlist() -> list[str]:
    if _ALLOWLIST_FILE.exists():
        try:
            return json.loads(_ALLOWLIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return list(_DEFAULT_ALLOWLIST)


def _save_allowlist(domains: list[str]) -> None:
    _ALLOWLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALLOWLIST_FILE.write_text(
        json.dumps(sorted(set(domains)), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _check_domain(url: str) -> str | None:
    """None = erlaubt; str = Fehler-Nachricht (Domain blockiert)."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return f"[Ungültige URL: {url}]"
    if not host:
        return None  # about:blank, data:, etc. — erlaubt
    allowlist = _load_allowlist()
    for allowed in allowlist:
        if host == allowed or host.endswith("." + allowed):
            return None
    return (
        f"[DOMAIN-BLOCKIERT: '{host}' ist nicht in der Browser-Allowlist.\n"
        f"Aktuell erlaubt: {', '.join(sorted(allowlist))}\n"
        f"Freigeben mit: browser__domain_allowlist_add(domain='{host}')]"
    )


def _session_screenshot(label: str) -> str:
    """Screenshot für Session-Log. Gibt Pfad oder '' zurück."""
    page, err = _get_page()
    if err:
        return ""
    try:
        _SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:19]
        p = _SESSION_LOG_DIR / f"{label}_{ts}.png"
        page.screenshot(path=str(p), full_page=False)
        return str(p)
    except Exception:
        return ""


def _resolve_locator(page, target: str):
    """Konvertiert Target-String in Playwright-Locator.

    Konventionen:
      text=Schaltfläche       → get_by_text
      role=button name=OK     → get_by_role(role, name=name)
      label=E-Mail            → get_by_label
      placeholder=Suche       → get_by_placeholder
      #id / .class / tag[…]   → CSS-Selektor (Standard)
    """
    t = target.strip()
    if t.startswith("text="):
        return page.get_by_text(t[5:], exact=False)
    if t.startswith("role="):
        rest = t[5:]
        parts = rest.split(" name=", 1)
        role = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else None
        return page.get_by_role(role, name=name) if name else page.get_by_role(role)
    if t.startswith("label="):
        return page.get_by_label(t[6:])
    if t.startswith("placeholder="):
        return page.get_by_placeholder(t[12:])
    return page.locator(t)


def _store_pending(gate_id: str, action_type: str, params: dict) -> None:
    _pending_actions[gate_id] = {"type": action_type, "params": params}


def _execute_pending(gate_id: str) -> str:
    action = _pending_actions.pop(gate_id, None)
    if not action:
        return (
            f"[Aktions-Daten für Gate {gate_id} nicht mehr im Speicher.\n"
            f"Mögliche Ursache: Server-Neustart zwischen Anfrage und GO.\n"
            f"Lösung: Aktion neu aufrufen (browser_click/browser_type/browser_submit).]"
        )

    page, err = _get_page()
    if err:
        return err

    action_type = action["type"]
    params = action["params"]

    # Session-Log: Vorher-Screenshot
    pre_shot = _session_screenshot(f"pre_{action_type}_{gate_id[:6]}")

    try:
        if action_type == "click":
            target = params["target"]
            loc = _resolve_locator(page, target)
            loc.first.click(timeout=10_000)
            audit_log("browser_click", f"Klick: '{target}' | URL: {page.url}", "APPROVED")
            result_msg = f"Geklickt: '{target}'"

        elif action_type == "type":
            target = params["target"]
            text = params["text"]
            loc = _resolve_locator(page, target)
            loc.first.fill(text, timeout=10_000)
            audit_log("browser_type",
                      f"Eingetippt in: '{target}' | {len(text)} Zeichen | URL: {page.url}",
                      "APPROVED")
            result_msg = f"Eingetippt in '{target}': {len(text)} Zeichen"

        elif action_type == "submit":
            target = params.get("target", "")
            if target:
                loc = _resolve_locator(page, target)
                loc.first.click(timeout=10_000)
            else:
                page.keyboard.press("Enter")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except Exception:
                pass
            audit_log("browser_submit",
                      f"Submit: '{target or 'Enter'}' | Neue URL: {page.url}", "APPROVED")
            result_msg = f"Submit ausgeführt → {page.url} | Titel: {page.title()}"

        else:
            return f"[Unbekannter Aktions-Typ: {action_type}]"

    except Exception as e:
        audit_log(f"browser_{action_type}", f"FEHLER: {e}", "ERROR")
        return f"[Ausführungs-Fehler: {e}]"

    # Session-Log: Nachher-Screenshot
    post_shot = _session_screenshot(f"post_{action_type}_{gate_id[:6]}")

    return (
        f"AUSGEFÜHRT: {result_msg}\n"
        f"Seite: {page.url}\n"
        f"\n"
        f"Session-Log:\n"
        f"  Vorher:  {pre_shot or '(kein Screenshot)'}\n"
        f"  Nachher: {post_shot or '(kein Screenshot)'}\n"
        f"\n"
        f"Nächster Schritt: browser__browser_screenshot() oder browser__browser_dom_tree()"
    )


# ─── Ungated Tools (lesen / beobachten) ──────────────────────────────────────

@mcp.tool()
@_pw_bound
def browser_open(url: str, headless: bool = False) -> str:
    """Browser öffnen und URL laden — UNGATED (nur Beobachtung, keine Aktion).

    Öffnet ein eigenes, sauberes Chromium-Profil (keine gespeicherten Passwörter,
    kein Sync, kein Haupt-Browser). Domain-Allowlist wird geprüft.

    url:      Ziel-URL (muss in Domain-Allowlist sein)
    headless: False = sichtbares Fenster (Standard); True = Hintergrund

    Nach dem Öffnen: browser_screenshot() zum Sehen, browser_dom_tree() zum Lesen."""
    check_freeze()
    block = _check_domain(url)
    if block:
        return block

    global _pw, _context, _page
    try:
        pw = _ensure_playwright()
        if _context is None:
            _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            _context = pw.chromium.launch_persistent_context(
                str(_PROFILE_DIR),
                headless=headless,
                args=[
                    "--no-default-browser-check",
                    "--disable-sync",
                    "--disable-features=ChromeWhatsNew,Translate,PasswordManagerOnboarding",
                    "--no-first-run",
                ],
                no_viewport=False,
                viewport={"width": 1280, "height": 800},
            )

        if len(_context.pages) == 0:
            _page = _context.new_page()
        else:
            _page = _context.pages[-1]

        _page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = _page.title()
        current_url = _page.url

        audit_log("browser_open", f"URL: {url}", "OK")
        return (
            f"Browser geöffnet: {current_url}\n"
            f"Titel: {title}\n"
            f"Profil: {_PROFILE_DIR}\n"
            f"\n"
            f"Nächste Schritte:\n"
            f"  browser__browser_screenshot()        — Seite sehen\n"
            f"  browser__browser_dom_tree()          — Elemente finden\n"
            f"  browser__browser_click('text=...')   — Element klicken (GO-gated)"
        )
    except Exception as e:
        return f"[Browser-Fehler: {e}]"


@mcp.tool()
@_pw_bound
def browser_navigate(url: str) -> str:
    """In bestehendem Tab zu einer URL navigieren — UNGATED.

    Domain-Allowlist wird geprüft. Für Links auf der Seite folgen oder
    direkt zu einer bekannten URL gehen."""
    check_freeze()
    block = _check_domain(url)
    if block:
        return block

    page, err = _get_page()
    if err:
        return err
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        audit_log("browser_navigate", f"URL: {url}", "OK")
        return f"Navigiert zu: {page.url}\nTitel: {page.title()}"
    except Exception as e:
        return f"[Navigation fehlgeschlagen: {e}]"


@mcp.tool()
@_pw_bound
def browser_screenshot() -> str:
    """Screenshot der aktuellen Browser-Seite — UNGATED.

    Gibt den Pfad zur PNG-Datei zurück.
    Weiterverarbeitung: llm__vision_describe(image_path='<pfad>', question='...')"""
    check_freeze()
    page, err = _get_page()
    if err:
        return err
    try:
        _SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        p = _SESSION_LOG_DIR / f"page_{ts}.png"
        page.screenshot(path=str(p), full_page=False)
        size_kb = p.stat().st_size // 1024
        return (
            f"Screenshot: {p}\n"
            f"  Seite: {page.url}\n"
            f"  Grösse: {size_kb} KB\n"
            f"\n"
            f"Analyse: llm__vision_describe(image_path='{p}', question='Was siehst du?')"
        )
    except Exception as e:
        return f"[Screenshot-Fehler: {e}]"


@mcp.tool()
@_pw_bound
def browser_dom_tree() -> str:
    """Accessibility-Tree der aktuellen Seite — UNGATED.

    Zeigt interaktive Elemente strukturiert (Rollen, Namen, Werte).
    Ideal um den richtigen Selektor für browser_click / browser_type zu finden.

    Selektor-Konventionen für Folge-Calls:
      text=Schaltfläche       → nach sichtbarem Text
      role=button name=OK     → nach Rolle + Name
      label=E-Mail            → nach Form-Label
      placeholder=Suche       → nach Placeholder
      #mein-id                → CSS-Selektor"""
    check_freeze()
    page, err = _get_page()
    if err:
        return err
    try:
        # aria_snapshot (Playwright >= 1.49) — liefert ARIA-Text-Baum
        try:
            tree = page.aria_snapshot()
            truncated = len(tree) > 3500
            return (
                f"DOM-Tree: {page.url}\n"
                f"{'─' * 50}\n"
                f"{tree[:3500]}"
                + ("\n[...gekürzt]" if truncated else "")
            )
        except AttributeError:
            pass  # Fallback auf evaluate

        # Fallback: interaktive Elemente via JS
        js = """
        const sels = 'a[href], button, input, select, textarea, [role], h1, h2, h3';
        const els = Array.from(document.querySelectorAll(sels)).slice(0, 80);
        return els.map(el => {
            const role = el.getAttribute('role') || el.tagName.toLowerCase();
            const type = el.getAttribute('type') || '';
            const name = (el.innerText || el.value || el.placeholder ||
                          el.getAttribute('aria-label') || el.title || '').trim().slice(0, 70);
            const id = el.id ? ('#' + el.id) : '';
            return role + (type ? '[' + type + ']' : '') + id + (name ? ' "' + name + '"' : '');
        });
        """
        elements = page.evaluate(js)
        if not elements:
            return "[Keine interaktiven Elemente gefunden]"
        lines = "\n".join(f"  {e}" for e in elements)
        return (
            f"DOM-Tree: {page.url}\n"
            f"{'─' * 50}\n"
            f"{lines}"
            + (f"\n[...{len(elements)} Elemente insgesamt]" if len(elements) >= 80 else "")
        )
    except Exception as e:
        return f"[DOM-Tree-Fehler: {e}]"


@mcp.tool()
@_pw_bound
def browser_get_text() -> str:
    """Sichtbarer Text der aktuellen Seite — UNGATED.

    Für Inhalt-Extraktion ohne Vision-Modell. Max 4000 Zeichen."""
    check_freeze()
    page, err = _get_page()
    if err:
        return err
    try:
        text = (page.inner_text("body") or "").strip()
        truncated = len(text) > 4000
        return (
            f"[{page.url}]\n\n"
            + text[:4000]
            + ("\n\n[...Text gekürzt (> 4000 Zeichen)]" if truncated else "")
        )
    except Exception as e:
        return f"[Text-Fehler: {e}]"


@mcp.tool()
@_pw_bound
def browser_get_url() -> str:
    """Aktuelle URL und Seitentitel — UNGATED."""
    check_freeze()
    page, err = _get_page()
    if err:
        return err
    return f"URL: {page.url}\nTitel: {page.title()}"


@mcp.tool()
@_pw_bound
def browser_find_element(query: str) -> str:
    """Element auf der Seite suchen (ohne zu klicken) — UNGATED.

    query-Format:
      text=Schaltfläche       → nach sichtbarem Text
      role=button name=OK     → nach Rolle + Name
      label=E-Mail            → nach Form-Label
      placeholder=Suche       → nach Placeholder
      #id / .klasse           → CSS-Selektor

    Gibt sichtbare Elemente zurück — für browser_click / browser_type."""
    check_freeze()
    page, err = _get_page()
    if err:
        return err
    try:
        loc = _resolve_locator(page, query)
        count = loc.count()
        if count == 0:
            return f"[Kein Element gefunden für: '{query}']"
        results = []
        for i in range(min(count, 5)):
            el = loc.nth(i)
            try:
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                text = (el.inner_text() or "").strip()[:80]
                visible = el.is_visible()
                results.append(f"  [{i}] <{tag}> visible={visible} text='{text}'")
            except Exception:
                results.append(f"  [{i}] (nicht lesbar)")
        suffix = f"\n  ... und {count - 5} weitere" if count > 5 else ""
        return (
            f"Gefunden: {count} Element(e) für '{query}'\n"
            + "\n".join(results)
            + suffix
        )
    except Exception as e:
        return f"[Suche fehlgeschlagen: {e}]"


@mcp.tool()
@_pw_bound
def browser_close() -> str:
    """Browser schliessen und Ressourcen freigeben — UNGATED."""
    check_freeze()
    global _pw, _context, _page
    try:
        if _context:
            _context.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    finally:
        _context = None
        _page = None
        _pw = None
    audit_log("browser_close", "Browser geschlossen", "OK")
    return f"Browser geschlossen.\nSession-Log: {_SESSION_LOG_DIR}"


@mcp.tool()
def browser_list_pending() -> str:
    """Offene Browser-GO-Gates anzeigen — UNGATED."""
    items = [g for g in gate_list() if "browser" in g["tool"]]
    if not items:
        return "Keine offenen Browser-Gates."
    lines = []
    for g in items:
        sharp = " [SCHARF/TOTP]" if g["sharp"] else ""
        lines.append(f"  {g['id']}{sharp} — {g['tool']}: {g['preview'][:80]}")
    return "Offene Browser-Gates:\n" + "\n".join(lines)


@mcp.tool()
def browser_cancel_action(gate_id: str) -> str:
    """Browser-Gate abbrechen — UNGATED."""
    _pending_actions.pop(gate_id, None)
    ok = gate_cancel(gate_id)
    return (
        f"Gate {gate_id} abgebrochen."
        if ok else
        f"[Gate {gate_id} nicht gefunden oder bereits erledigt.]"
    )


@mcp.tool()
def domain_allowlist_list() -> str:
    """Aktuell freigegebene Browser-Domains anzeigen — UNGATED."""
    domains = _load_allowlist()
    return "Freigegebene Domains:\n" + "\n".join(f"  - {d}" for d in sorted(domains))


@mcp.tool()
def domain_allowlist_add(domain: str) -> str:
    """Domain zur Browser-Allowlist hinzufügen — UNGATED (Konfiguration).

    domain: z.B. 'example.com' (Subdomains werden automatisch miterfasst)"""
    check_freeze()
    # Bereinigen: Schema und Pfad entfernen
    d = domain.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/")[0].split("?")[0]
    if not d or "." not in d:
        return f"[Ungültige Domain: '{domain}' — erwartet z.B. 'example.com']"
    domains = _load_allowlist()
    if d in domains:
        return f"'{d}' ist bereits in der Allowlist."
    domains.append(d)
    _save_allowlist(domains)
    audit_log("domain_allowlist_add", f"Domain hinzugefügt: {d}", "OK")
    return f"'{d}' zur Allowlist hinzugefügt.\nAktuell: {', '.join(sorted(domains))}"


# ─── GO-Gated Tools (verändern die Welt) ─────────────────────────────────────

@mcp.tool()
@_pw_bound
def browser_click(target: str) -> str:
    """Element klicken — GO-GATE (normale Genehmigung).

    Legt PENDING-Gate an. Erst nach 'GO <gate_id>' wird geklickt.
    Kein TOTP erforderlich (normales Gate).

    target: CSS-Selektor oder text=.../role=.../label=.../placeholder=...

    Workflow:
      1. browser_click("text=Anmelden")  → PENDING abc123
      2. User: GO abc123
      3. browser__browser_confirm_action(gate_id="abc123") → Klick ausgeführt"""
    check_freeze()
    page, err = _get_page()
    if err:
        return err

    # Vorab prüfen ob Element existiert
    try:
        loc = _resolve_locator(page, target)
        count = loc.count()
        visible = loc.first.is_visible() if count > 0 else False
    except Exception as e:
        return f"[Element-Prüfung fehlgeschlagen: {e}]"

    if count == 0:
        return (
            f"[Element nicht gefunden: '{target}']\n"
            f"Tipp: browser_find_element('...') zum Suchen nach Alternativen."
        )

    preview = (
        f"Klick auf: '{target}'\n"
        f"Seite: {page.url}\n"
        f"Gefunden: {count} Element(e), sichtbar={visible}"
    )
    gid, msg = pending_message("browser_click", preview, sharp=False)
    _store_pending(gid, "click", {"target": target})
    return msg


@mcp.tool()
def browser_type(target: str, text: str) -> str:
    """Text in Eingabefeld eintippen — SCHARF (GO + TOTP).

    Legt PENDING-Gate mit TOTP-Pflicht an.
    ACHTUNG: Passwörter NIE über den Agenten eintippen lassen.

    target: Selektor (label=..., placeholder=..., #id, ...)
    text:   Einzugebender Text

    Workflow:
      1. browser_type(target="label=E-Mail", text="user@example.com") → PENDING abc123 [SCHARF]
      2. User: GO abc123 123456
      3. browser__browser_confirm_action(gate_id="abc123", totp_code="123456")"""
    check_freeze()
    page, err = _get_page()
    if err:
        return err

    preview = (
        f"Eintippen in: '{target}'\n"
        f"Text: '{text[:50]}{'...' if len(text) > 50 else ''}'\n"
        f"Seite: {page.url}"
    )
    gid, msg = pending_message("browser_type", preview, sharp=True)
    _store_pending(gid, "type", {"target": target, "text": text})
    return msg


@mcp.tool()
def browser_submit(target: str = "") -> str:
    """Formular/Schaltfläche absenden — SCHÄRFSTES Gate (GO + TOTP).

    Jede Submit-Aktion kann externen Zustand ändern (Datenbankeinträge,
    E-Mails, Bestellungen). Daher schärfste Gate-Klasse.

    target: Submit-Button-Selektor (leer = Enter auf aktiver Eingabe)

    Workflow:
      1. browser_submit(target="role=button name=Absenden") → PENDING abc123 [SCHARF]
      2. User: GO abc123 123456
      3. browser__browser_confirm_action(gate_id="abc123", totp_code="123456")"""
    check_freeze()
    page, err = _get_page()
    if err:
        return err

    preview = (
        f"FORMULAR-SUBMIT: '{target or 'Enter auf aktiver Eingabe'}'\n"
        f"Seite: {page.url}\n"
        f"WARNUNG: Diese Aktion sendet/speichert Daten extern."
    )
    gid, msg = pending_message("browser_submit", preview, sharp=True)
    _store_pending(gid, "submit", {"target": target})
    return msg


@mcp.tool()
@_pw_bound
def browser_confirm_action(gate_id: str, totp_code: str = "") -> str:
    """Genehmigt ein Browser-Gate und führt die Aktion aus.

    Normale Gates:  browser_confirm_action(gate_id="abc123")
    TOTP-Gates:     browser_confirm_action(gate_id="abc123", totp_code="123456")

    TOTP-Code aus der Authenticator-App (Secret: YUFQ6UNCAXTI4XQSGTSVXCHFIEBRXDR2)."""
    check_freeze()

    result = gate_approve(gate_id, totp_code or None)
    if result is True:
        return _execute_pending(gate_id)
    if result is False:
        return f"[Gate '{gate_id}' nicht gefunden, abgelaufen oder bereits ausgeführt.]"
    return str(result)  # TOTP-Fehlermeldung


# ─── Einstiegspunkt ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("browser-mcp Selbsttest")
    print(f"  Profil-Verzeichnis: {_PROFILE_DIR}")
    print(f"  Session-Log:        {_SESSION_LOG_DIR}")
    print(f"  Allowlist:          {_load_allowlist()}")
    try:
        import importlib.metadata
        pw_ver = importlib.metadata.version("playwright")
        print(f"  Playwright:         v{pw_ver}")
    except ImportError:
        print("  Playwright:         FEHLT — pip install playwright && playwright install chromium")
    mcp.run(transport="stdio")
