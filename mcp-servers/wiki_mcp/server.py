"""wiki-mcp — Repo -> Architektur-Wiki/README als MCP-Server.

Verwandelt ein Code-Repository automatisch in eine lesbare Architektur-Doku:
Struktur-Scan (Verzeichnisbaum + Sprachen) + AST-Extraktion der öffentlichen
Python-API (Module/Klassen/Funktionen + Docstrings) + Synthese durch ein Modell.
Ersetzt die Rolle von deepwiki/repo-to-wiki — self-contained, kein Cloud-Key nötig
(lokales Ollama als Default; via WIKI_MODEL umstellbar).

Tools:
  - repo_tree(repo_path)      -> kompakter Struktur-/Sprachen-Überblick (ohne Modell)
  - document_repo(repo_path)  -> fertige Architektur-Doku als Markdown (mit Modell)

Start (stdio):  python server.py
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wiki-mcp")

_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_MODEL = os.environ.get("WIKI_MODEL", "gpt-oss-32k")

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".next", ".cache", "site-packages", ".mypy_cache",
              ".pytest_cache", "target", ".idea", ".vscode", "coverage"}
_CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".rb",
             ".c", ".cpp", ".h", ".cs", ".php", ".kt", ".swift", ".scala", ".sh"}
_DOC_NAMES = {"readme.md", "readme.rst", "readme.txt", "package.json",
              "pyproject.toml", "requirements.txt", "cargo.toml", "go.mod"}


def _ollama_chat(messages: list[dict], *, timeout: float = 360.0,
                 num_ctx: int = 32768) -> str:
    import httpx

    payload = {"model": _MODEL, "messages": messages, "stream": False,
               "options": {"num_ctx": num_ctx}}
    try:
        r = httpx.post(f"{_OLLAMA}/api/chat", json=payload, timeout=timeout)
    except httpx.ConnectError:
        return f"[Fehler: Ollama nicht erreichbar unter {_OLLAMA}.]"
    except httpx.ReadTimeout:
        return f"[Fehler: Zeitüberschreitung ({timeout:.0f}s) bei Modell '{_MODEL}'.]"
    if r.status_code != 200:
        return f"[Fehler: Ollama HTTP {r.status_code}: {r.text[:200]}]"
    return ((r.json().get("message") or {}).get("content", "").strip()
            or "[Fehler: leere Modellantwort.]")


def _walk(root: Path, max_files: int = 400):
    """Sammelt relevante Dateien (überspringt Build-/Dep-Ordner)."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in _CODE_EXT or fn.lower() in _DOC_NAMES:
                files.append(p)
            if len(files) >= max_files:
                return files
    return files


def _lang_stats(files: list[Path]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        if ext in _CODE_EXT:
            stats[ext] = stats.get(ext, 0) + 1
    return dict(sorted(stats.items(), key=lambda kv: -kv[1]))


def _py_api(path: Path) -> str:
    """Extrahiert öffentliche API (Modul-Docstring, Klassen, Funktionen) via AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return ""
    lines = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        lines.append(f"  \"\"\"{mod_doc.strip().splitlines()[0]}\"\"\"")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            lines.append(f"  class {node.name}")
            d = ast.get_docstring(node)
            if d:
                lines.append(f"    # {d.strip().splitlines()[0]}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                    lines.append(f"    def {sub.name}(...)")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            args = ", ".join(a.arg for a in node.args.args)
            lines.append(f"  def {node.name}({args})")
            d = ast.get_docstring(node)
            if d:
                lines.append(f"    # {d.strip().splitlines()[0]}")
    return "\n".join(lines)


def _build_digest(root: Path, files: list[Path]) -> str:
    """Baut einen kompakten Struktur-Digest fürs Modell."""
    parts = [f"REPO: {root.name}", f"Pfad: {root}", ""]
    stats = _lang_stats(files)
    if stats:
        parts.append("Sprachen (Dateien): " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    parts.append(f"Relevante Dateien: {len(files)}")
    parts.append("")

    # READMEs / Manifeste zuerst (geben den meisten Kontext)
    for f in files:
        if f.name.lower() in _DOC_NAMES:
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")[:1500]
            except Exception:  # noqa: BLE001
                continue
            parts.append(f"--- {f.relative_to(root)} ---\n{txt}\n")

    # Python-API extrahieren
    parts.append("=== ÖFFENTLICHE PYTHON-API (AST) ===")
    py_count = 0
    for f in files:
        if f.suffix.lower() == ".py":
            api = _py_api(f)
            if api:
                parts.append(f"# {f.relative_to(root)}\n{api}")
                py_count += 1
        if py_count >= 60:
            parts.append("…(weitere Python-Dateien abgeschnitten)")
            break

    digest = "\n".join(parts)
    return digest[:22000] + ("\n…[gekürzt]" if len(digest) > 22000 else "")


@mcp.tool()
def repo_tree(repo_path: str, max_files: int = 400) -> str:
    """Schneller Struktur-/Sprachen-Überblick eines Repos (ohne Modell).
    Für: erstmal sehen, woraus ein Repo besteht. `repo_path` = Pfad zum Repo."""
    root = Path(repo_path)
    if not root.exists():
        return f"[Fehler: Pfad nicht gefunden: {repo_path}]"
    files = _walk(root, max_files)
    stats = _lang_stats(files)
    lines = [f"REPO: {root.name} ({root})",
             f"Relevante Dateien: {len(files)}",
             "Sprachen: " + (", ".join(f"{k}={v}" for k, v in stats.items()) or "—"),
             "", "Top-Verzeichnisse:"]
    top: dict[str, int] = {}
    for f in files:
        rel = f.relative_to(root)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        top[top_dir] = top.get(top_dir, 0) + 1
    for d, n in sorted(top.items(), key=lambda kv: -kv[1])[:25]:
        lines.append(f"  {d}/  ({n} Dateien)")
    return "\n".join(lines)


@mcp.tool()
def document_repo(repo_path: str, focus: str = "") -> str:
    """Erzeugt eine Architektur-Doku (Markdown) für ein Repo: Zweck, Hauptkomponenten,
    Datenfluss, wichtige Module, Einstiegspunkte. Für: ein fremdes/eigenes Repo schnell
    verstehen oder dokumentieren. `repo_path` = Pfad, `focus` = optionaler Schwerpunkt."""
    root = Path(repo_path)
    if not root.exists():
        return f"[Fehler: Pfad nicht gefunden: {repo_path}]"
    files = _walk(root)
    if not files:
        return f"[Fehler: keine Code-/Doku-Dateien in {repo_path} gefunden.]"
    digest = _build_digest(root, files)
    focus_line = f" Schwerpunkt: {focus}." if focus.strip() else ""
    prompt = (
        f"Du bist ein Software-Architekt. Erstelle aus der folgenden Repo-Struktur "
        f"eine klare deutsche Architektur-Doku als Markdown mit den Abschnitten: "
        f"## Zweck, ## Hauptkomponenten, ## Datenfluss/Ablauf, ## Wichtige Module, "
        f"## Einstiegspunkte, ## Tech-Stack.{focus_line} Stütze dich NUR auf die "
        f"gegebenen Infos, erfinde keine Details.\n\n=== REPO-DIGEST ===\n{digest}"
    )
    doc = _ollama_chat([{"role": "user", "content": prompt}])
    return f"# Architektur-Wiki: {root.name}\n\n" + doc


_MATRIX_ROOT = Path(r"n:\allinall")
_ARTICLE_DIR = _MATRIX_ROOT / "articles"

_ARTICLE_TOPICS = {
    "überblick":   "Das Gesamtsystem: Architektur, Ziel, Zusammenspiel der Komponenten",
    "routing":     "Wie Anfragen intern geroutet werden (AGENTS.md, MCP-Server, Modelle)",
    "sicherheit":  "Sicherheitskonzept: Approval-Gates, Injection-Schutz, Kosten-Deckel",
    "fabrik":      "factory-mcp: Bots automatisch generieren und in Docker verifizieren",
    "wissensbasis":"WeKnora/RAG: Hybrid-Search, Embeddings, Ingest-Pipeline",
    "stimme":      "voice-mcp und Telegram: Die Matrix auf dem Handy",
    "council":     "Rat der Modelle: eingebaute Zweitmeinung mit Widerspruchs-Markierung",
}


@mcp.tool()
def list_article_topics() -> str:
    """Listet die vorgefertigten Artikel-Themen für 'build_in_public'.
    Für: sehen, über welche Aspekte der Matrix ein Artikel geschrieben werden kann."""
    lines = ["Verfügbare Artikel-Themen (Schlüssel → Beschreibung):", ""]
    for key, desc in _ARTICLE_TOPICS.items():
        lines.append(f"  {key:15s} — {desc}")
    lines.append("")
    lines.append("Freie Themen sind ebenfalls möglich (topic='...' als Text).")
    return "\n".join(lines)


@mcp.tool()
def build_in_public(topic: str = "überblick", save: bool = True) -> str:
    """Schreibt einen Blog-Artikel über die Schöpfer-Matrix — 'Build in public'.
    Stützt sich auf den tatsächlichen Code (wiki.repo_tree + AST-Scan), kein Raten.
    topic: Schlüssel aus list_article_topics() ODER freier Themensatz.
    save=True: Artikel als Markdown in n:/allinall/articles/ speichern.
    Für: Trigger 'schreib einen Artikel', 'build in public', 'dokumentiere dich selbst'."""
    if not _MATRIX_ROOT.exists():
        return f"[Fehler: Matrix-Root nicht gefunden: {_MATRIX_ROOT}]"

    # Beschreibung auflösen
    desc = _ARTICLE_TOPICS.get(topic.lower().strip(), topic)

    files = _walk(_MATRIX_ROOT)
    digest = _build_digest(_MATRIX_ROOT, files)

    prompt = (
        "Du schreibst einen deutschen Blog-Artikel für ein Automatisierungs-Business-Portfolio. "
        "Stil: klar, persönlich, technisch ehrlich — kein Marketing-Sprech. "
        "Zielgruppe: technik-affine Leser, die verstehen wollen WIE so ein System gebaut wird. "
        "Zeige konkrete Entscheidungen, Schwierigkeiten, Lösungen. "
        "Keine Buzzwords wie 'KI-Revolution'. "
        "Format: Markdown-Artikel mit ## Abschnitten, ca. 600–900 Wörter. "
        f"Thema: {desc}. "
        "Stütze dich NUR auf den folgenden tatsächlichen Code-Digest — erfinde keine Details.\n\n"
        f"=== MATRIX-DIGEST ===\n{digest}"
    )

    article = _ollama_chat([{"role": "user", "content": prompt}], num_ctx=32768)

    slug = topic.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")[:40]
    header = f"# Schöpfer-Matrix: {desc}\n\n*Automatisch generiert von wiki.build_in_public — {slug}*\n\n"
    full = header + article

    if save:
        _ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
        out = _ARTICLE_DIR / f"{slug}.md"
        out.write_text(full, encoding="utf-8")
        return full + f"\n\n---\n*Gespeichert: {out}*"

    return full


if __name__ == "__main__":
    mcp.run()
