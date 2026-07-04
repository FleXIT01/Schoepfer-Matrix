"""review-mcp — Code-Review als MCP-Server (self-contained Static Analysis).

Ein harter, abhängigkeitsfreier Reviewer auf Basis von Pythons `ast` und
`compile`. Findet Syntaxfehler, Sicherheitsmuster und Code-Smells und gibt
strukturierte Findings mit Schweregrad zurück. Wird als Pflicht-Gate nach
jeder Code-Generierung eingesetzt (Rolle von repo-critic-ai, aber als
verlässlicher Python-Dienst).

Start (stdio):  python server.py
"""
from __future__ import annotations

import ast
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("review-mcp")

_MAX_FUNC_LINES = 80
_MAX_COMPLEXITY = 12  # grobe Verzweigungs-Zahl pro Funktion


class _Reviewer(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.findings: list[tuple[str, int, str]] = []  # (severity, line, msg)

    def add(self, sev: str, line: int, msg: str) -> None:
        self.findings.append((sev, line, msg))

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add("high", node.lineno, "Nacktes 'except:' — fängt auch SystemExit/KeyboardInterrupt. Spezifische Exception fangen.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in ("eval", "exec"):
            self.add("critical", node.lineno, f"Einsatz von {name}() — Sicherheitsrisiko (Code-Injection).")
        if name == "system" or (isinstance(node.func, ast.Attribute) and node.func.attr == "system"):
            self.add("high", node.lineno, "os.system() — bevorzugt subprocess.run mit Argumentliste (Shell-Injection-Risiko).")
        self.generic_visit(node)

    def _check_func(self, node) -> None:
        # Mutable Default-Argumente
        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.add("high", node.lineno, f"Funktion '{node.name}': veränderbares Default-Argument ([]/{{}}). Nutze None + Init im Körper.")
        # Länge
        if node.body:
            last = node.body[-1]
            length = getattr(last, "end_lineno", node.lineno) - node.lineno
            if length > _MAX_FUNC_LINES:
                self.add("medium", node.lineno, f"Funktion '{node.name}' ist {length} Zeilen lang (> {_MAX_FUNC_LINES}). Aufteilen erwägen.")
        # Docstring
        if not ast.get_docstring(node):
            self.add("low", node.lineno, f"Funktion '{node.name}' hat keinen Docstring.")
        # Zyklomatische Komplexität (grob)
        branches = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.And, ast.Or))
                       for n in ast.walk(node))
        if branches > _MAX_COMPLEXITY:
            self.add("medium", node.lineno, f"Funktion '{node.name}': hohe Komplexität (~{branches} Verzweigungen).")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_func(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_func(node)
        self.generic_visit(node)


def _scan_markers(source: str, findings: list) -> None:
    for i, line in enumerate(source.splitlines(), 1):
        up = line.upper()
        if "TODO" in up or "FIXME" in up or "XXX" in up:
            findings.append(("low", i, f"Marker im Code: {line.strip()[:80]}"))


def _review_source(source: str, filename: str) -> dict:
    """Reviewt Quelltext und liefert ein strukturiertes Ergebnis-Dict."""
    findings: list[tuple[str, int, str]] = []

    # 1) Syntax / Kompilierbarkeit
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return {
            "filename": filename,
            "ok": False,
            "syntax_error": f"Zeile {exc.lineno}: {exc.msg}",
            "findings": [("critical", exc.lineno or 0, f"Syntaxfehler: {exc.msg}")],
        }

    reviewer = _Reviewer(source)
    reviewer.visit(tree)
    findings.extend(reviewer.findings)
    _scan_markers(source, findings)

    findings.sort(key=lambda f: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f[0], 4), f[1]))
    return {"filename": filename, "ok": True, "syntax_error": None, "findings": findings}


def _format(result: dict) -> str:
    fn = result["filename"]
    findings = result["findings"]
    if result.get("syntax_error"):
        return f"❌ {fn}: SYNTAXFEHLER — {result['syntax_error']}"
    if not findings:
        return f"✅ {fn}: keine Probleme gefunden."

    counts: dict[str, int] = {}
    for sev, _, _ in findings:
        counts[sev] = counts.get(sev, 0) + 1
    summary = ", ".join(f"{n}× {s}" for s, n in counts.items())
    icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
    lines = [f"Review {fn}: {len(findings)} Finding(s) ({summary})"]
    for sev, line, msg in findings[:40]:
        lines.append(f"  {icon.get(sev, '•')} [{sev}] Z{line}: {msg}")
    return "\n".join(lines)


@mcp.tool()
def review_code(code: str, filename: str = "snippet.py") -> str:
    """Reviewt einen Python-Quelltext (String): Syntax, Sicherheit (eval/exec/os.system),
    veränderbare Defaults, nackte excepts, Komplexität, fehlende Docstrings, TODO-Marker.
    Für: schnelle Qualitätsprüfung von generiertem oder geschriebenem Code."""
    return _format(_review_source(code, filename))


@mcp.tool()
def review_file(path: str) -> str:
    """Reviewt eine Python-Datei auf der Platte (siehe review_code).
    Für: Prüfung einer konkreten Quelldatei."""
    p = Path(path)
    if not p.exists():
        return f"❌ Datei nicht gefunden: {path}"
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"❌ Lesefehler {path}: {exc}"
    return _format(_review_source(source, p.name))


@mcp.tool()
def scan_repo(repo_path: str, max_files: int = 50) -> str:
    """Scannt alle .py-Dateien eines Verzeichnisses und aggregiert die Findings
    (kritische zuerst). Für: Gesamt-Review eines generierten Projekts/Repos."""
    root = Path(repo_path)
    if not root.exists():
        return f"❌ Pfad nicht gefunden: {repo_path}"

    files = [p for p in root.rglob("*.py")
             if "node_modules" not in p.parts and ".git" not in p.parts][:max_files]
    if not files:
        return f"Keine .py-Dateien in {repo_path} gefunden."

    total = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    syntax_errors = 0
    blocks: list[str] = []
    for p in files:
        try:
            res = _review_source(p.read_text(encoding="utf-8", errors="replace"), str(p.relative_to(root)))
        except Exception:  # noqa: BLE001
            continue
        if res.get("syntax_error"):
            syntax_errors += 1
        for sev, _, _ in res["findings"]:
            total[sev] = total.get(sev, 0) + 1
        # Nur Dateien mit kritischen/hohen Findings detailliert zeigen
        if any(s in ("critical", "high") for s, _, _ in res["findings"]) or res.get("syntax_error"):
            blocks.append(_format(res))

    header = (
        f"REPO-SCAN: {repo_path}\n"
        f"  {len(files)} Datei(en) geprüft | Syntaxfehler: {syntax_errors}\n"
        f"  Findings gesamt: 🔴 {total['critical']} kritisch, 🟠 {total['high']} hoch, "
        f"🟡 {total['medium']} mittel, ⚪ {total['low']} niedrig\n"
        f"  Bewertung: {'❌ NICHT BESTANDEN' if (total['critical'] or syntax_errors) else '✅ BESTANDEN (keine kritischen)'}"
    )
    return header + ("\n\n" + "\n\n".join(blocks[:15]) if blocks else "")


@mcp.tool()
def visual_review(screenshot_path: str, spec: str,
                  model: str = "qwen3-vl:32b") -> str:
    """I2 Fabrik mit Augen: prüft einen Screenshot einer Web-App gegen eine Spezifikation.

    Nutzt das multimodale Ollama-Modell (qwen3-vl) um den Screenshot zu analysieren
    und konkrete visuelle Findings (fehlende Elemente, Layout-Brüche, Spec-Verstösse)
    zurückzugeben.

    VRAM-Hinweis: qwen3-vl:32b braucht ~20 GB VRAM. Bei 16 GB VRAM zuerst
    gpt-oss-32k in Ollama entladen (`ollama stop gpt-oss-32k`) oder
    planner.can_load vorab prüfen.

    screenshot_path: absoluter Pfad zu PNG/JPG
    spec:            Spezifikation als Text (was soll sichtbar/korrekt sein?)
    model:           Ollama-Modell (Standard: qwen3-vl:32b)"""
    import base64
    import os as _os
    import httpx

    p = Path(screenshot_path)
    if not p.exists():
        return f"❌ Screenshot nicht gefunden: {screenshot_path}"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception as e:  # noqa: BLE001
        return f"❌ Fehler beim Lesen des Screenshots: {e}"

    ollama_base = _os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    prompt = (
        "Du bist ein QA-Engineer und prüfst eine Web-App visuell gegen eine Spezifikation.\n\n"
        f"SPEZIFIKATION:\n{spec}\n\n"
        "Analysiere den Screenshot sorgfältig. Antworte in drei Abschnitten:\n"
        "1. KORREKT: was ist vorhanden und entspricht der Spec\n"
        "2. FEHLER: was fehlt oder ist falsch — jeden Punkt mit Schwere [kritisch/mittel/klein]\n"
        "3. FAZIT: BESTANDEN oder NICHT BESTANDEN (und kurze Begründung)\n\n"
        "Nur was du im Screenshot siehst zählt — keine Annahmen."
    )
    messages = [{"role": "user", "content": prompt, "images": [b64]}]
    payload = {"model": model, "messages": messages, "stream": False}

    try:
        r = httpx.post(f"{ollama_base}/api/chat", json=payload, timeout=420.0)
    except httpx.ConnectError:
        return f"❌ Ollama nicht erreichbar: {ollama_base}"
    except httpx.ReadTimeout:
        return ("❌ Timeout (420s) — qwen3-vl noch nicht geladen?\n"
                "Tipp: `ollama pull qwen3-vl:32b` und VRAM prüfen via planner.can_load.")

    if r.status_code == 404:
        return (f"❌ Modell '{model}' nicht in Ollama. Installation: `ollama pull {model}`\n"
                "VRAM-Hinweis: qwen3-vl:32b braucht ~20 GB. Bei 16 GB: erst gpt-oss-32k entladen.")
    if r.status_code != 200:
        return f"❌ Ollama HTTP {r.status_code}: {r.text[:200]}"

    content = ((r.json().get("message") or {}).get("content", "")).strip()
    if not content:
        return "❌ Leere Modellantwort von qwen3-vl."
    return f"VISUELLES REVIEW — {p.name}\n{'='*50}\n{content}"


if __name__ == "__main__":
    mcp.run()
