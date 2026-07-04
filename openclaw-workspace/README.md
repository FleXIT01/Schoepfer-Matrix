# Schöpfer-Matrix — OpenClaw-Integration (EINSATZBEREIT)

OpenClaw (das zentrale Hirn) ist eingerichtet und nutzt die lokalen Python-Fähigkeiten
über 5 MCP-Server. **End-to-End getestet:** ein Agent-Turn ruft echte MCP-Tools auf und
liefert echte Daten zurück. Gesamtarchitektur: `../MASTERPLAN_SCHOEPFER_MATRIX.txt`.

## Schnellstart

Vom Repo-Root `n:\allinall`:

```
matrix "Hol mir die ChEMBL-Daten zu Aspirin"
matrix "Finde Inhibitoren für EGFR und nenne die Targets"
matrix --probe     # listet alle MCP-Tools, die OpenClaw sieht
matrix --test      # testet alle 5 MCP-Server direkt
```

`matrix.cmd` setzt `OPENCLAW_STATE_DIR` und ruft den OpenClaw-Agenten auf.

## Was eingerichtet ist (verifiziert)

- **Hirn:** OpenClaw 2026.6.2 (`node openclaw-main/openclaw.mjs`), lokaler Modus.
- **Provider:** ollama (`models.providers.ollama.baseUrl = http://localhost:11434`).
- **Default-Modell:** `ollama/gpt-oss-32k` — gpt-oss:20b mit auf **32k erweitertem
  Kontext** (eigenes Modelfile, `PARAMETER num_ctx 32768`). NÖTIG, weil 8 MCP-Server
  = 32 Tool-Schemas (~10k Tokens) den Standard-Kontext (4096) sprengen → sonst
  „Ollama API stream ended" / Compaction-Loop. Passt mit ~14 GB komplett in die 16 GB GPU.
  (qwen2.5:14b / llama3.1:8b sind im Tool-Harness UNZUVERLÄSSIG — gpt-oss nehmen.)
- **Kontext-Budget:** `models.providers.ollama.contextTokens/contextWindow = 32768`,
  `agents.defaults.compaction.reserveTokens/reserveTokensFloor = 4096` (CLI-Pfad) und —
  **kritisch fürs Gateway/Telegram** — `models.providers.ollama.maxTokens = 4096`: der
  Output-Reserve = maxTokens, Default ist 16384 = die HALBE Kontextlänge → lange Chats
  liefen in „Context overflow". Mit 4096 bleibt das Prompt-Budget bei ~28.672 Tokens.
  **Nicht über 32k Kontext gehen** — 64k sprengt die 16 GB VRAM (Ollama-OOM).
- **State/Config:** `openclaw-workspace/state/openclaw.json` (isoliert, kein User-Default berührt).
- **8 MCP-Server registriert, 32 Tools** (per `openclaw mcp probe` bestätigt):
  - science (11): arXiv, PubMed, OpenAlex, EuropePMC, AlphaFold, RCSB-PDB, ChEMBL, STRING, Ensembl, Reactome, openFDA
  - llm (5): **Modell-Routing** — code_generate (codestral), vision_describe (qwen3-vl), reason_deep (gpt-oss), quick_answer (qwen2.5:7b), route_model
  - factory (3): list_capabilities, build_bot, verify_package
  - review (3): review_code, review_file, scan_repo
  - planner (3): get_resources, can_load, recommend
  - pdf (3): pdf_extract, pdf_summarize, pdf_translate (lokal via pypdf + ollama)
  - research (2): deep_research, web_lookup (lokale Tiefenrecherche, DuckDuckGo + Synthese)
  - knowledge (2): knowledge_search, knowledge_stats
- **Bildgenerierung:** ComfyUI/SDXL über den `comfy`-Provider (lokal, kein Cloud-Key).
  Start: **`comfy.cmd`** (Port 8188). End-to-end bewiesen via `openclaw infer image generate`.
- **8 Skills** in `skills/`: supervisor, drug-discovery, build-bot, deep-research,
  repo-review, knowledge-ask, **image-create**, **pdf-tools**.

## Tool-Namensschema im Agenten

OpenClaw exponiert MCP-Tools als `<server>__<tool>`, z.B. `science__chembl_search`,
`science__alphafold_fetch`, `knowledge__knowledge_search`, `review__scan_repo`.

## Direkter Aufruf (ohne Launcher)

```
set OPENCLAW_STATE_DIR=n:/allinall/openclaw-workspace/state
node n:/allinall/openclaw-main/openclaw.mjs agent --local --session-id s1 -m "deine Anfrage"
```

## Verwaltung

```
node openclaw-main/openclaw.mjs mcp list           # registrierte Server
node openclaw-main/openclaw.mjs mcp probe           # Server verbinden + Tools listen
node openclaw-main/openclaw.mjs mcp add <name> --command <py> --arg <server.py>
node openclaw-main/openclaw.mjs config get agents.defaults.model
```

Wissens-Index neu bauen (für knowledge-ask):
```
python n:\allinall\knowledge-ingest\ingest.py
```
MCP-Server isoliert testen:
```
python n:\allinall\mcp-servers\test_mcp.py all
```

## Wie das Routing funktioniert

Kein zentrales if/else. OpenClaws Agent-Loop wählt anhand der MCP-Tool-Schemas und der
Skill-`description`. Für mehrstufige Ziele zerlegt der `supervisor`-Skill und verteilt an
Spezialisten — mit Pflicht-Gates (`review`/`factory.verify_package`) vor „fertig".

## Telegram-Bot (eingerichtet, verifiziert, FUNKTIONIERT)

- Bot: **@pc_projekt_Bot**, channel telegram enabled, dmPolicy=open, **allowFrom=["*"]**.
- Dauerbetrieb: **`gateway.cmd`** im Repo-Root. **Sauberer Neustart:** erkennt beim Start
  ALLE vorigen Gateway-Sitzungen (per Kommandozeile, locale-unabhängig), fragt kurz nach
  (`J`/`N`, Default `J` nach 8 s) und beendet sie + die versteckte Windows-Aufgabe, bevor
  es neu startet. So entsteht NIE ein Telegram-Poll-Konflikt. Fenster offen lassen.
- **Autostart:** Verknüpfung „Schöpfer-Matrix Gateway" im Windows-Autostart-Ordner
  (`shell:startup`, minimiert) → Bot geht bei jeder Anmeldung automatisch online.
- Voraussetzung: Ollama läuft (Tray, Port 11434).
- Verifiziert: echte Telegram-Nachricht → Gateway → Agent-Turn → Antwort
  ("Inbound message telegram:... -> @pc_projekt_Bot" im Log).

### Zwei Fallstricke (beide behoben) — bei Telegram-Problemen zuerst prüfen
1. **allowFrom leer = Bot ignoriert alle lautlos.** Fix: `openclaw doctor --fix`
   (setzt allowFrom=["*"]). doctor --fix ist generell das erste Mittel.
2. **Nur EIN Gateway pro Bot-Token.** Mehrere Poller (z.B. die versteckte
   Scheduled Task "OpenClaw Gateway" + ein manuelles) → 409-Conflict → Telegram-Worker
   stirbt still. `gateway.cmd` räumt das jetzt selbst auf. Niemals `getUpdates`
   manuell aufrufen, während das Gateway läuft.
- Diagnose: Detail-Log `C:\Users\<user>\AppData\Local\Temp\openclaw\openclaw-YYYY-MM-DD.log`.

## Bildgenerierung (ComfyUI, lokal)

1. **`comfy.cmd`** starten (ComfyUI auf Port 8188; der mitgelieferte run_nvidia_gpu.bat
   zeigt auf ein altes V:-Laufwerk — daher comfy.cmd nutzen).
2. Im Chat: „erstelle ein Bild von …" → der `comfy`-Provider rendert via SDXL.
3. **VRAM (16 GB):** LLM (14 GB) + Bildmodell passen nicht gleichzeitig komplett rein.
   Für reine Bildarbeit ggf. `ollama stop gpt-oss-32k`; sonst lagert ComfyUI auf CPU aus
   (langsamer, aber funktioniert). Workflow: `comfy-workflow-sdxl.json`.

## Modell-Routing (llm-MCP)

Das Hirn (gpt-oss-32k) ruft je Aufgabe das passende lokale Spezialmodell als Tool:
`llm.code_generate`→codestral, `llm.vision_describe`→qwen3-vl, `llm.quick_answer`→qwen2.5:7b,
`llm.reason_deep`→gpt-oss, `llm.route_model` empfiehlt das passende Tool. Bei 16 GB VRAM
läuft immer nur EIN großes Modell — Wechsel kosten ~10–30 s (Modell-Swap).

## Cloud on-demand (OpenRouter / Claude)

Default-Hirn bleibt **lokal & gratis** (gpt-oss-32k). Cloud nur bei Bedarf, gestuft:
- `llm.cloud_cheap` → **DeepSeek v3.2** ($0,23/$0,34 pro Mio) — günstige Cloud-Qualität, Routine.
- `llm.cloud_reason` → **Claude Opus 4.8** ($5/$25) — TEUERSTE Stufe, NUR für wirklich
  schwere Aufgaben (nie für einfache Fragen; die Tool-Beschreibung erzwingt das).
- `llm.cloud_code` → **Claude Sonnet 4.6** ($3/$15) — nur wenn ausdrücklich gewünscht / komplex.
- Key in `models.providers.openrouter.apiKey` **und** im llm-MCP-env (`OPENROUTER_API_KEY`).
  Modelle via env: `OPENROUTER_MODEL` (reason=opus-4.8), `OPENROUTER_CODE_MODEL` (sonnet-4.6),
  `DEEPSEEK_MODEL` (v3.2).
- Direkt testen: `openclaw infer model run --model openrouter/anthropic/claude-sonnet-4.6 --prompt "…"`.

**Parallele Cloud-Subagenten** (vorbereitet, schlummernd): `agents.defaults.subagents.model`
zeigt auf Claude. Aktiv nur mit `tools.profile="full"` — dann kann der Dirigent Subagenten
spawnen. ACHTUNG: das lokale Hirn sammelt deren Ergebnisse unzuverlässig ein; zuverlässig
nur mit **Cloud-Hirn** (`agents.defaults.model` auf Cloud), was pro Nachricht kostet.
Default bewusst auf `coding`-Profil + lokalem Hirn (zuverlässig, günstig).

## Skills (installiert & ready)

Alle 8 Skills sind via `skills install` in `agent-workspace/skills/` installiert und
„ready" (knowledge-ask aktiviert via skills.entries.knowledge-ask.enabled=true).

## Noch offen (optional)

1. **Cloud-Modell** (optional): für noch stärkeres Reasoning einen anthropic/openai-Key
   konfigurieren und `agents.defaults.model` umstellen.
2. **Schwere Dienste** (MaxKB/WeKnora-RAG) bei Bedarf einrichten; der leichte
   `knowledge`-MCP deckt die Korpus-Suche vorerst ab.
3. **WhatsApp zusätzlich** (optional): `channels.whatsapp.enabled true` + QR scannen.
4. **Echte parallele Subagenten:** `tools.profile="coding"` entfernt die Agenten-Tools;
   der supervisor orchestriert daher als EIN Hirn sequenziell. Für echte Parallelität ein
   Profil mit Agenten-Tools wählen (am besten mit Cloud-Modell).
