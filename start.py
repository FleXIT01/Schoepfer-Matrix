#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║              UNIVERSELLE SCHÖPFER-MATRIX — START                    ║
║                                                                      ║
║  Einziger Einstiegspunkt für das gesamte AI-OS Ökosystem.           ║
║  Steuert 36 Repositories, 5 Agenten, 84+ Tools.                    ║
║                                                                      ║
║  Modi:                                                               ║
║    python start.py                    → Interaktiver Modus           ║
║    python start.py build              → Einzel-Build (wie bisher)    ║
║    python start.py worldloop          → Autonome Endlos-Schleife     ║
║    python start.py serve              → Server: Webhooks + World-Loop ║
║    python start.py grill <thema>      → Architektur-Interview         ║
║    python start.py status             → System-Status anzeigen       ║
║    python start.py heal               → Self-Healing Scan            ║
╚══════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Projekt-Root (N:\allinall) und bot1 auf den Pfad setzen
ALLINALL_ROOT = Path(__file__).resolve().parent
BOT1_ROOT = ALLINALL_ROOT / "bot1"
sys.path.insert(0, str(BOT1_ROOT))

# Windows-Terminal: UTF-8 erzwingen (sonst crashen Emojis auf cp1252)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("omega")

# Externe Bibliotheken + interne Registry-Logs reduzieren
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("generator.agent.services.service_registry").setLevel(logging.WARNING)


_GLOBAL_MODEL_CACHE = None
_OPENCLAW_BRIDGE_PROC = None


def _ensure_openclaw_bridge(port: int = 18789) -> bool:
    """Startet die OpenClaw-Python-Bridge wenn sie nicht läuft."""
    global _OPENCLAW_BRIDGE_PROC
    import httpx
    import subprocess
    import time

    # Läuft schon?
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        if r.status_code == 200:
            logger.info("OpenClaw-Bridge läuft bereits auf Port %d", port)
            return True
    except Exception:
        pass

    # Starten
    logger.info("Starte OpenClaw-Bridge auf Port %d…", port)
    try:
        bridge_script = str(BOT1_ROOT / "generator" / "agent" / "services" / "openclaw_bridge.py")
        _OPENCLAW_BRIDGE_PROC = subprocess.Popen(
            [sys.executable, bridge_script, "--port", str(port), "--model",
             _GLOBAL_MODEL_CACHE or "llama3.1:8b"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Warte max 8s auf Start
        for _ in range(8):
            time.sleep(1)
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                if r.status_code == 200:
                    logger.info("OpenClaw-Bridge bereit auf Port %d", port)
                    return True
            except Exception:
                pass
        logger.warning("OpenClaw-Bridge nicht rechtzeitig gestartet.")
        return False
    except Exception as exc:
        logger.warning("OpenClaw-Bridge konnte nicht gestartet werden: %s", exc)
        return False

def _create_llm(model_override: str | None = None):
    """Erstellt den LLM-Adapter (aus bot1-Konfiguration)."""
    global _GLOBAL_MODEL_CACHE
    from generator.config import LLM_API_BASE, LLM_MODEL, LLM_PROVIDER, get_api_key_for_provider
    from generator.llm import create_llm_adapter

    provider = LLM_PROVIDER
    # 1) Expliziter Model-Override vom CLI
    if model_override:
        model = model_override
        _GLOBAL_MODEL_CACHE = model
    # 2) Zwischengespeicherter Wert aus vorheriger Auswahl
    elif _GLOBAL_MODEL_CACHE:
        model = _GLOBAL_MODEL_CACHE
    # 3) Aus .env
    else:
        model = LLM_MODEL
    api_key = get_api_key_for_provider(provider)

    if provider == "ollama" and not model:
        from generator.llm.ollama_adapter import get_available_models
        base_url = LLM_API_BASE or "http://localhost:11434"
        models = get_available_models(base_url)
        if not models:
            print("FEHLER: Ollama läuft nicht oder hat keine Modelle.")
            print("Starte Ollama: ollama serve")
            print("Lade ein Modell: ollama pull llama3.1")
            sys.exit(1)

        # Nicht-interaktiv? Nimm erstes Modell
        if not sys.stdin.isatty():
            model = models[0]
            _GLOBAL_MODEL_CACHE = model
            print(f"Ausgewählt: {model}")
        else:
            print("\nVerfügbare Ollama-Modelle:")
            for i, m in enumerate(models, 1):
                print(f"  [{i}] {m}")
            choice = input("Modell wählen (Nummer) > ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(models):
                model = models[int(choice) - 1]
            else:
                model = choice or models[0]
            _GLOBAL_MODEL_CACHE = model
            print(f"Modell {model} wurde für diese Sitzung gespeichert.\n")

    return create_llm_adapter(
        provider, api_key=api_key, model=model, base_url=LLM_API_BASE,
    )


def _create_registry(*, auto_start: bool = False):
    """Erstellt die AI-OS Service-Registry mit allen 36 Repos."""
    from generator.agent.services.factory import build_registry
    return build_registry(
        base_path=str(ALLINALL_ROOT),
        load_legacy=True,
        auto_start_core=auto_start,
    )


def cmd_status(args):
    """Zeigt den Status aller Services und Skills."""
    print("\n" + "=" * 60)
    print("  UNIVERSELLE SCHÖPFER-MATRIX — SYSTEM-STATUS")
    print("=" * 60)

    registry = _create_registry()
    report = registry.status_report()

    print(f"\n📦 Services: {report['services']['total']}")
    print(f"   🟢 Laufend: {report['services']['running']}")
    for svc in report["services"]["details"]:
        icon = "🟢" if svc["status"] == "running" else "⚪"
        print(f"   {icon} {svc['display_name']} [{svc['status']}]")
        if svc["capabilities"]:
            print(f"      Fähigkeiten: {', '.join(svc['capabilities'][:5])}")

    print(f"\n🧠 Skills: {report['skills']['total']}")
    print(f"   Lokal: {report['skills']['by_source']['local']}")
    print(f"   Service: {report['skills']['by_source']['service']}")
    print(f"   Generiert: {report['skills']['by_source']['generated']}")

    if report["skills"]["most_used"]:
        print("\n📊 Meistgenutzt:")
        for s in report["skills"]["most_used"][:5]:
            print(f"   {s['name']}: {s['calls']}x (Ø {s['avg_ms']}ms)")

    print(f"\n📁 Repositories in {ALLINALL_ROOT}:")
    repos = sorted(p.name for p in ALLINALL_ROOT.iterdir() if p.is_dir())
    print(f"   {len(repos)} Projekte: {', '.join(repos[:10])}…")
    print()


def cmd_build(args):
    """Einzel-Build: Generiert einen Bot (wie bisher, mit AI-OS Power)."""
    from generator.cli.interface import CLI
    from generator.modes.classic_mode import ClassicModeRunner
    from generator.modes.blueprint_mode import BlueprintModeRunner
    from generator.agent.orchestrator import Orchestrator

    llm = _create_llm()
    registry = _create_registry() if not args.no_aios else None

    if registry:
        print("🧠 AI-OS Modus aktiviert.")
    else:
        print("⚙️ Standard-Modus (ohne AI-OS Netzwerk).")

    cli = CLI()
    cli.display_header("Bot Generator — AI-OS Edition")

    mode = args.build_mode or "classic"
    if mode == "classic":
        runner = ClassicModeRunner()
    else:
        runner = BlueprintModeRunner()

    runner.run(cli=cli, llm=llm)


def cmd_worldloop(args):
    """Startet die autonome World-Loop."""
    from generator.agent.orchestrator import Orchestrator
    from generator.models.bot_spec import BotSpec

    llm = _create_llm()
    # auto_start=False, um 2-Minuten-Blockaden durch fehlende Docker-Container zu vermeiden!
    registry = _create_registry(auto_start=False)

    orch = Orchestrator(llm, registry=registry)

    goals = []
    if args.goal:
        spec = BotSpec(
            name="task_bot",
            description=args.goal,
            system_prompt="Du bist ein nützlicher Assistent.",
            first_message="Hallo!"
        )
        goals.append({
            "name": args.goal.replace(" ", "_")[:30],
            "description": args.goal,
            "priority": 10,
            "deploy_target": args.deploy or "none",
            "spec": spec
        })

    print("\n🌍 World-Loop wird gestartet…")
    print(f"   Ziele: {len(goals) or 'Wartet auf Messenger-Input'}")
    print(f"   Max. Zyklen: {args.cycles or '∞'}")
    print()

    cycles = orch.run_world_loop(
        goals=goals,
        out_dir=BOT1_ROOT / "output",
        max_cycles=args.cycles or 0,
        progress=lambda msg: print(f"  → {msg}"),
    )

    print(f"\n✅ {len(cycles)} Zyklen abgeschlossen.")
    for i, c in enumerate(cycles, 1):
        goal = c.get("goal", {})
        status = c.get("status", "unknown")
        job_id = c.get("job_id", "")
        
        ok = status in ("completed", "waiting_for_approval")
        icon = "✅" if status == "completed" else "⏸️" if status == "waiting_for_approval" else "❌"
        
        print(f"   [{i}] {goal.get('name', '?')} (Job: {job_id}) — Status: {icon} {status.upper()}")


def cmd_heal(args):
    """Self-Healing: Scannt den eigenen Code und repariert Probleme."""
    from generator.agent.self_healing import SelfHealer

    registry = _create_registry()
    healer = SelfHealer(registry)

    print("\n🏥 Self-Healing Scan wird gestartet…")
    result = healer.run_scan(auto_fix=args.fix)

    print(f"\n{result.get('summary', 'Kein Ergebnis.')}")
    for issue in result.get("issues", [])[:15]:
        icon = "🔴" if issue.get("severity") in ("critical", "high") else "🟡"
        print(f"   {icon} [{issue.get('severity')}] {issue.get('file')}:{issue.get('line')} "
              f"— {issue.get('message', '')[:80]}")

    if result.get("fixed"):
        print(f"\n🔧 {len(result['fixed'])} Issues repariert.")

def cmd_serve(args):
    """Server-Modus: Webhook-Listener + OmegaAgent Dauerbetrieb.

    Eingehende Messenger-Nachrichten (WhatsApp/Discord/Telegram über LangBot/CowAgent)
    landen über den Webhook-Port in der Queue und werden vom OmegaAgent verarbeitet.
    """
    from generator.agent.omega_agent import OmegaAgent
    from generator.agent.services.webhook_listener import start_server

    port = args.port or 9999
    print("\n" + "=" * 60)
    print("  UNIVERSELLE SCHÖPFER-MATRIX — SERVER-MODUS (OMEGA)")
    print("=" * 60)
    print(f"  Webhook-Listener:  http://0.0.0.0:{port}")
    print(f"    POST /webhook/message   (allgemein)")
    print(f"    POST /webhook/langbot   (LangBot-Format)")
    print(f"    POST /webhook/cowagent  (CowAgent/WeCom)")
    print("  OmegaAgent:        Dauerbetrieb — pollt Queue + Messenger")
    print("  (Strg+C zum Beenden)")
    print("=" * 60 + "\n")

    # 1) Webhook-Listener im Hintergrund-Thread starten
    thread = start_server(host="0.0.0.0", port=port, blocking=False)
    if thread is None:
        print("⚠️  Webhook-Listener nicht gestartet (fastapi/uvicorn fehlt?).")
        print("    Installiere: pip install fastapi uvicorn pydantic")
        print("    OmegaAgent läuft trotzdem (ohne Messenger-Eingang).\n")
    else:
        print(f"✅ Webhook-Listener läuft auf Port {port}.\n")

    # 2) OmegaAgent Dauerbetrieb — pollt Queue + Messenger
    llm = _create_llm()
    registry = _create_registry(auto_start=False)
    _ensure_openclaw_bridge()
    omega = OmegaAgent(llm, registry=registry, out_dir=BOT1_ROOT / "output")

    try:
        omega.run_continuous(
            poll_interval=5.0,
            max_cycles=args.cycles or 0,
            progress=lambda m: print(f"  {m}"),
        )
    except KeyboardInterrupt:
        print("\n🛑 Server-Modus beendet.")


def cmd_omega(args):
    """OmegaAgent: Der Mega-Agent. Zerlegt komplexe Ziele und delegiert an 6 Sub-Agenten.

    python start.py omega --goal "Recherchiere über CRISPR"
    python start.py omega --goal "..." --model qwen2.5:14b
    python start.py omega                         # interaktiver Modus
    python start.py omega --daemon                # Dauerbetrieb (pollt Messenger)
    """
    from generator.agent.omega_agent import OmegaAgent

    llm = _create_llm(model_override=getattr(args, "model", None) or None)
    registry = _create_registry(auto_start=not args.no_auto)

    # OpenClaw Bridge starten (das Hirn)
    if not args.no_auto:
        _ensure_openclaw_bridge()

    out_dir = BOT1_ROOT / "output"
    omega = OmegaAgent(llm, registry=registry, out_dir=out_dir)

    # -- Daemon-Modus: kontinuierlicher Betrieb, pollt Messenger/Webhooks
    if args.daemon:
        return _run_omega_daemon(omega, args)

    # -- Einmal-Ausführung via --goal
    if args.goal:
        result = omega.execute(args.goal, progress=lambda m: print(f"  {m}"))
        print(f"\n{'='*60}")
        print(f"🌌 OMEGA RESULTAT")
        print(f"{'='*60}")
        print(f"\n{result['summary']}")
        print(f"\n{'─'*60}")
        ok_count = sum(1 for t in result["tasks"] if t["ok"])
        print(f"Sub-Tasks: {ok_count}/{len(result['tasks'])} erfolgreich ({result['elapsed_s']:.1f}s)")
        for t in result["tasks"]:
            icon = "✅" if t["ok"] else "❌"
            print(f"  {icon} [{t['agent']}] {t['summary'][:100]}")
        print()
        return

    # -- Interaktiver Modus: Eingabe von stdin
    print("\n" + "=" * 60)
    print("  OMEGA MEGA-AGENT — INTERAKTIV")
    print("  Beschreibe dein Ziel. Der Agent zerlegt und delegiert.")
    print("  (Tippe 'exit' zum Beenden, 'status' für System-Status)")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n🎯 Ziel > ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("  OmegaAgent beendet.")
                break
            if not user_input:
                continue
            if user_input.lower() in ("status", "system"):
                cmd_status(args)
                continue

            result = omega.execute(user_input, progress=lambda m: print(f"  {m}"))
            print(f"\n🤖 {result['summary']}")
            ok_count = sum(1 for t in result["tasks"] if t["ok"])
            if result["tasks"]:
                print(f"   ({ok_count}/{len(result['tasks'])} Tasks, {result['elapsed_s']:.1f}s)")

        except KeyboardInterrupt:
            print("\n  Beendet.")
            break
        except Exception as e:
            print(f"❌ Fehler: {e}")


def _run_omega_daemon(omega, args):
    """OmegaAgent Dauerbetrieb: Endlosschleife mit Messenger/Webhook-Polling."""
    print("\n" + "=" * 60)
    print("  OMEGA MEGA-AGENT — DAUERBETRIEB")
    print("  Der Agent läuft im Hintergrund und wartet auf Ziele.")
    print("  Eingänge: Messenger (LangBot/CowAgent), Webhook (Port 9999)")
    print("  (Strg+C zum Beenden)")
    print("=" * 60)

    # Starte Webhook-Listener im Hintergrund
    try:
        from generator.agent.services.webhook_listener import start_server
        start_server(host="0.0.0.0", port=9999, blocking=False)
        print("✅ Webhook-Listener läuft auf Port 9999.\n")
    except Exception:
        print("⚠️  Webhook-Listener nicht gestartet (fastapi/uvicorn fehlt?).\n")

    try:
        omega.run_continuous(
            poll_interval=5.0,
            max_cycles=args.cycles or 0,
            progress=lambda m: print(f"  {m}"),
        )
    except KeyboardInterrupt:
        print("\n🛑 OmegaAgent Dauerbetrieb beendet.")


def cmd_grill(args):
    """/grill-me: das System interviewt den Nutzer bei unklaren Architektur-Entscheidungen.

    Statt sofort blind zu programmieren, stellt der Architekt gezielte Rückfragen,
    bis das Ziel präzise genug für eine saubere Umsetzung ist.
    """
    from generator.llm.base import LLMMessage

    llm = _create_llm()
    topic = (getattr(args, "topic", "") or "").strip()
    if not topic:
        topic = input("\nWas möchtest du bauen? > ").strip()
    if not topic:
        print("Kein Thema angegeben.")
        return

    print("\n" + "=" * 60)
    print("  GRILL-ME — Architektur-Interview")
    print("  Ich stelle dir Rückfragen, bis das Ziel klar ist.")
    print("  (Tippe 'fertig', wenn du genug beantwortet hast)")
    print("=" * 60)

    transcript: list[str] = [f"Ziel des Nutzers: {topic}"]
    system = (
        "Du bist ein erfahrener Software-Architekt. Deine Aufgabe ist es, durch GEZIELTE "
        "Rückfragen Unklarheiten in einem Projektziel aufzudecken, BEVOR programmiert wird. "
        "Stelle IMMER nur GENAU EINE konkrete, kurze Frage pro Runde — zu Scope, Zielgruppe, "
        "Datenquellen, Tech-Stack, Deployment oder Erfolgskriterien. Wenn das Ziel präzise "
        "genug ist, antworte ausschließlich mit 'BEREIT: <eine prägnante Zusammenfassung der "
        "finalen Spezifikation>'."
    )

    for round_no in range(1, 9):
        prompt = (
            "Bisheriger Interview-Verlauf:\n" + "\n".join(transcript) +
            "\n\nStelle die nächste einzelne Rückfrage ODER gib 'BEREIT: …' aus, "
            "wenn genug Klarheit besteht."
        )
        try:
            reply = llm.chat(messages=[LLMMessage(role="user", content=prompt)],
                             system=system, temperature=0.3).strip()
        except Exception as exc:  # noqa: BLE001
            print(f"❌ LLM-Fehler: {exc}")
            return

        if reply.upper().startswith("BEREIT"):
            spec = reply.split(":", 1)[1].strip() if ":" in reply else reply
            print("\n✅ Architektur geklärt:\n")
            print(spec)
            print("\n→ Starte den Bau mit:")
            print(f'   python start.py worldloop --goal "{spec[:80]}"')
            return

        print(f"\n[{round_no}] 🤖 {reply}")
        ans = input("   Du > ").strip()
        if ans.lower() in ("fertig", "done", "exit", "q"):
            break
        transcript.append(f"Architekt fragt: {reply}")
        transcript.append(f"Nutzer antwortet: {ans}")

    print("\n📋 Interview beendet. Zusammenfassung der Anforderungen:")
    for line in transcript:
        print(f"   {line}")


# ── Intent-Routing ────────────────────────────────────────────────────────────

# Reihenfolge ist wichtig: spezifischere Intents zuerst prüfen.
_KW_STATUS = ("status", "systemstatus", "welche services", "welche repos",
              "repositories", "system-status", "system status", "zeig mir die services")
_KW_HEAL = ("self-heal", "self heal", "selbstheil", "repariere dich", "repariere den code",
            "fehler scannen", "code scannen", "scanne den code", "heal")
_KW_BUILD = ("baue ", "bau mir", "bau mal", "erstelle einen bot", "erstelle eine app",
             "erstelle ein projekt", "erstelle eine website", "erstelle eine anwendung",
             "programmiere ein", "programmiere eine", "programmiere mir", "entwickle ein",
             "entwickle eine", "entwickle mir", "generiere einen bot", "bot bauen",
             "app bauen", "projekt bauen", "schreib mir ein programm", "schreibe ein programm",
             "build a bot", "build an app", "erstelle mir einen", "erstelle mir eine",
             "android-app", "android app", "ios-app", "mobile app", "web-app", "webapp",
             "app für", "app zur", "app die", "anwendung für", "anwendung die",
             "software für", "tool für mich")
_KW_TASK = ("such", "find", "speicher", "speichere", "schreib", "lies", "lese", "datei",
            "download", "herunterlad", "lade ", "abruf", "hole", "hol ", "recherch",
            "analysier", "analyse", "berechne", "rechne", "code aus", "führe", "ausführ",
            "liste", "zeige mir", "zeig mir", "fasse", "zusammenfass", "übersetze",
            "url", "http", "webseite", "website", "screenshot", "klicke", "öffne",
            "wetter", "kurs", "preis", "konvertier", "extrahier", "bild", "generiere ein bild")
_KW_GREET = ("hallo", "hi ", "hey", "guten morgen", "guten tag", "servus", "moin",
             "wer bist du", "was kannst du", "hilfe", "help", "danke", "wie geht")


def _route_intent(user_input: str, llm) -> tuple[str, str]:
    """Bestimmt robust, was der Nutzer will — Heuristik zuerst, LLM nur als Fallback.

    Returns:
        (intent, payload) mit intent ∈ {SCIENCE, TASK, WORLDLOOP, STATUS, HEAL, CHAT}.
        Der Standard ist immer Ausführung (TASK), niemals eine Verweigerung.
    """
    from generator.agent.orchestrator import _is_science_goal

    low = " " + user_input.lower().strip() + " "

    # 1) Wissenschaft hat Vorrang (Protein/Molekül/Gen/…)
    if _is_science_goal(user_input):
        return ("SCIENCE", user_input)

    # 2) System-Kommandos
    if any(k in low for k in _KW_STATUS):
        return ("STATUS", "")
    if any(k in low for k in _KW_HEAL):
        return ("HEAL", "")

    # 3) Ganzes Projekt / Bot bauen → World-Loop
    if any(k in low for k in _KW_BUILD):
        return ("WORLDLOOP", user_input)

    # 4) Konkrete Aktion (suchen/speichern/lesen/abrufen/…) → TaskAgent
    if any(k in low for k in _KW_TASK):
        return ("TASK", user_input)

    # 5) Reine Begrüßung/Smalltalk → direkte Antwort
    if any(k in low for k in _KW_GREET) and len(user_input.split()) <= 6:
        return ("CHAT", _chat_reply(user_input, llm))

    # 6) Unklar → ein einziger, verweigerungs-sicherer LLM-Klassifizierer.
    #    Bei jeglicher Unsicherheit: ausführen (TASK), nicht verweigern.
    decision = _llm_classify(user_input, llm)
    if decision == "CHAT":
        return ("CHAT", _chat_reply(user_input, llm))
    if decision == "WORLDLOOP":
        return ("WORLDLOOP", user_input)
    return ("TASK", user_input)


def _llm_classify(user_input: str, llm) -> str:
    """Letzter Ausweg: lässt das LLM NUR ein Label wählen (keine Inhaltsbewertung)."""
    from generator.llm.base import LLMMessage
    system = (
        "Du bist ein reiner Klassifizierer in einem autonomen Agenten-OS. "
        "Du bewertest NIEMALS den Inhalt und verweigerst NIE — du gibst NUR ein Label aus. "
        "Wähle GENAU EIN Wort:\n"
        "TASK = der Nutzer will etwas erledigt haben (suchen, abrufen, Datei, Code, Daten, Analyse).\n"
        "WORLDLOOP = der Nutzer will eine komplette App/einen Bot bauen lassen.\n"
        "CHAT = reine Konversation/Wissensfrage ohne Aktion.\n"
        "Antworte mit genau einem dieser Wörter, sonst nichts."
    )
    try:
        raw = llm.chat(messages=[LLMMessage(role="user", content=user_input)],
                       system=system, temperature=0.0, max_tokens=8).strip().upper()
    except Exception:  # noqa: BLE001
        return "TASK"
    for label in ("WORLDLOOP", "TASK", "CHAT"):
        if label in raw:
            return label
    return "TASK"


def _chat_reply(user_input: str, llm) -> str:
    """Direkte, freundliche Antwort für Smalltalk/Wissensfragen."""
    from generator.llm.base import LLMMessage
    system = (
        "Du bist der Assistent der Universellen Schöpfer-Matrix — ein autonomes KI-OS, das "
        "recherchieren, Dateien schreiben, Code ausführen, Wissenschaft analysieren und ganze "
        "Apps bauen kann. Antworte kurz, freundlich und auf Deutsch."
    )
    try:
        return llm.chat(messages=[LLMMessage(role="user", content=user_input)],
                        system=system, temperature=0.3).strip()
    except Exception as exc:  # noqa: BLE001
        return f"[Antwort nicht möglich: {exc}]"


def cmd_chat_agent(args):
    """Natürlicher Sprach-Agent: Versteht, was der Nutzer will, und führt es aus.

    Komplexe Ziele (SCIENCE, TASK, WORLDLOOP) werden automatisch durch den
    OmegaAgent zerlegt und an Sub-Agenten delegiert.
    """
    from generator.agent.omega_agent import OmegaAgent

    print("\n" + "=" * 60)
    print("  UNIVERSELLE SCHÖPFER-MATRIX — ONLINE")
    print("  Komplexe Ziele werden automatisch zerlegt und delegiert.")
    print("  (Tippe 'exit' zum Beenden, 'status' für System-Status)")
    print("=" * 60)

    llm = _create_llm()
    registry = _create_registry(auto_start=False)
    _ensure_openclaw_bridge()
    omega = OmegaAgent(llm, registry=registry, out_dir=BOT1_ROOT / "output")

    while True:
        try:
            user_input = input("\nDu > ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("  Auf Wiedersehen!")
                break
            if not user_input:
                continue

            intent, payload = _route_intent(user_input, llm)

            if intent in ("SCIENCE", "TASK", "WORLDLOOP"):
                # OmegaAgent zerlegt und delegiert an Sub-Agenten
                print(f"🌌 OmegaAgent übernimmt: {payload[:80]}")
                result = omega.execute(payload, progress=lambda m: print(f"  {m}"))
                print(f"\n🤖 {result['summary']}")
                ok_count = sum(1 for t in result["tasks"] if t["ok"])
                if result["tasks"]:
                    print(f"   ({ok_count}/{len(result['tasks'])} Sub-Tasks, {result['elapsed_s']:.1f}s)")

            elif intent == "STATUS":
                print("🤖 Ich rufe den System-Status ab...")
                cmd_status(args)

            elif intent == "HEAL":
                print("🤖 Ich starte den Self-Healing Scan...")
                args.fix = True
                cmd_heal(args)

            else:  # CHAT
                print(f"🤖 {payload}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Fehler: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Universelle Schöpfer-Matrix — AI-OS Einstiegspunkt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python start.py                     Interaktiver Chat-Agent (mit OmegaAgent)\n"
            "  python start.py omega --goal 'Wetter-Bot mit API'   Mega-Agent Einmal-Ausführung\n"
            "  python start.py omega               Mega-Agent Dauerbetrieb\n"
            "  python start.py build               Bot generieren\n"
            "  python start.py worldloop --goal 'Wetter-Bot bauen'\n"
            "  python start.py serve               Server-Modus (Messenger-Webhooks + World-Loop)\n"
            "  python start.py grill 'Android-App für Protein-Faltung'\n"
            "  python start.py status              System-Status\n"
            "  python start.py heal --fix           Self-Healing mit Auto-Fix\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    # build
    p_build = sub.add_parser("build", help="Bot generieren (Einzel-Build)")
    p_build.add_argument("--no-aios", action="store_true", help="Ohne AI-OS Netzwerk")
    p_build.add_argument("--mode", dest="build_mode", choices=["classic", "blueprint"])
    p_build.set_defaults(func=cmd_build)

    # worldloop
    p_wl = sub.add_parser("worldloop", help="Autonome World-Loop starten")
    p_wl.add_argument("--goal", help="Ziel-Beschreibung")
    p_wl.add_argument("--cycles", type=int, default=0, help="Max. Zyklen (0=unendlich)")
    p_wl.add_argument("--deploy", choices=["local", "firebase", "android", "none"], default="none")
    p_wl.set_defaults(func=cmd_worldloop)

    # status
    p_st = sub.add_parser("status", help="System-Status anzeigen")
    p_st.set_defaults(func=cmd_status)

    # heal
    p_heal = sub.add_parser("heal", help="Self-Healing Scan")
    p_heal.add_argument("--fix", action="store_true", help="Probleme automatisch reparieren")
    p_heal.set_defaults(func=cmd_heal)

    # omega (Mega-Agent: zerlegt Ziele, delegiert an Sub-Agenten)
    p_omega = sub.add_parser("omega", help="OmegaAgent: Mega-Agent mit Task-Zerlegung und Sub-Agenten")
    p_omega.add_argument("--goal", help="Ziel-Beschreibung (leer = interaktive Schleife)")
    p_omega.add_argument("--model", help="Ollama-Modell (z.B. llama3.1:8b, qwen2.5:14b)")
    p_omega.add_argument("--daemon", action="store_true", help="Dauerbetrieb: pollt Messenger/Webhooks")
    p_omega.add_argument("--cycles", type=int, default=0, help="Max. Zyklen im Dauerbetrieb (0=unendlich)")
    p_omega.add_argument("--no-auto", action="store_true", help="Services nicht automatisch starten")
    p_omega.set_defaults(func=cmd_omega)

    # serve (Server-Modus: Webhook-Listener + World-Loop)
    p_serve = sub.add_parser("serve", help="Server-Modus: Messenger-Webhooks empfangen + World-Loop")
    p_serve.add_argument("--port", type=int, default=9999, help="Webhook-Port (Standard: 9999)")
    p_serve.add_argument("--cycles", type=int, default=0, help="Max. Zyklen (0=unendlich)")
    p_serve.set_defaults(func=cmd_serve)

    # grill (Architektur-Interview)
    p_grill = sub.add_parser("grill", help="Architektur-Interview vor dem Bauen (/grill-me)")
    p_grill.add_argument("topic", nargs="?", default="", help="Was gebaut werden soll")
    p_grill.set_defaults(func=cmd_grill)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_chat_agent(args)


if __name__ == "__main__":
    main()
