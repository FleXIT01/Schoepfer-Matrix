# Bot Generator

Ein CLI-Tool, das aus einer Beschreibung automatisch einen **echten, lauffähigen Bot** baut — inklusive Verifikation und Selbstreparatur durch ein Multi-Agenten-System.

---

## Was passiert wenn du einen Bot generierst

```
Du beschreibst den Bot      →   Interview (max. 5 Rückfragen)
                            →   Spezifikation + 4 Doku-Dateien
                            →   Agent-Build (Architekt → Coder → Gates → Fixer)
                            →   Lauffähiges bot/-Paket + BUILD_REPORT.md
                            →   Echter Test gegen das lokale Modell (Abnahme)
```

Der Unterschied zu früher: der generierte Bot **kann wirklich etwas tun** (Dateien lesen, Code ausführen, HTTP-Requests, SQLite-Store ...) — und das System **prüft und repariert** den generierten Code solange, bis er die Verifikations-Gates besteht.

---

## Voraussetzungen

- Python 3.10+
- Für lokale Bots ohne API-Key: [Ollama](https://ollama.com) installiert + mindestens ein Modell geladen

```powershell
# Empfohlene Modelle (lokal, kein API-Key nötig)
ollama pull qwen2.5:7b        # schnell, gut für einfache Bots
ollama pull qwen2.5:14b       # besser für komplexen Code
ollama pull codestral:latest  # sehr gut für Coding-Bots
ollama pull llama3.1:8b       # guter Allrounder
```

---

## Schnellstart

```powershell
# 1. Repo / Ordner öffnen
cd C:\Users\Farnberger\Documents\bot\bot1

# 2. Virtuelle Umgebung anlegen und aktivieren
python -m venv .venv
.venv\Scripts\activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Starten — Ollama läuft automatisch wenn nötig
python main.py

# Oder direkt mit Provider und Modus
python main.py classic --provider anthropic
python main.py classic --provider ollama --model qwen2.5:14b
python main.py blueprint
```

---

## Provider

| Provider | Voraussetzung | .env |
|---|---|---|
| `ollama` **(Standard)** | Ollama lokal, `ollama pull <modell>` | — |
| `anthropic` | Anthropic-Account | `ANTHROPIC_API_KEY=sk-ant-...` |
| `openai` | OpenAI-Account | `OPENAI_API_KEY=sk-...` |
| `lmstudio` | LM Studio lokal | — |
| `openai-compat` | Beliebiger OpenAI-kompatibler Endpoint | `LLM_API_BASE=https://...` |

```powershell
copy .env.example .env
# .env öffnen, API-Key eintragen
```

> **Tipp Ollama:** Falls Ollama beim Start nicht läuft, öffnet der Bot Generator automatisch ein neues Terminal-Fenster mit `ollama serve` und wartet bis zu 20 Sekunden.

---

## Modi

### `classic` — vollständiger Bot mit Verifikation *(empfohlen)*

```powershell
python main.py classic
```

1. **Interview** — bis zu 5 gezielte Rückfragen zum Bot-Zweck
2. **Spezifikation** — vollständige BotSpec + 4 Doku-Dateien
3. **Agent-Build** — Architekt plant Tools, Coder generiert Code, Gates prüfen, Fixer repariert
4. **Abnahme** — einmaliger echter Lauf gegen das lokale Modell

### `blueprint` — schnelle Entscheidungshilfe

```powershell
python main.py blueprint
```

Ein kurzes Gespräch → eine kompakte `blueprint.md` mit: Zweck, 5 Use Cases, Provider-Empfehlung, Architektur, Komplexitätsschätzung, Empfehlung für den Classic-Modus.

---

## Ablauf Classic (Beispiel)

```
Welche Art von Bot soll ich für dich generieren?
> Ich brauche einen Bot der Python-Code-Snippets erklärt und ausführt

Wer sind die Hauptnutzer?
> Entwickler die schnell Code testen wollen

[1/4] Anforderungen...
[2/4] Architektur...
[3/4] Prompt-Paket...
[4/4] JSON-Schemas...

Baue jetzt einen echten, verifizierten Bot...
  · Architekt plant Tools...
  · Coder generiert Tool 'code_erklaeren'...
  · Verifiziere Gesamtpaket...
  · Bot verifiziert — alle Gates grün.
  · Finaler Lauf gegen das lokale Modell erfolgreich.

✅ output\codebot_20260605T120000

Starte den Bot mit:
  cd "output\codebot_20260605T120000"
  pip install -r requirements.txt
  python run.py
```

---

## Ausgabe (Classic)

```
output/{bot-name}_{timestamp}/
├── requirements.md        Anforderungen, Use Cases, Zielgruppe
├── architecture.md        LLM-Wahl, Architektur, Datenfluss
├── prompt_package.md      System-Prompt, Beispiel-Konversationen, Developer Notes
├── schemas.json           Input/Output/State-Schemas
├── bot_spec.json          Vollständige maschinenlesbare Spezifikation
├── BUILD_REPORT.md        Verifikations-Protokoll (welche Gates grün, Anzahl Fixes)
├── bot/
│   ├── config.py          BotConfig (alle Parameter)
│   ├── memory.py          Konversationshistorie (in_session oder persistent_json)
│   ├── llm_client.py      Provider-agnostischer LLM-Client (injizierbar für Tests)
│   ├── tools.py           Echte Tool-Implementierungen + dispatch()
│   └── runner.py          BotRunner mit Laufzeit-Tool-Loop
├── run.py                 Einstiegspunkt → python run.py
├── test_smoke.py          Offline-Selbsttest (kein Modell nötig)
└── requirements.txt       Abhängigkeiten des generierten Bots
```

### Den generierten Bot starten

```powershell
cd output\{bot-name}_{timestamp}
pip install -r requirements.txt
python run.py
# → Bot startet interaktive Terminal-Session
```

### Offline-Test (kein Modell nötig)

```powershell
python test_smoke.py
# → SMOKE_OK wenn der Bot syntaktisch korrekt und instanziierbar ist
```

---

## Verfügbare Tool-Bibliothek

Tools die der Architekt dem Bot automatisch zuweist wenn sie passen:

| Tool | Beschreibung |
|---|---|
| `read_file` | Liest den Textinhalt einer lokalen Datei |
| `write_file` | Schreibt Text in eine lokale Datei |
| `run_python` | Führt Python-Code in einem isolierten Subprozess aus (Timeout 15s) |
| `web_fetch` | Ruft den Textinhalt einer URL per HTTP GET ab |
| `http_request` | Allgemeiner HTTP-Request (GET/POST/PUT/DELETE) |
| `sqlite_store` | Persistenter Key-Value-Speicher (SQLite, `set`/`get`) |

Tools die nicht aus der Bibliothek kommen, werden **generiert und getestet** (Coder → Gate → Fixer bis zu 4 Versuche). Falls nicht reparierbar: sicherer Stub (Bot bleibt lauffähig).

---

## Wie der Laufzeit-Tool-Loop funktioniert

Der Bot kommuniziert Tools über JSON — kein natives Function-Calling nötig (funktioniert mit jedem lokalen Modell):

```
Bot-Anfrage "Lies bitte README.md"
  → Modell antwortet: {"tool": "read_file", "args": {"path": "README.md"}}
  → BotTools.dispatch("read_file", {"path": "README.md"}) → Dateiinhalt
  → Modell bekommt: [TOOL-ERGEBNIS read_file]: ...Inhalt...
  → Modell formuliert finale Antwort
```

---

## Verifikations-Gates

Der Orchestrator prüft jede Einheit **im Subprozess gegen eine temp-Kopie** (kein laufendes Modell nötig, isoliert, mit Timeout):

| Gate | Was wird geprüft |
|---|---|
| **syntax** | `ast.parse` — syntaktisch korrekt? |
| **import** | `python -c "import bot.runner"` — importierbar? |
| **smoke** | `BotRunner(llm=MockLLM()).respond("Hallo")` gibt str zurück? |
| **tool** | Tool-Funktion läuft ohne Absturz auf Beispiel-Input? |
| **tool_loop** | Laufzeit-JSON-Dispatch macht ≥ 2 LLM-Aufrufe? |

Schlägt ein Gate fehl: Fixer bekommt den echten Traceback und repariert. Nach `MAX_FIX_ATTEMPTS` Versuchen: Stub einsetzen, Paket bleibt grün.

---

## Konfiguration (.env)

```
LLM_PROVIDER=ollama          # anthropic | openai | ollama | lmstudio | openai-compat
LLM_MODEL=                   # leer = Provider-Default (z.B. llama3.1 bei Ollama)
LLM_API_BASE=                # optional: abweichender API-Endpunkt
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OUTPUT_DIR=output
MAX_FOLLOWUP_QUESTIONS=5
AGENT_MAX_FIX_ATTEMPTS=4     # Max. Reparatur-Versuche pro Tool
AGENT_MAX_GLOBAL_ITERS=3     # Max. Projekt-Reparaturrunden
SANDBOX_TIMEOUT=30           # Sekunden Timeout pro Gate-Subprozess
AGENT_FINAL_REAL_RUN=1       # 0 = finalen echten Lauf überspringen
```

---

## CLI-Argumente

```powershell
python main.py [classic|blueprint] [--provider PROVIDER] [--model MODEL]
```

```powershell
python main.py                                    # fragt Modus + Modell interaktiv ab
python main.py classic                            # Classic, Provider aus .env
python main.py classic --provider anthropic       # überschreibt .env-Provider
python main.py classic --provider ollama --model qwen2.5:14b
python main.py blueprint --provider openai --model gpt-4o
```

---

## Tests ausführen

```powershell
# Deterministische Gate- und Orchestrator-Suite (kein Modell nötig, ~10 Sek.)
python tests/run_checks.py
# → 16 bestanden, 0 fehlgeschlagen

# Echter End-to-End-Build gegen lokales Ollama
python tests/real_run.py qwen2.5:7b
python tests/real_run.py qwen2.5:14b
```

---

## Projektstruktur

```
bot1/
├── main.py                      Einstiegspunkt + Provider/Modus-Auswahl
├── requirements.txt
├── .env.example
├── tests/
│   ├── run_checks.py            Deterministische Suite (Gates + Orchestrator)
│   └── real_run.py              Echter End-to-End-Lauf gegen Ollama
└── generator/
    ├── config.py                Alle Env-Variablen + Agent-Konstanten
    ├── llm/                     LLM-Adapter (Anthropic, OpenAI, Ollama, Compat, Mock)
    ├── models/                  BotSpec + InterviewState (Pydantic)
    ├── interview/               Interview-Schleife, Extraktor, alle Prompts
    ├── spec/                    BotSpecBuilder (InterviewState → BotSpec)
    ├── blocks/                  Block 1-4 Renderer (Doku-Generierung)
    ├── templates/               Jinja2-Templates für Doku-Blöcke
    ├── modes/                   ClassicModeRunner, BlueprintModeRunner
    ├── writer/                  Schreibt Doku-Dateien auf Disk
    ├── cli/                     Rich-Terminal-Interface (Spinner, Farben)
    └── agent/                   Multi-Agenten-Build-System
        ├── orchestrator.py      Controller-Schleife (reine Python-Logik)
        ├── package_builder.py   Deterministischer Bot-Paket-Erzeuger
        ├── build_plan.py        Pydantic: BuildPlan, FileTask, ToolTask
        ├── report.py            BUILD_REPORT.md Renderer
        ├── agents/              ArchitectAgent, CoderAgent, FixerAgent
        ├── verify/              sandbox.py, gates.py, mock_llm.py
        └── tools/               library.py + impl/ (6 geprüfte Tools)
```

---

## Eigenen LLM-Provider einbinden

```python
from generator.llm.base import BaseLLMAdapter, LLMMessage

class MeinAdapter(BaseLLMAdapter):
    def _call_api(self, messages, system, temperature, max_tokens, force_json) -> str:
        # force_json=True → JSON-Constraint im System-Prompt oder native JSON-Mode
        # self._append_json_constraint(system) fügt deutschen JSON-Hinweis an
        ...

# Nutzen:
from generator.modes.classic_mode import ClassicModeRunner
runner = ClassicModeRunner()
runner.run(cli=cli, llm=MeinAdapter())
```

---

## Modell-Empfehlungen (Ollama, lokal)

| Modell | Stärke | Empfehlen für |
|---|---|---|
| `qwen2.5:7b` | schnell, gutes Deutsch | einfache Bots, Tests |
| `qwen2.5:14b` | ausgewogen | Standard-Empfehlung |
| `codestral:latest` | Code-Spezialist | Coding-Bots, Tool-Generierung |
| `llama3.1:8b` | guter Allrounder | allgemeine Bots |
| `gemma3:27b` | sehr gut | komplexe Bots mit vielen Tools |
