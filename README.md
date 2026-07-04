# 🧠 Schöpfer-Matrix

**Ein persönlicher KI-Assistent, der komplett auf deinem eigenen PC läuft** — lokales
LLM, Telegram als Fernbedienung, 24 Werkzeug-Server mit 127 Tools, RAG-Wissensbasis,
Bild-Generierung, automatische Backups und eine Eval-Suite, die jede Änderung gegen
den alten Stand misst.

Kein Abo, keine Cloud-Pflicht: Das Hirn ist `gpt-oss:20b` via [Ollama](https://ollama.com)
auf der eigenen GPU (16 GB VRAM, 49k Kontext). Cloud-Modelle (DeepSeek/Claude via
OpenRouter) sind optionaler Fallback mit hartem Tagesbudget.

---

## Was sie kann

| Bereich | Beispiele im Telegram-Chat |
|---|---|
| 💬 **Assistent** | Fragen, Recherche („recherchiere gründlich …"), Zusammenfassungen, PDF-Berichte per `research_pdf_send` |
| 🖥️ **PC-Steuerung** | Programme starten, Dateien verwalten, Screenshots + Bildverständnis (qwen3-vl), echter Browser (Playwright, mit Freigabe-Gates) |
| 📚 **Wissensbasis (RAG)** | WeKnora-Stack (Qdrant + ParadeDB, bge-m3, BGE-Reranker): „such in unserer Wissensbasis nach …", automatisches Einlernen von Rechercheergebnissen |
| 🔬 **Wissenschaft** | PubMed, arXiv, ChEMBL, AlphaFold, RCSB PDB, OpenAlex, EuropePMC … (11 Science-Tools) |
| 📄 **Dokumente** | PDF erstellen, Word/Excel/PowerPoint lesen + schreiben |
| 🎨 **Bilder** | ComfyUI-Bildgenerierung direkt aus dem Chat |
| 🗣️ **Sprache** | Sprachnachrichten verstehen (Whisper) und antworten (Piper) — inkl. „mach mir einen Podcast über …" |
| 🔁 **Automatisierung** | n8n-Webhooks, Job-Queue für Langläufer, GitHub-Workflow (Issue → Branch → PR, mit Freigabe) |
| 💾 **Betrieb** | `/backup` per Chat, tägliche Backups, Morgenbriefing (arXiv-Watchlist + Systemstatus), Wochen-Retro mit Verbesserungsvorschlägen |

## Sicherheit ist eingebaut, nicht angeflanscht

- **Freigabe-Gates:** E-Mail-Versand, PRs, Browser-Eingaben brauchen ein explizites
  `GO <id>` im Chat — kritische Aktionen zusätzlich **TOTP** (Authenticator-App).
- **Kostenbremse:** Cloud-Calls haben ein Tageslimit (Standard 2 €) + Stundenlimit;
  bei Überschreitung wird geblockt statt gebucht.
- **Injektions-Quarantäne:** Inhalte aus Web/Mail/PDF sind *Daten*, niemals Befehle.
- **Domain-Allowlist** für den Browser, **Audit-Log** für jede scharfe Aktion,
  **Not-Aus** per Hotkey.
- **Telegram-Allowlist:** Der Bot antwortet nur dir.

## Zuverlässigkeit

- **Selbstheilung:** Gateway-Absturz → automatischer Neustart; `Strg+C` oder
  `stop.cmd` fährt *alles* sauber herunter (nichts „spannt wieder auf").
- **Watchdog** (alle 5 min): heilt den laufenden Stack, weckt aber nie ungewollt
  etwas auf; schlägt Alarm, wenn das jüngste Backup älter als 3 Tage ist.
- **Backups:** täglich 02:30 (state, MCP-Server, Skripte, eval, Skills,
  Docker-Volumes inkl. n8n) mit Aufbewahrung „14 Tage, aber nie unter 5 Backups";
  verpasste Läufe werden beim nächsten Hochfahren nachgeholt.
- **Golden-Eval-Suite:** 26 geseedete Testfälle prüfen das Tool-Routing des lokalen
  Modells deterministisch gegen eine Baseline — jede Prompt-/Tool-Änderung ist in
  ~30 Sekunden messbar (`run_eval.cmd`, nächtlich automatisch, Telegram-Alarm bei
  Regression).

## Architektur

```
Telegram ──► OpenClaw-Gateway (Node, Port 18789)
                │  System-Prompt: AGENTS.md (Werkzeug-Routing)
                ▼
         gpt-oss-32k @ Ollama (lokal, 49k Kontext, Flash-Attention, q8-KV)
                │
                ▼  Tool-Calls (MCP, stdio)
   24 MCP-Server / 127 Tools (Python)
   ├─ research / kb (WeKnora-RAG + Reranker) / science / knowledge
   ├─ assistant (run_command, backup_now, research_pdf_send) / screenshot / browser
   ├─ llm (Modell-Routing, Codestral, Vision, Cloud-Fallback + Budget)
   ├─ pdf / office / wiki / molviz / quiz / voice / mail / hook (n8n) / github / jobs
   └─ trace / status / planner / profile / factory / review
                │
                ▼
   Docker (optional): WeKnora-RAG · SearXNG · n8n        ComfyUI (Bilder)
```

## Installation

Siehe **[INSTALL.md](INSTALL.md)** — Kurzfassung:

```bat
:: Voraussetzungen: Windows, Python 3.12+, Node 22+, Ollama,
::                  OpenClaw-Release in openclaw-main\, optional Docker
install.cmd          :: prüft alles, richtet Konfiguration + Modell + Tasks ein
notepad secrets.env  :: Telegram-Token + Chat-ID eintragen (Minimum)
gateway.cmd          :: alles starten – Bot ist in ~1 Minute online
```

Alle Skripte sind **portabel**: kein Pfad ist hartkodiert, der Repo-Ordner darf
überall liegen. Maschinen-Konfiguration in `matrix.env`, alle Schlüssel in
`secrets.env` — beide werden nie committet.

## Bedienung

| Aktion | Befehl |
|---|---|
| Alles starten | `gateway.cmd` oder `python matrix.py up` |
| Alles stoppen | **Strg+C** im Gateway-Fenster, `stop.cmd` oder `python matrix.py stop` |
| Gesamtstatus (Dienste, VRAM, Tasks, Backup-Alter, Eval) | `status.cmd` / `matrix.py status` |
| Autostart beim PC-Boot an/aus | `autostart.cmd on` / `off` |
| Sofort-Backup | `/backup` im Chat oder `matrix.py backup` |
| Eval-Suite gegen Baseline | `run_eval.cmd` / `matrix.py eval` |
| Logs / Tool-Kontextbudget | `matrix.py logs` · `matrix.py budget` |

`matrix.py` ist das zentrale CLI (`up/stop/status/eval/backup/briefing/retro/budget/logs`)
— es delegiert an die getesteten Skripte. Architektur-Entscheidungen und geplante
Erweiterungen: **[ROADMAP.md](ROADMAP.md)**.

## Projektstruktur

```
├─ gateway.cmd / gateway_loop.ps1   Start + Supervisor (Selbstheilung)
├─ stop.cmd / stop_all.ps1          Alles sauber beenden
├─ install.cmd / INSTALL.md         Installation auf neuen Systemen
├─ env.cmd / matrix.env / secrets.env   zentrale Konfiguration (Templates im Repo)
├─ status.cmd / health.ps1          Gesamtstatus auf einen Blick
├─ watchdog.cmd / backup.cmd        Betrieb: Heilung, Backups, Alarme
├─ briefing.py / retro.py / mail_poll.py   Morgenbriefing, Wochen-Retro, Mail-Eingang
├─ mcp-servers/                     24 MCP-Server (Python, FastMCP)
├─ eval/                            Golden-Suite, Tool-Budget, Profile, Kataloge
├─ matrix.py                        zentrales CLI (up/stop/status/eval/…)
├─ openclaw-workspace/agent-workspace/   AGENTS.md (Werkzeug-Routing) + 21 Skills
└─ openclaw-main/                   OpenClaw (separat installieren, nicht im Repo)
```

## Voraussetzungen

- Windows 10/11, GPU mit ~16 GB VRAM (für gpt-oss:20b @ 49k; kleinere Modelle möglich)
- Python 3.12+, Node.js 22+, [Ollama](https://ollama.com)
- [OpenClaw](https://openclaw.ai)-Release, entpackt nach `openclaw-main\`
- Optional: Docker Desktop (RAG-Wissensbasis, SearXNG-Suche, n8n), ComfyUI, Piper/Whisper

## Ehrliche Grenzen

- Das Tool-Routing eines 20B-Modells ist fragil — genau deshalb gibt es die
  Golden-Suite mit Baseline-Diff. Prompt-Änderungen ohne Eval-Lauf sind Blindflug.
- Windows-only (Batch/PowerShell/Task-Scheduler); eine Linux-Portierung wäre
  ein eigenes Projekt.
- Antivirus mit HTTPS-Inspektion (z. B. Avast) bricht Python-TLS —
  `install.cmd` richtet den `truststore`-Fix automatisch ein.

---

*Gebaut als privates Projekt — ein PC, eine GPU, ein Telegram-Chat.*
