"""github-mcp — GitHub REST-API + Git-Operationen für die Issue→PR-Pipeline (I6).

Tools:
  get_issue(owner_repo, number)            — Issue-Text + Labels holen
  list_issues(owner_repo, state, limit)    — offene Issues auflisten
  clone_or_pull(owner_repo, local_dir)     — Repo clonen oder aktualisieren
  create_branch(local_path, branch_name)   — neuen Branch anlegen
  commit_push(local_path, branch, message) — alles stagen, committen, pushen
  create_pr(owner_repo, branch, title, body, base) — PR öffnen (V6-Gate!)

Sicherheitsregeln (I6-Pflicht):
  - Token kommt aus Umgebungsvariable GITHUB_TOKEN (nie hardcoded).
  - create_pr ist immer hinter V6-Gate (Bestätigung via mail.confirm_action).
  - Kein force-push, kein push auf main/master.
  - Token-Scope: nur eigene Repos, Contents R/W + Issues R + PRs R/W.

Start (stdio): python server.py
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from resilience import idempotent  # noqa: E402  (R3: PR/Push nie doppelt)

mcp = FastMCP("github-mcp")

_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
_API    = "https://api.github.com"
_CLONE_ROOT = Path(os.environ.get("GITHUB_CLONE_ROOT", r"n:\allinall\repos"))

_CLONE_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Interner Hilfscode
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    if not _TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN nicht gesetzt. "
            "Token erstellen: https://github.com/settings/tokens?type=beta "
            "Dann in n:\\allinall\\secrets.env eintragen und sync_secrets.py laufen lassen."
        )
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _api_get(path: str) -> dict | list:
    r = httpx.get(f"{_API}{path}", headers=_headers(), timeout=20)
    if r.status_code == 404:
        raise RuntimeError(f"GitHub 404: {path}")
    r.raise_for_status()
    return r.json()


def _api_post(path: str, body: dict) -> dict:
    r = httpx.post(f"{_API}{path}", headers=_headers(), json=body, timeout=20)
    r.raise_for_status()
    return r.json()


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if _TOKEN:
        env["GIT_ASKPASS"] = "echo"
        env["GIT_USERNAME"] = "x-token-auth"
        env["GIT_PASSWORD"] = _TOKEN
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env=env,
    )


def _remote_url(owner_repo: str) -> str:
    owner, _, repo = owner_repo.partition("/")
    if not repo:
        raise ValueError(f"owner_repo muss 'owner/repo' sein, nicht '{owner_repo}'")
    return f"https://x-token-auth:{_TOKEN}@github.com/{owner}/{repo}.git"


# ---------------------------------------------------------------------------
# MCP-Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_issue(owner_repo: str, number: int) -> str:
    """Holt Titel, Body und Labels eines GitHub-Issues.

    Args:
        owner_repo: 'owner/repo', z.B. 'meinname/meinprojekt'
        number:     Issue-Nummer (z.B. 4)

    Returns:
        Formatierter Issue-Text mit Titel, Labels, Body.
    """
    try:
        data = _api_get(f"/repos/{owner_repo}/issues/{number}")
    except RuntimeError as e:
        return f"[github-mcp] {e}"
    except httpx.HTTPStatusError as e:
        return f"[github-mcp] HTTP {e.response.status_code}: {e.response.text[:200]}"

    labels = ", ".join(lb["name"] for lb in data.get("labels", [])) or "—"
    return (
        f"Issue #{data['number']}: {data['title']}\n"
        f"Status: {data['state']}  |  Labels: {labels}\n"
        f"URL: {data['html_url']}\n\n"
        f"---\n{data.get('body') or '(kein Body)'}"
    )


@mcp.tool()
def list_issues(owner_repo: str, state: str = "open", limit: int = 20) -> str:
    """Listet Issues eines Repos auf.

    Args:
        owner_repo: 'owner/repo'
        state:      'open', 'closed' oder 'all' (Standard: 'open')
        limit:      Maximale Anzahl (Standard: 20)

    Returns:
        Tabellarische Liste mit Nummer, Titel, Labels.
    """
    try:
        data = _api_get(f"/repos/{owner_repo}/issues?state={state}&per_page={min(limit, 100)}")
    except RuntimeError as e:
        return f"[github-mcp] {e}"
    except httpx.HTTPStatusError as e:
        return f"[github-mcp] HTTP {e.response.status_code}: {e.response.text[:200]}"

    if not isinstance(data, list) or not data:
        return f"[github-mcp] Keine Issues gefunden (state={state})."

    lines = [f"Issues in {owner_repo} (state={state}):", ""]
    for issue in data[:limit]:
        labels = ", ".join(lb["name"] for lb in issue.get("labels", []))
        label_str = f"  [{labels}]" if labels else ""
        lines.append(f"  #{issue['number']:4d}  {issue['title']}{label_str}")
    return "\n".join(lines)


@mcp.tool()
def clone_or_pull(owner_repo: str, local_dir: str = "") -> str:
    """Clont ein Repo oder aktualisiert es (git pull), falls es schon da ist.

    Args:
        owner_repo: 'owner/repo'
        local_dir:  Lokaler Pfad (leer = automatisch n:\\allinall\\repos\\<repo>)

    Returns:
        Lokaler Pfad des Repos oder Fehlermeldung.
    """
    _, _, repo_name = owner_repo.partition("/")
    dest = Path(local_dir) if local_dir else _CLONE_ROOT / repo_name

    try:
        url = _remote_url(owner_repo)
    except (ValueError, RuntimeError) as e:
        return f"[github-mcp] {e}"

    try:
        if (dest / ".git").exists():
            r = _git(["pull", "--ff-only"], cwd=dest)
            status = "aktualisiert (git pull)"
        else:
            dest.mkdir(parents=True, exist_ok=True)
            r = _git(["clone", url, str(dest)], cwd=dest.parent)
            status = "geclont"
    except subprocess.CalledProcessError as e:
        return f"[github-mcp] git-Fehler:\n{e.stderr[-400:]}"
    except subprocess.TimeoutExpired:
        return "[github-mcp] git-Timeout (Repo zu groß?)"

    return f"Repo {owner_repo} {status}.\nLokal: {dest}\n{r.stdout.strip()}"


@mcp.tool()
def create_branch(local_path: str, branch_name: str) -> str:
    """Legt einen neuen Branch an (von aktuellem HEAD, z.B. main).

    KEIN Push — Branch ist nur lokal bis commit_push aufgerufen wird.

    Args:
        local_path:  Absoluter Pfad zum geclonten Repo
        branch_name: z.B. 'fix/issue-4'

    Returns:
        Bestätigung oder Fehlermeldung.
    """
    path = Path(local_path)
    if not (path / ".git").exists():
        return f"[github-mcp] Kein Git-Repo unter: {local_path}"

    forbidden = {"main", "master", "develop", "production"}
    if branch_name.lower() in forbidden:
        return f"[github-mcp] Branch '{branch_name}' ist gesperrt — nie direkt auf {forbidden} pushen."

    try:
        _git(["checkout", "-b", branch_name], cwd=path)
    except subprocess.CalledProcessError as e:
        return f"[github-mcp] Branch-Fehler:\n{e.stderr[-300:]}"

    return f"Branch '{branch_name}' angelegt in {local_path}."


@mcp.tool()
def commit_push(local_path: str, branch: str, message: str) -> str:
    """Stagt alle Änderungen, committet und pusht den Branch.

    Sicherheit: Kein force-push. Push nur auf den angegebenen Branch,
    niemals auf main/master/develop/production.

    Args:
        local_path: Absoluter Pfad zum geclonten Repo
        branch:     Branch-Name (muss mit create_branch angelegt worden sein)
        message:    Commit-Nachricht

    Returns:
        Bestätigung mit Push-Ausgabe oder Fehlermeldung.
    """
    path = Path(local_path)
    if not (path / ".git").exists():
        return f"[github-mcp] Kein Git-Repo unter: {local_path}"

    forbidden = {"main", "master", "develop", "production"}
    if branch.lower() in forbidden:
        return f"[github-mcp] Push auf '{branch}' verboten — nur Feature-Branches erlaubt."

    try:
        _git(["add", "-A"], cwd=path)
        status = _git(["status", "--short"], cwd=path)
        if not status.stdout.strip():
            return "[github-mcp] Keine Änderungen zum Committen."
        _git(["commit", "-m", message], cwd=path)
        push = _git(["push", "--set-upstream", "origin", branch], cwd=path)
    except subprocess.CalledProcessError as e:
        return f"[github-mcp] git-Fehler:\n{e.stderr[-400:]}"

    return f"Committed & gepusht auf '{branch}'.\n{push.stdout.strip() or push.stderr.strip()}"


@mcp.tool()
@idempotent(lambda owner_repo, branch, title, body, base="main":
            f"pr:{owner_repo}:{branch}:{base}")
def create_pr(
    owner_repo: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> str:
    """Öffnet einen Pull Request. IMMER hinter V6-Gate — zuerst mail.confirm_action aufrufen!

    Nutzungsregel (PFLICHT):
      1. Erst `mail.confirm_action(action='github_pr', ...)` — wartet auf GO.
      2. Erst nach GO dieses Tool aufrufen.

    Args:
        owner_repo: 'owner/repo'
        branch:     Feature-Branch (nicht main/master)
        title:      PR-Titel
        body:       PR-Beschreibung (Markdown)
        base:       Ziel-Branch (Standard: 'main')

    Returns:
        PR-URL oder Fehlermeldung.
    """
    forbidden = {"main", "master", "develop", "production"}
    if branch.lower() in forbidden:
        return f"[github-mcp] PR von '{branch}' verboten — nur Feature-Branches."

    try:
        data = _api_post(f"/repos/{owner_repo}/pulls", {
            "title": title,
            "body":  body,
            "head":  branch,
            "base":  base,
        })
    except RuntimeError as e:
        return f"[github-mcp] {e}"
    except httpx.HTTPStatusError as e:
        return f"[github-mcp] HTTP {e.response.status_code}: {e.response.text[:300]}"

    return (
        f"Pull Request erstellt!\n"
        f"  #{data['number']}: {data['title']}\n"
        f"  URL: {data['html_url']}\n"
        f"  {data['head']['ref']} -> {data['base']['ref']}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
