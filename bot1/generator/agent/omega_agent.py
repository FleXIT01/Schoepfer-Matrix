"""OmegaAgent: Der Mega-Agent — zerlegt komplexe Ziele, delegiert an Sub-Agenten.

Architektur:
  OmegaAgent.execute(goal)
    → _decompose(goal)        LLM zerlegt Ziel in Task-DAG
    → _run_plan(plan)         Führt Tasks aus (parallel wo möglich)
    → _synthesize(goal, res)  LLM fasst Ergebnisse zusammen

Sub-Agenten (alle existieren bereits):
  research   → ResearcherAgent.research()       gpt-researcher, MaxKB, ArXiv, PubMed
  science    → ScienceAgent.analyze()            ChEMBL, AlphaFold, PDB, Ensembl, STRING
  task       → TaskAgent.run()                   21 Tools (web, files, python, browser)
  build      → Orchestrator.build()              Architect→Coder→Fixer→Gates
  review     → FixerAgent + repo-critic          AST-Analyse, Security-Scan
  deploy     → DeployAgent.deploy_local()        Docker-Build + Container-Start
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..llm.base import LLMMessage
from ..models.bot_spec import BotSpec

logger = logging.getLogger(__name__)

# ──────────────────────────────── Datentypen ────────────────────────────────

@dataclass
class SubTask:
    id: str
    agent: str              # "research" | "science" | "task" | "build" | "review" | "deploy"
    goal: str               # Konkrete Aufgabenbeschreibung
    depends_on: list[str]   # IDs der Vorgänger-Tasks

@dataclass
class TaskResult:
    task_id: str
    agent: str
    goal: str
    ok: bool
    summary: str
    error: str = ""

Progress = Callable[[str], None]

# ─────────────────────────────── Decompose-Prompt ───────────────────────────

_DECOMPOSE_SYSTEM = (
    "Du bist ein Task-Decomposer in einem autonomen KI-Betriebssystem. "
    "Deine Aufgabe: Entscheide OB und WIE ein Benutzer-Ziel zerlegt werden muss.\n\n"

    "Verfügbare Sub-Agenten:\n\n"

    "- research: Recherchiert APIs, Paper, Dokumentation, Web-Inhalte. "
    "Nutzt DuckDuckGo, ArXiv, PubMed, OpenAlex. "
    "KEIN science-Agent — nur wenn es um Software/Tech/Wissen geht.\n"

    "- science: NUR für Biochemie/Medizin/Genetik. "
    "Nutzt ChEMBL, AlphaFold, Ensembl, STRING, PDB, Reactome, openFDA. "
    "NICHT für Physik, Astronomie, Mathematik, Informatik.\n"

    "- task: Konkrete Aktionen: Dateien, Python, Web, Browser, Bilder. "
    "21 Built-in-Tools. Für ALLES was kein reines Wissen ist. "
    "NICHT für komplette Programme — dafür gibt es build.\n"

    "- build: Komplette Software-Projekte (Bot/App/Website). "
    "Plant Tools, schreibt Code, testet automatisch. "
    "IMMER wenn der Nutzer Code/Programm/Bot ERSTELLEN will.\n"

    "- review: Code-Review. NUR nach einem build.\n"

    "- deploy: Docker, Firebase, Android. NUR nach einem build+review.\n\n"

    "KRITISCHE REGELN:\n"
    "1. Für reine Wissensfragen (warum, was ist, erkläre, wie funktioniert): "
    "MAXIMAL 1 Task vom Typ 'research'. Kein science, kein task, kein build.\n"
    "2. Science NUR bei Biochemie/Medizin/Genetik — NICHT bei Physik/Astronomie.\n"
    "3. Build/Review/Deploy NUR wenn der Nutzer etwas BAUEN will.\n"
    "4. Maximal 2 Tasks außer bei expliziten Build-Aufträgen.\n"
    "5. Wenn du dir unsicher bist: Nimm 'task' (der Agent hat 21 Tools und kann alles).\n\n"

    "Antworte AUSSCHLIESSLICH mit diesem JSON-Format:\n"
    '{"tasks": ['
    '  {"id": "1", "agent": "research", "goal": "Recherchiere...", "depends_on": []}'
    ']}\n'
    "Kein Text vor oder nach dem JSON."
)

# ─────────────────────────────── Synthese-Prompt ────────────────────────────

_SYNTHESIZE_SYSTEM = (
    "Du bist der Ergebnis-Synthetisierer der Universellen Schöpfer-Matrix. "
    "Fasse die Ergebnisse aller Sub-Agenten zu einer präzisen, "
    "deutschsprachigen Zusammenfassung zusammen.\n\n"
    "Struktur:\n"
    "1. Was wurde erreicht? (1-2 Sätze)\n"
    "2. Wichtigste Erkenntnisse (Bullet-Points)\n"
    "3. Nächste Schritte / Empfehlung\n\n"
    "Maximal 300 Wörter. Kein Markdown außer Bullet-Points."
)

# ─────────────────────────────── OmegaAgent ────────────────────────────────

class OmegaAgent:
    """Der Mega-Agent. Nimmt ein komplexes Ziel, zerlegt es in Sub-Tasks,
    delegiert an die 6 spezialisierten Sub-Agenten und synthetisiert Ergebnisse."""

    def __init__(self, llm, *, registry=None, out_dir: Path | None = None) -> None:
        self._llm = llm
        self._registry = registry
        self._out_dir = out_dir or Path("output")

        # Sub-Agenten verzögert erstellen (vermeidet Import-Zyklen)
        self._researcher = None
        self._scientist = None
        self._task_agent = None
        self._orchestrator = None
        self._deployer = None

    # ── Properties (lazy init) ───────────────────────────────────────────

    @property
    def researcher(self):
        if self._researcher is None:
            from .agents.researcher import ResearcherAgent
            self._researcher = ResearcherAgent(self._llm, registry=self._registry)
        return self._researcher

    @property
    def scientist(self):
        if self._scientist is None:
            from .agents.science_agent import ScienceAgent
            self._scientist = ScienceAgent(self._llm, registry=self._registry)
        return self._scientist

    @property
    def task_agent(self):
        if self._task_agent is None:
            from .task_agent import TaskAgent
            self._task_agent = TaskAgent(self._llm, max_steps=14)
        return self._task_agent

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from .orchestrator import Orchestrator
            self._orchestrator = Orchestrator(self._llm, registry=self._registry)
        return self._orchestrator

    @property
    def deployer(self):
        if self._deployer is None:
            from .agents.deployer import DeployAgent
            self._deployer = DeployAgent(self._llm, registry=self._registry)
        return self._deployer

    # ── Hauptmethode ─────────────────────────────────────────────────────

    def execute(self, goal: str, progress: Progress | None = None) -> dict[str, Any]:
        """Führt ein komplexes Ziel aus. Gibt strukturierte Ergebnisse zurück."""
        say = progress or (lambda _m: None)
        t0 = time.time()
        say(f"🌌 OmegaAgent: Analysiere Ziel: {goal[:100]}")

        # 0) Fast-Path: einfache Wissensfrage → direkt beantworten (1 LLM-Call)
        if self._is_simple_knowledge_question(goal):
            say("⚡ Fast-Path: Direkte Antwort (keine Zerlegung nötig)")
            summary = self._direct_answer(goal)
            elapsed = time.time() - t0
            say(f"✅ OmegaAgent: {elapsed:.1f}s")
            return {
                "goal": goal, "summary": summary, "tasks": [],
                "ok": True, "elapsed_s": elapsed, "fast_path": True,
            }

        # 0.5) Build-Heuristic: explizite "baue/erstell/programmier"-Aufrufe
        if self._is_build_request(goal):
            say("🏗️  Build-Heuristic: Forciere research→build→review-Pipeline")
            plan = [
                SubTask(id="1", agent="research", goal=f"Recherchiere Anforderungen für: {goal[:100]}", depends_on=[]),
                SubTask(id="2", agent="build", goal=goal, depends_on=["1"]),
                SubTask(id="3", agent="review", goal=f"Überprüfe den generierten Code für: {goal[:100]}", depends_on=["2"]),
            ]
        else:
            # 1) Zerlegen via LLM (mit OpenClaw-Fallback)
            plan = self._decompose(goal)
        if not plan:
            say("⚠️  Keine Zerlegung möglich – führe direkt via TaskAgent aus.")
            summary = self.task_agent.run(goal, progress=say)
            return {"goal": goal, "summary": summary, "tasks": [], "ok": True}

        say(f"📋 {len(plan)} Sub-Tasks geplant:")
        for t in plan:
            deps = f" (wartet auf: {', '.join(t.depends_on)})" if t.depends_on else ""
            say(f"   [{t.id}] {t.agent}: {t.goal[:80]}{deps}")

        # 2) Ausführen
        results = self._run_plan(plan, say)

        # 3) Synthetisieren
        say("🧠 Synthetisiere Ergebnisse…")
        summary = self._synthesize(goal, results)

        elapsed = time.time() - t0
        all_ok = all(r.ok for r in results.values())
        say(f"{'✅' if all_ok else '⚠️'} OmegaAgent: {len(results)}/{len(plan)} Tasks in {elapsed:.1f}s")

        return {
            "goal": goal,
            "summary": summary,
            "tasks": [
                {"id": r.task_id, "agent": r.agent, "ok": r.ok, "summary": r.summary[:200]}
                for r in results.values()
            ],
            "ok": all_ok,
            "elapsed_s": elapsed,
        }

    # ── Fast-Path: Einfache Fragen direkt beantworten ──────────────────

    @staticmethod
    def _is_simple_knowledge_question(goal: str) -> bool:
        """Erkennt einfache Wissensfragen, die keine Zerlegung brauchen."""
        low = goal.lower().strip()
        if len(low) > 120:
            return False
        build_kw = ("baue", "erstell", "programmier", "entwickle", "generier",
                    "deploy", "docker", "firebase", "app", "website", "bot",
                    "api", "datenbank", "server", "frontend", "backend")
        for kw in build_kw:
            if kw in low:
                return False
        question_kw = ("warum", "wieso", "weshalb", "was ist", "wer ist",
                       "wie funktioniert", "erkläre", "erkläre mir",
                       "definition", "definiere", "beschreibe", "nenne",
                       "was bedeutet", "wofür steht", "unterschied",
                       "zusammenfassung", "faszi", "kurz erkl",
                       "in 2 sätzen", "in zwei sätzen", "in 3 sätzen")
        for kw in question_kw:
            if kw in low:
                return True
        return False

    def _direct_answer(self, goal: str) -> str:
        """Beantwortet eine einfache Wissensfrage mit EINEM LLM-Call."""
        system = (
            "Du bist ein präziser Assistent. Beantworte die Frage kurz, "
            "korrekt und auf Deutsch. Maximal 150 Wörter."
        )
        try:
            return self._llm.chat(
                messages=[LLMMessage(role="user", content=goal)],
                system=system,
                temperature=0.1,
                max_tokens=300,
            ).strip()
        except Exception as exc:
            return f"[LLM-Fehler: {exc}]"

    @staticmethod
    def _is_build_request(goal: str) -> bool:
        """Erkennt explizite Build-Aufträge (Code/App/Bot erstellen)."""
        low = f" {goal.lower()} "
        # Build-Verben
        build_kw = (" baue ", " erstell ", " programmier ", " entwickle ",
                    " generier ", " schreib ein ", " schreibe ein ",
                    " coden ", " implementier ")
        has_build = any(kw in low for kw in build_kw)
        # Ziel-Wörter (ganze Wörter, keine Substrings wie "Programmiersprache")
        target_kw = (" app ", " website ", " webseite ", " bot ", " programm ",
                     " tool ", " anwendung ", " spiel ", " rechner ",
                     " taschenrechner", " api ", " server ")
        has_target = any(kw in low for kw in target_kw)
        return has_build and has_target

    def run_continuous(self, *, poll_interval: float = 5.0,
                       max_cycles: int = 0,
                       progress: Progress | None = None) -> None:
        """Endlos-Loop: pollt eingehende Nachrichten und verarbeitet sie.

        Liest aus:
          - webhook_listener (HTTP POSTs von Messenger)
          - LangBot/CowAgent über die Service-Registry

        Args:
            poll_interval: Sekunden zwischen Polls wenn keine Nachrichten da sind.
            max_cycles: 0 = endlos, >0 = nach N Zyklen stoppen.
            progress: Callback für Statusmeldungen.
        """
        say = progress or (lambda _m: None)
        cycles = 0

        say("🌍 OmegaAgent Dauerbetrieb gestartet.")
        say(f"   Poll-Intervall: {poll_interval}s, Max Zyklen: {max_cycles or '∞'}")
        say("   Warte auf Ziele (Messenger, Webhook)…")

        while True:
            try:
                # 1) Eingehende Nachrichten prüfen
                goals = self._check_incoming_messages()
                if goals:
                    say(f"📨 {len(goals)} neue(s) Ziel(e) empfangen.")

                # 2) Jedes Ziel verarbeiten
                for goal in goals:
                    cycles += 1
                    say(f"\n⚡ Zyklus {cycles}" + (f"/{max_cycles}" if max_cycles else ""))
                    result = self.execute(goal, progress=say)
                    say(f"🤖 {result['summary'][:150]}")
                    ok_count = sum(1 for t in result["tasks"] if t["ok"])
                    say(f"   ({ok_count}/{len(result['tasks'])} Tasks, {result['elapsed_s']:.1f}s)")

                    # 3) Ergebnisse in MaxKB speichern
                    self._ingest_learnings(goal, result, say)

                    if max_cycles and cycles >= max_cycles:
                        say(f"\n✅ {max_cycles} Zyklen erreicht. Dauerbetrieb beendet.")
                        return

                # 4) Kurz warten wenn keine neuen Ziele
                if not goals:
                    time.sleep(poll_interval)

            except KeyboardInterrupt:
                say("\n🛑 Dauerbetrieb unterbrochen.")
                break
            except Exception as exc:
                logger.exception("Fehler im Dauerbetrieb: %s", exc)
                say(f"⚠️ Fehler (nicht kritisch): {exc}")
                time.sleep(poll_interval)

    def _check_incoming_messages(self) -> list[str]:
        """Prüft alle Quellen auf neue Ziele/Nachrichten."""
        goals: list[str] = []

        # 1) Webhook-Listener (Port 9999)
        try:
            from .services.webhook_listener import get_pending_messages
            messages = get_pending_messages(max_count=5)
            for msg in messages:
                text = str(msg.get("text", "")).strip()
                if text:
                    platform = msg.get("platform", "unknown")
                    sender = msg.get("sender", "anonymous")
                    goals.append(f"[{platform}@{sender}]: {text}")
        except Exception:
            pass  # Webhook-Listener nicht geladen — ignorieren

        # 2) LangBot Messenger Service (falls registriert)
        if self._registry:
            messenger = self._registry.get_service("langbot")
            if messenger and messenger.health_check():
                try:
                    result = messenger.execute("messages/pending", {})
                    if result.ok and isinstance(result.data, list):
                        for msg in result.data:
                            text = str(msg.get("text", "")).strip()
                            if text:
                                goals.append(f"[langbot]: {text}")
                except Exception:
                    pass

        return goals

    def _ingest_learnings(self, goal: str, result: dict, say: Progress) -> None:
        """Speichert Zyklus-Ergebnisse in MaxKB (wenn verfügbar)."""
        if not self._registry:
            return
        knowledge = self._registry.get_service("maxkb")
        if not knowledge or not knowledge.health_check():
            return
        try:
            summary = result.get("summary", "")[:1000]
            if summary:
                knowledge.execute("ingest", {
                    "title": f"OmegaAgent: {goal[:80]}",
                    "content": f"Ziel: {goal}\n\nErgebnis:\n{summary}",
                    "source": "omega_agent",
                    "tags": ["omega_loop", "autonomous"],
                })
                say("   💾 Ergebnis in MaxKB gespeichert.")
        except Exception as exc:
            logger.debug("MaxKB-Ingest fehlgeschlagen (nicht kritisch): %s", exc)

    # ── 1) Decompose ─────────────────────────────────────────────────────

    def _decompose(self, goal: str) -> list[SubTask]:
        """LLM zerlegt das Ziel in einen Task-DAG.

        Pipeline:
        1. OpenClaw (Hirn) klassifiziert den Intent — wenn verfügbar
        2. LLM zerlegt basierend auf der Klassifikation
        """

        # 1) OpenClaw Intent-Klassifikation (das Hirn)
        openclaw_hint = self._classify_via_openclaw(goal)

        # 2) LLM-Decompose mit OpenClaw-Hint
        user = f"Ziel des Nutzers:\n{goal}\n"
        if openclaw_hint:
            user += f"\nOpenClaw Intent-Analyse:\n{openclaw_hint}\n\n"
        user += "Zerlege dieses Ziel in Sub-Aufgaben."

        try:
            raw = self._llm.chat(
                messages=[LLMMessage(role="user", content=user)],
                system=_DECOMPOSE_SYSTEM,
                temperature=0.1,
                max_tokens=1024,
            ).strip()
        except Exception as exc:
            logger.warning("Decompose LLM-Fehler: %s", exc)
            return []

        # JSON extrahieren (tolerant gegen Markdown-Fences)
        data = self._parse_json(raw)
        if not data or "tasks" not in data:
            logger.warning("Decompose: Kein JSON gefunden in: %s", raw[:200])
            return []

        tasks = []
        seen: set[str] = set()
        for item in data.get("tasks", []):
            tid = str(item.get("id", ""))
            agent = str(item.get("agent", "")).lower()
            task_goal = str(item.get("goal", ""))
            deps = [str(d) for d in item.get("depends_on", [])]

            if not tid or not agent or not task_goal:
                continue
            if tid in seen:
                continue
            if agent not in ("research", "science", "task", "build", "review", "deploy"):
                continue
            valid_deps = [d for d in deps if d in seen]
            seen.add(tid)
            tasks.append(SubTask(id=tid, agent=agent, goal=task_goal, depends_on=valid_deps))

        return tasks

    def _classify_via_openclaw(self, goal: str) -> str:
        """Fragt OpenClaw nach Intent-Klassifikation. Gibt Hint oder '' zurück."""
        if not self._registry:
            return ""
        openclaw = self._registry.get_service("openclaw")
        if not openclaw or not openclaw.health_check():
            return ""

        try:
            result = openclaw.route_intent(goal)
            if result.ok and isinstance(result.data, dict):
                intent = result.data.get("intent", "")
                complexity = result.data.get("complexity", 0)
                agents = result.data.get("suggested_agents", [])
                hint = result.data.get("plan_hint", "")
                if intent:
                    return (
                        f"Intent: {intent}\n"
                        f"Komplexität: {complexity}/5\n"
                        f"Empfohlene Agenten: {', '.join(agents) if agents else 'automatisch'}\n"
                        f"Strategie: {hint}"
                    )
        except Exception as exc:
            logger.debug("OpenClaw-Klassifikation fehlgeschlagen: %s", exc)

        return ""

    # ── 2) Execute Plan ──────────────────────────────────────────────────

    def _run_plan(self, plan: list[SubTask], say: Progress) -> dict[str, TaskResult]:
        """Führt alle Tasks aus, respektiert Abhängigkeiten. Unabhängige Tasks parallel."""
        results: dict[str, TaskResult] = {}
        task_map = {t.id: t for t in plan}
        completed: set[str] = set()
        failed: set[str] = set()

        while len(completed) + len(failed) < len(plan):
            # Finde Tasks deren Abhängigkeiten alle erfüllt sind
            ready = []
            for t in plan:
                if t.id in completed or t.id in failed:
                    continue
                if all(d in completed for d in t.depends_on):
                    ready.append(t)

            if not ready:
                # Deadlock: übrige Tasks haben unerfüllbare Abhängigkeiten
                for t in plan:
                    if t.id not in completed and t.id not in failed:
                        results[t.id] = TaskResult(
                            task_id=t.id, agent=t.agent, goal=t.goal,
                            ok=False, summary="", error="Abhängigkeit nicht erfüllt (Deadlock)"
                        )
                        failed.add(t.id)
                break

            # Parallele Ausführung aller bereiten Tasks
            with ThreadPoolExecutor(max_workers=min(len(ready), 4)) as executor:
                futures = {executor.submit(self._run_task, t, say): t for t in ready}
                for future in as_completed(futures):
                    t = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = TaskResult(
                            task_id=t.id, agent=t.agent, goal=t.goal,
                            ok=False, summary="", error=str(exc)
                        )
                    results[t.id] = result
                    if result.ok:
                        completed.add(t.id)
                        say(f"   ✅ [{t.id}] {t.agent}: {result.summary[:80]}")
                    else:
                        failed.add(t.id)
                        say(f"   ❌ [{t.id}] {t.agent}: {result.error[:80]}")

        return results

    # ── 3) Synthesize ────────────────────────────────────────────────────

    def _synthesize(self, goal: str, results: dict[str, TaskResult]) -> str:
        """LLM fasst alle Sub-Ergebnisse zu einer Gesamtzusammenfassung zusammen."""
        parts = []
        for tid, r in sorted(results.items()):
            status = "✅" if r.ok else "❌"
            parts.append(f"[{tid}] {status} {r.agent}: {r.goal}\n  → {r.summary or r.error}")

        if not parts:
            return "Keine Ergebnisse."

        user = (
            f"Ursprüngliches Ziel: {goal}\n\n"
            f"Ergebnisse der Sub-Agenten:\n\n" + "\n\n".join(parts)
        )
        try:
            return self._llm.chat(
                messages=[LLMMessage(role="user", content=user)],
                system=_SYNTHESIZE_SYSTEM,
                temperature=0.3,
                max_tokens=800,
            ).strip()
        except Exception:
            # Fallback: erste 3 Ergebnisse konkatenieren
            return "\n".join(
                f"{r.agent}: {r.summary[:200]}" for r in list(results.values())[:3]
            )

    # ── Task-Dispatch ────────────────────────────────────────────────────

    def _run_task(self, task: SubTask, say: Progress) -> TaskResult:
        """Führt einen einzelnen Sub-Task aus, indem der passende Agent aufgerufen wird."""
        try:
            if task.agent == "research":
                return self._run_research(task, say)
            elif task.agent == "science":
                return self._run_science(task, say)
            elif task.agent == "task":
                return self._run_general_task(task, say)
            elif task.agent == "build":
                return self._run_build(task, say)
            elif task.agent == "review":
                return self._run_review(task, say)
            elif task.agent == "deploy":
                return self._run_deploy(task, say)
            else:
                return TaskResult(task_id=task.id, agent=task.agent, goal=task.goal,
                                  ok=False, error=f"Unbekannter Agent-Typ: {task.agent}")
        except Exception as exc:
            logger.exception("Task [%s] fehlgeschlagen", task.id)
            return TaskResult(task_id=task.id, agent=task.agent, goal=task.goal,
                              ok=False, error=str(exc))

    def _run_research(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🔍 [{task.id}] Recherchiere: {task.goal[:60]}")
        result = self.researcher.research(task.goal, depth="standard")
        summary = str(result.get("summary", ""))[:500]
        return TaskResult(task_id=task.id, agent="research", goal=task.goal,
                          ok=bool(summary), summary=summary or "Keine Ergebnisse")

    def _run_science(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🧬 [{task.id}] Wissenschafts-Analyse: {task.goal[:60]}")
        result = self.scientist.analyze(task.goal, save_report=True, depth="full")
        report = str(result.get("report", ""))[:800]
        return TaskResult(task_id=task.id, agent="science", goal=task.goal,
                          ok=bool(report), summary=report or "Keine Ergebnisse",
                          error="" if report else "ScienceAgent lieferte kein Ergebnis")

    def _run_general_task(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🔧 [{task.id}] Führe aus: {task.goal[:60]}")
        result = self.task_agent.run(task.goal, progress=lambda m: say(f"      {m}"))
        return TaskResult(task_id=task.id, agent="task", goal=task.goal,
                          ok=not result.startswith("[LLM-Fehler"),
                          summary=result[:500], error=result if result.startswith("[") else "")

    def _run_build(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🏗️  [{task.id}] Baue: {task.goal[:60]}")
        name = re.sub(r"[^a-z0-9_]", "_", task.goal.lower())[:30] or "generated_bot"
        spec = BotSpec(
            name=name,
            description=task.goal,
            system_prompt=f"Du bist ein {name}. Hilf dem Nutzer bei {task.goal[:80]}.",
            first_message="Hallo! Wie kann ich helfen?",
        )
        out = self._out_dir / f"{name}_{_timestamp()}"
        result = self.orchestrator.build(spec, out, progress=lambda m: say(f"      {m}"))
        # Summary aus Steps bauen (BuildResult.summary ist oft leer)
        step_summary = "; ".join(
            f"{s.step}: {'OK' if s.status == 'ok' else s.status}" for s in result.steps[-3:]
        ) if result.steps else ""
        # Final-Run-Output säubern (keine Tracebacks)
        final = result.final_run_output or ""
        if "Traceback" in final:
            final = final.split("Traceback")[0].strip()
        final_text = f" Output: {final[:80]}" if final else ""
        summary = (result.summary or f"Build {'OK' if result.ok else 'fehlgeschlagen'}."
                   f"{final_text} [{step_summary}]")
        return TaskResult(task_id=task.id, agent="build", goal=task.goal,
                          ok=result.ok, summary=summary[:500],
                          error="" if result.ok else summary)

    def _run_review(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🔎 [{task.id}] Code-Review: {task.goal[:60]}")
        # Nutze repo-critic Service falls verfügbar, sonst lokales LLM-Review
        if self._registry:
            reviewer = self._registry.get_service("repo-critic")
            if reviewer:
                try:
                    if reviewer.ensure_running(timeout_seconds=5.0):
                        res = reviewer.execute("review", {"source": task.goal, "language": "python"})
                        if res.ok:
                            issues = res.data.get("issues", []) if isinstance(res.data, dict) else []
                            summary = f"{res.data.get('score', '?')}/100 – {len(issues)} Issues"
                            return TaskResult(task_id=task.id, agent="review", goal=task.goal,
                                              ok=True, summary=summary)
                except Exception as exc:
                    logger.debug("repo-critic nicht verfügbar: %s", exc)

        # Fallback: LLM-basiertes Review
        try:
            from .agents.fixer import FixerAgent
            fixer = FixerAgent(self._llm, registry=self._registry)
            hints = fixer._get_review_hints(task.goal)
            return TaskResult(task_id=task.id, agent="review", goal=task.goal,
                              ok=True, summary=hints[:500] or "Review abgeschlossen")
        except Exception as exc:
            return TaskResult(task_id=task.id, agent="review", goal=task.goal,
                              ok=True, summary=f"LLM-Review: {str(exc)[:200]}")

    def _run_deploy(self, task: SubTask, say: Progress) -> TaskResult:
        say(f"   🚀 [{task.id}] Deploye: {task.goal[:60]}")
        # Versuche lokales Deployment im output-Verzeichnis
        project_dir = str(self._out_dir)
        result = self.deployer.deploy_local(project_dir, port=8080)
        ok = result.get("ok", False) if isinstance(result, dict) else False
        summary = str(result.get("stdout", result.get("instructions", "")))[:500] if isinstance(result, dict) else str(result)[:500]
        return TaskResult(task_id=task.id, agent="deploy", goal=task.goal,
                          ok=ok, summary=summary or "Deployment abgeschlossen")

    # ── JSON-Parser ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Robuster JSON-Parser: toleriert Markdown-Fences und Teil-JSON."""
        # Code-Fences entfernen
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Äußerstes {…} extrahieren
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def _timestamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%dT%H%M%S")
