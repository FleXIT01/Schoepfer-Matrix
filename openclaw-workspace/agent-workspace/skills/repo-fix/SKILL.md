---
name: repo-fix
description: "GitHub Issue → automatischer Fix-Branch → Pull Request. Eigenes Claude-Code-Äquivalent."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔧",
        "requires": { "mcp": ["github", "review", "mail"] }
      }
  }
---

# repo-fix (I6) — Issue→PR-Pipeline

Trigger: „fix Issue #N in <repo>", „bearbeit Issue", „erstell einen PR für #N",
„schau dir Issue #N an und fix es", „Issue→PR".

---

## Sicherheitsregeln (IMMER einhalten)

- **Kein Push auf main/master/develop** — immer Feature-Branch `fix/issue-N`.
- **PR erst nach GO** — `mail.confirm_action(action='github_pr', ...)` aufrufen und
  auf Bestätigung warten, DANN erst `github.create_pr()`.
- **Kein force-push** — `commit_push` erlaubt das nicht (hardcoded).
- Token-Scope: nur eigene Repos. Fremde Repos → ablehnen, Nutzer informieren.

---

## Ablauf

### 1. Issue verstehen

```
github.get_issue(owner_repo="owner/repo", number=N)
```

→ Issue-Titel + Body lesen. Bei unklarem Issue: STOPP, beim Nutzer nachfragen.

### 2. Repo holen

```
github.clone_or_pull(owner_repo="owner/repo")
```

→ gibt lokalen Pfad zurück (z.B. `n:\allinall\repos\meinprojekt`).

### 3. Codebase verstehen (optional aber empfohlen)

```
wiki.document_repo(repo_path=<lokaler_pfad>)
```

→ Überblick über Architektur, bevor Änderungen gemacht werden.

### 4. Feature-Branch anlegen

```
github.create_branch(local_path=<pfad>, branch_name="fix/issue-N")
```

### 5. Fix implementieren (SELBST erledigen)

Direkt Dateien im geclonten Repo bearbeiten — kein extra Tool.
Regeln:
- Minimale Änderungen: nur was das Issue behebt, keine Refactors nebenbei.
- Tests anpassen/ergänzen, wenn vorhanden.
- Commit-Message: `fix: <Issue-Titel> (closes #N)`

### 6. Code reviewen

```
review.review_code(code=<geänderter_code>, context=<issue_beschreibung>)
```

→ Falls Review NICHT grün → Probleme beheben, dann nochmal reviewen.
→ Erst wenn Review grün: weiter zu Schritt 7.

### 7. Committen & pushen

```
github.commit_push(
    local_path=<pfad>,
    branch="fix/issue-N",
    message="fix: <Issue-Titel> (closes #N)"
)
```

### 8. GO-Gate — PR erst nach Bestätigung!

```
mail.confirm_action(
    action="github_pr",
    description="PR öffnen: fix/issue-N → main in owner/repo",
    details="Titel: ...\nBranch: fix/issue-N\nIssue: #N"
)
```

→ Warten auf GO vom Nutzer. Bei NEIN: PR nicht öffnen, Nutzer informieren.

### 9. Pull Request öffnen (nur nach GO)

```
github.create_pr(
    owner_repo="owner/repo",
    branch="fix/issue-N",
    title="fix: <Issue-Titel>",
    body="Behebt #N.\n\n## Änderungen\n...\n\n## Review\n<Review-Zusammenfassung>",
    base="main"
)
```

→ PR-URL ausgeben.

### 10. Melden

Telegram-Nachricht: Issue #N, PR-URL, kurze Zusammenfassung was geändert wurde.

---

## Fehlerfälle

- `GITHUB_TOKEN nicht gesetzt` → Nutzer auf `n:\allinall\secrets.env` + `sync_secrets.py` hinweisen.
- Review meldet kritische Probleme → Fix überarbeiten, nicht einfach ignorieren.
- `clone_or_pull` schlägt fehl → Repo-Name prüfen (muss `owner/repo` sein).
- Branch existiert schon → anderen Namen wählen (`fix/issue-N-v2`) oder Nutzer fragen.
- Issue in fremdem Repo → ablehnen: „Token ist nur für eigene Repos konfiguriert."
