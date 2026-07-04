# Schöpfer-Matrix — Installation

Persönlicher KI-Assistent: lokales LLM (Ollama) + OpenClaw-Gateway + Telegram-Bot
+ 24 MCP-Server (127 Tools) + RAG, Backups, Watchdog, Eval-Suite.

## Voraussetzungen

| Was | Version | Woher |
|---|---|---|
| Windows | 10/11 | — |
| Python | 3.12+ | https://www.python.org/downloads/ |
| Node.js | 22+ | https://nodejs.org/ |
| Ollama | aktuell | https://ollama.com/download |
| OpenClaw | Release entpackt nach `openclaw-main\` | siehe unten |
| Docker Desktop | optional (RAG/WeKnora, SearXNG, n8n) | https://docker.com |
| GPU | 16 GB VRAM empfohlen (gpt-oss:20b @ 49k-Kontext) | — |

**OpenClaw:** Release herunterladen und so entpacken, dass
`<repo>\openclaw-main\openclaw.mjs` existiert.

## Installation (3 Schritte)

```bat
:: 1) Repo klonen / entpacken, dann im Repo-Ordner:
install.cmd

:: 2) secrets.env ausfüllen (mindestens):
::    TELEGRAM_BOT_TOKEN       (@BotFather -> /newbot)
::    TELEGRAM_DEFAULT_CHAT_ID (@userinfobot fragen)

:: 3) Starten:
gateway.cmd
```

`install.cmd` ist idempotent (mehrfach ausführbar) und erledigt:
Voraussetzungs-Check → pip-Pakete + `truststore`-Fix (wichtig bei
Antivirus-HTTPS-Inspektion wie Avast!) → `matrix.env`/`secrets.env` aus
Vorlagen → `openclaw.json` aus Template **mit auf deinen Ordner
umgeschriebenen Pfaden** → Ollama-Modell `gpt-oss-32k` (num_ctx 49152)
→ Hintergrund-Tasks (Backup 02:30, Eval 03:15, Briefing 07:00,
MailPoll/Watchdog alle 5 min, Retro So 20:00 — verpasste Läufe werden
nachgeholt).

## Bedienung

| Aktion | Befehl |
|---|---|
| Alles starten | `gateway.cmd` |
| Alles stoppen | **Strg+C** im Gateway-Fenster oder `stop.cmd` |
| Gesamtstatus | `status.cmd` |
| Sofort-Backup | `/backup` im Telegram-Chat oder Task 02:30 |
| Autostart beim PC-Boot an/aus | `autostart.cmd on` / `off` |
| Eval-Suite manuell | `run_eval.cmd` (nachts automatisch) |
| Sprachsteuerung (Push-to-Talk) | `voice.cmd` — F8 halten und sprechen (Gateway muss laufen) |

### Optional: Sprachsteuerung (Voice-PTT)

Python-Pakete kommen über `requirements.txt` mit. Zusätzlich nötig für
gesprochene Antworten: [Piper](https://github.com/rhasspy/piper/releases)
nach `piper\` entpacken + deutsche Stimme `de_DE-thorsten-medium.onnx` (+ `.json`)
von [HuggingFace](https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium)
ins gleiche Verzeichnis. Ohne Piper kommt die Antwort nur als Text im Fenster.
Taste/Modell konfigurierbar in `matrix.env` (`VOICE_PTT_KEY`, `WHISPER_MODEL`).

## Pfad-/Konfig-Prinzip

- **Kein Pfad ist hartkodiert:** alle Skripte leiten `MATRIX_ROOT` aus ihrem
  eigenen Speicherort ab (`env.cmd` bzw. `$PSScriptRoot`).
- **`matrix.env`** = Maschinen-Konfig (Python-Pfad, Backup-Ziel) — nicht im Git.
- **`secrets.env`** = alle Tokens/Keys — nicht im Git; `sync_secrets.py`
  überträgt sie nach `openclaw.json`.
- **`openclaw.json.template`** = Konfiguration mit `{{PLATZHALTERN}}`;
  `install.cmd` erzeugt daraus die echte `openclaw.json`.

## Bekannte Stolpersteine

- **Antivirus (Avast & Co.) bricht Python-HTTPS:** gelöst durch
  `truststore` + `sitecustomize.py` (macht `install.cmd` automatisch).
- **Batch-Dateien brauchen CRLF-Zeilenenden** — bei Git
  `core.autocrlf=true` auf Windows verwenden.
- **Telegram-Bot antwortet nicht nach Boot:** Gateway läuft nicht —
  `gateway.cmd` starten oder `autostart.cmd on`.
- **Backup-Ziel:** externes Laufwerk in `matrix.env` → `BACKUP_DEST` setzen;
  ohne Angabe wird `_backups\` im Repo-Ordner genutzt. Der Watchdog alarmiert
  per Telegram, wenn das jüngste Backup älter als 3 Tage ist.
