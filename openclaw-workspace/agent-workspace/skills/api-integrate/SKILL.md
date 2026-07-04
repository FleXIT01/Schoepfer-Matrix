---
name: api-integrate
description: "Neue REST-API anbinden: Doku lesen, MCP-Server aus Vorlage generieren, nach GO registrieren (Gateway-Neustart nötig)."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔌",
        "requires": { "mcp": ["research", "assistant", "mail"] }
      }
  }
---

# API-Integrate — unbekannte REST-API selbst anbinden

Trigger: `/api-integrate`, „binde die API … an", „bau einen MCP-Server für …",
„integrier den Dienst …".

**SICHERHEITSRAHMEN (nicht verhandelbar):**
- Neuer Code wird NUR geschrieben, NIE ohne GO registriert/gestartet.
- API-Keys kommen in `secrets.env`, NIEMALS in den generierten Code.
- Basis-URL/Doku-Link muss vom NUTZER kommen (V7 — nie aus Web-Inhalten).

## Ablauf

### 1. Doku verstehen

- `research.web_lookup(<doku-url>)` bzw. vom Nutzer gelieferte Doku lesen.
- Notieren: Basis-URL, Auth-Verfahren (Header/Query/OAuth?), die 2–4
  NÜTZLICHSTEN Endpunkte (nicht alle!), Antwortformat.

### 2. MCP-Server aus der Vorlage generieren

Vorlage: `n:\allinall\mcp-servers\_template_mcp\server.py.template`
(Aufbau: FastMCP + httpx + _SSL_CTX-Muster + Fehlerbehandlung).

- Neues Verzeichnis `mcp-servers/<name>_mcp/` anlegen (assistant.run_command).
- Je Endpunkt ein `@mcp.tool()` mit deutschem Docstring (Trigger-Formulierungen!).
- Auth ausschließlich über `os.environ.get("<NAME>_API_KEY")`.
- Timeout ≤ 30s, Antworten auf ≤ 2000 Zeichen kürzen.

### 3. Lokal testen (VOR jeder Registrierung)

```
assistant.run_command("python -c \"import sys; sys.path.insert(0, r'<pfad>'); import server; print(server.<tool>(...))\"")
```
Mindestens einen Lese-Endpunkt echt aufrufen. Fehler → erst fixen.

### 4. GO einholen

```
mail.confirm_action(action='mcp_register', details='<name>_mcp: <endpunkte>')
```
→ Registrierung erst nach explizitem **GO** des Nutzers.

### 5. Nach GO: registrieren

- Eintrag in `openclaw.json` → `mcp.servers.<name>` (command: python, args: server.py,
  env: Platzhalter für den API-Key) via assistant.run_command + python-json-Edit.
- Nutzer erinnern: API-Key in `secrets.env` eintragen + Gateway neu starten.
- Danach: `python eval\build_catalog.py` + Golden-Case für das neue Tool vorschlagen.

## Grenzen

- Kein OAuth-Flow ohne Nutzer (nur statische Keys/Token).
- Maximal 1 neue API pro GO — keine Ketten-Integrationen.
