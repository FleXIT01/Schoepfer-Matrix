"""factory-mcp — die Bot-Fabrik aus bot1 als MCP-Server.

Macht bot1s Alleinstellungsmerkmal verfügbar: einen Bot aus einer Spezifikation
generieren UND in einer Sandbox VERIFIZIEREN (Import-/Smoke-/Tool-Gates). Das hat
OpenClaws coding-agent so nicht. OpenClaw ruft diese Tools über MCP.

Start (stdio):  python server.py

Hinweis: build_bot benötigt ein laufendes Ollama (Standardmodell llama3.1:8b,
über Parameter 'model' änderbar). list_capabilities/verify_package brauchen kein LLM.

G2: Verifikation läuft in Docker (python:3.12-slim, --network none) wenn verfügbar.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BOT1 = Path(__file__).resolve().parents[2] / "bot1"
if str(_BOT1) not in sys.path:
    sys.path.insert(0, str(_BOT1))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("factory-mcp")

_OUTPUT_ROOT = _BOT1 / "output"

_DOCKER_IMPORT_SCRIPT = (
    "import sys; sys.path.insert(0, '/workspace');"
    "import bot.runner; print('IMPORT_OK')"
)


def _docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _docker_verify(root: Path, timeout: int = 60) -> tuple[bool, str]:
    """Verifiziert bot.runner-Import in python:3.12-slim ohne Netzwerk."""
    vol = f"{root}:/workspace"
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "-v", vol,
        "python:3.12-slim",
        "python", "-c", _DOCKER_IMPORT_SCRIPT,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"Docker-Verifikation Timeout ({timeout}s)"
    except Exception as exc:
        return False, f"Docker-Fehler: {exc}"

    if "IMPORT_OK" in proc.stdout:
        return True, "Docker-Sandbox: IMPORT_OK (python:3.12-slim, --network none)"
    err = (proc.stderr or proc.stdout).strip().splitlines()
    return False, "Docker-Import FEHLGESCHLAGEN:\n" + "\n".join(err[-8:])


@mcp.tool()
def list_capabilities() -> str:
    """Listet alle geprüften Tool-Capabilities, die ein generierter Bot erhalten kann
    (read_file, write_file, web_fetch, arxiv_search, chembl_search, generate_image, ...).
    Für: vorab sehen, welche Bausteine die Fabrik kennt."""
    from generator.agent.tools import library
    caps = library.available_capabilities()
    catalog = library.capability_catalog()
    return f"{len(caps)} verfügbare Capabilities:\n\n{catalog}"


@mcp.tool()
def build_bot(name: str, description: str, system_prompt: str = "",
              first_message: str = "Hallo!", model: str = "llama3.1:8b",
              docker_sandbox: bool = True) -> str:
    """Generiert UND verifiziert einen vollständigen Bot aus einer Spezifikation.
    Durchläuft Architect -> Coder -> Sandbox-Gates -> Fixer und schreibt ein
    lauffähiges Paket + BUILD_REPORT.md. Benötigt laufendes Ollama.
    docker_sandbox=True (Standard): abschließende Verifikation in python:3.12-slim
    ohne Netzwerk (G2). Falls Docker nicht verfügbar, wird der Schritt übersprungen.
    Für: einen neuen Bot/Agenten bauen lassen (mit echter Verifikation)."""
    from generator.llm import create_llm_adapter
    from generator.models.bot_spec import BotSpec
    from generator.agent.orchestrator import Orchestrator

    try:
        llm = create_llm_adapter("ollama", api_key=None, model=model,
                                 base_url="http://localhost:11434")
    except Exception as exc:  # noqa: BLE001
        return f"[Ollama nicht verfügbar: {exc}]"

    spec = BotSpec(
        name=name,
        description=description,
        system_prompt=system_prompt or f"Du bist {name}, ein hilfreicher Assistent.",
        first_message=first_message,
    )
    out_dir = _OUTPUT_ROOT / name.replace(" ", "_")[:40]
    out_dir.mkdir(parents=True, exist_ok=True)

    orch = Orchestrator(llm)
    progress: list[str] = []
    try:
        result = orch.build(spec, out_dir, progress=lambda m: progress.append(m))
    except Exception as exc:  # noqa: BLE001
        return f"[Build fehlgeschlagen: {exc}]"

    steps_ok = sum(1 for s in result.steps if s.status in ("ok", "fixed", "skipped"))
    lines = [
        f"{'✅' if result.ok else '⚠️'} Bot '{name}' gebaut nach: {out_dir}",
        f"  Dateien: {len(result.files)} | Schritte ok: {steps_ok}/{len(result.steps)}",
        f"  Finaler Lauf: {'OK' if result.final_run_ok else 'siehe Report' }",
        f"  Report: {out_dir / 'BUILD_REPORT.md'}",
    ]
    # Schritt-Status kompakt
    for s in result.steps[:12]:
        lines.append(f"    [{s.status}] {s.name}: {str(s.detail)[:70]}")

    # G2: abschließende Docker-Sandbox-Verifikation
    if docker_sandbox and result.ok:
        if _docker_available():
            ok, msg = _docker_verify(out_dir)
            lines.append(f"  Docker-Sandbox: {'✅' if ok else '❌'} {msg}")
        else:
            lines.append("  Docker-Sandbox: übersprungen (Docker nicht erreichbar)")

    return "\n".join(lines)


@mcp.tool()
def verify_package(path: str) -> str:
    """Verifiziert ein generiertes Bot-Paket: prüft die Struktur und versucht,
    bot.runner zu importieren. Primär in Docker (python:3.12-slim, --network none);
    Fallback auf lokalen Subprozess wenn Docker nicht verfügbar.
    Für: bestätigen, dass ein gebautes Paket wirklich lauffähig ist."""
    root = Path(path)
    if not root.exists():
        return f"❌ Pfad nicht gefunden: {path}"

    runner = root / "bot" / "runner.py"
    if not runner.exists():
        candidates = list(root.rglob("bot/runner.py"))
        if not candidates:
            return f"❌ Kein bot/runner.py unter {path} gefunden (kein gültiges Bot-Paket)."
        root = candidates[0].parents[1]

    files = len(list(root.rglob("*.py")))

    if _docker_available():
        ok, msg = _docker_verify(root)
        tag = "✅" if ok else "❌"
        return f"{tag} {msg}\n  Pfad: {root} | {files} .py-Dateien"

    # Fallback: lokaler Subprozess (kein Docker)
    driver = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "try:\n"
        "    import bot.runner\n"
        "    print('IMPORT_OK')\n"
        "except Exception as e:\n"
        "    import traceback; traceback.print_exc(); print('IMPORT_FAIL')\n"
    ) % str(root)
    try:
        proc = subprocess.run([sys.executable, "-c", driver],
                              capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return f"❌ Verifikation fehlgeschlagen: {exc}"

    if "IMPORT_OK" in proc.stdout:
        return f"✅ Paket OK (lokal, kein Docker): bot.runner importiert sauber ({files} .py-Dateien) unter {root}"
    err = (proc.stderr or proc.stdout).strip().splitlines()
    tail = "\n".join(err[-6:])
    return f"❌ Import-Gate FEHLGESCHLAGEN unter {root}:\n{tail}"


@mcp.tool()
def start_webapp(path: str, port: int = 8765, wait_seconds: int = 8) -> str:
    """I2 Fabrik mit Augen: startet eine gebaute Web-App auf einem lokalen Port.

    Sucht im Bot-Verzeichnis nach app.py / main.py / bot/runner.py und startet
    sie als Hintergrundprozess. Wartet bis der Port antwortet (max. wait_seconds).

    path:         Pfad zum Build-Verzeichnis (aus build_bot)
    port:         Port für die App (Standard 8765; 0 = automatisch frei wählen)
    wait_seconds: Sekunden warten bis die App bereit ist (Standard 8)

    Gibt die URL zurück oder eine Fehlermeldung."""
    import time
    import socket

    root = Path(path)
    if not root.exists():
        return f"❌ Pfad nicht gefunden: {path}"

    # Freien Port finden wenn port=0
    if port == 0:
        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

    # Einstiegspunkt suchen (Priorität: app.py > main.py > bot/runner.py)
    candidates = [
        root / "app.py",
        root / "main.py",
        root / "bot" / "runner.py",
    ]
    entry = next((c for c in candidates if c.exists()), None)
    if not entry:
        return (f"❌ Kein Einstiegspunkt gefunden in {path}.\n"
                "Erwartet: app.py, main.py, oder bot/runner.py")

    env = dict(__import__("os").environ)
    env["PORT"] = str(port)

    try:
        proc = subprocess.Popen(
            [sys.executable, str(entry)],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        return f"❌ Start fehlgeschlagen: {exc}"

    # Auf Port warten
    url = f"http://localhost:{port}"
    for _ in range(wait_seconds * 2):
        time.sleep(0.5)
        try:
            import httpx
            r = httpx.get(url, timeout=1.0)
            if r.status_code < 500:
                return f"✅ App läuft auf {url}  (PID {proc.pid}, Einstieg: {entry.name})"
        except Exception:
            pass
        if proc.poll() is not None:
            return f"❌ App-Prozess unerwartet beendet (Exit {proc.returncode}). Logs prüfen."

    return (f"⚠️ App gestartet aber Port {port} antwortet noch nicht nach {wait_seconds}s.\n"
            f"URL: {url}  PID: {proc.pid}  — kurz warten und screenshot_webapp aufrufen.")


@mcp.tool()
def screenshot_webapp(url: str, output_path: str = "") -> str:
    """I2 Fabrik mit Augen: Screenshot einer laufenden Web-App (headless Chromium).

    Benötigt playwright: `pip install playwright && playwright install chromium`
    Falls playwright fehlt, wird eine klare Installationsanleitung zurückgegeben.

    url:         URL der App (z.B. http://localhost:8765)
    output_path: Pfad für den Screenshot (leer = auto in bot1/output/screenshots/)

    Gibt den Pfad zum gespeicherten PNG zurück oder eine Fehlermeldung."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return (
            "❌ playwright nicht installiert.\n"
            "Installation (einmalig):\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            "Danach screenshot_webapp erneut aufrufen."
        )

    from datetime import datetime as _dt
    if output_path:
        out = Path(output_path)
    else:
        out = (_BOT1 / "output" / "screenshots" /
               f"screenshot_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(url, wait_until="networkidle", timeout=15_000)
            page.screenshot(path=str(out), full_page=False)
            browser.close()
        return f"Screenshot gespeichert: {out}"
    except Exception as exc:  # noqa: BLE001
        return f"❌ Screenshot fehlgeschlagen: {exc}"


if __name__ == "__main__":
    mcp.run()
