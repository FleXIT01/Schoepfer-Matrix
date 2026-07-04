"""Orchestrator: der Build-Zeit-Controller (reine Python-Logik, kein eigener LLM-Call).

Treibt Architect → Coder → Gates → Fixer in einer beschränkten Schleife, bis das
generierte Bot-Paket die deterministischen Gates besteht, und führt am Ende einen
echten Lauf gegen das lokale Modell als Abnahme aus.

AI-OS Erweiterung: Wenn eine ServiceRegistry übergeben wird, nutzt der Orchestrator
das gesamte Netzwerk aus 36+ Repositories (OpenClaw, agenticSeek, repo-critic-ai,
MaxKB, ComfyUI, Project Chimera, etc.) anstatt nur lokale LLM-Calls.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..config import (
    AGENT_FINAL_REAL_RUN,
    AGENT_MAX_FIX_ATTEMPTS,
    AGENT_MAX_GLOBAL_ITERS,
    SANDBOX_TIMEOUT,
)
from ..models.bot_spec import BotSpec
from . import package_builder
from .agents import ArchitectAgent, CoderAgent, DeployAgent, FixerAgent, ResearcherAgent
from .agents.science_agent import ScienceAgent
from .agents.architect import fallback_tooltasks
from .agents.coder import sample_from_code
from .build_plan import ToolTask
from .package_builder import ResolvedTool, build_package
from .report import BuildResult, StepLog, render_report
from .tools import library
from .verify import gates, sandbox

if TYPE_CHECKING:
    from .services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]


def _definition_for(name: str, description: str, sample: dict) -> dict:
    props: dict = {}
    required: list[str] = []
    for key, value in (sample or {}).items():
        typ = "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else "string"
        props[key] = {"type": typ, "description": key}
        required.append(key)
    if not props:
        props = {"query": {"type": "string", "description": "Eingabe"}}
        required = ["query"]
    return {
        "name": name,
        "description": description or name,
        "input_schema": {"type": "object", "properties": props, "required": required},
    }


class Orchestrator:
    def __init__(self, llm, *, real_run: bool | None = None,
                 registry: ServiceRegistry | None = None) -> None:
        self._registry = registry
        self.architect = ArchitectAgent(llm, registry=registry)
        self.coder = CoderAgent(llm, registry=registry)
        self.fixer = FixerAgent(llm, registry=registry)
        self.researcher = ResearcherAgent(llm, registry=registry)
        self.scientist = ScienceAgent(llm, registry=registry)
        self.deployer = DeployAgent(llm, registry=registry)
        self.max_fix = AGENT_MAX_FIX_ATTEMPTS
        self.max_global = AGENT_MAX_GLOBAL_ITERS
        self.timeout = SANDBOX_TIMEOUT
        self.real_run_timeout = max(180.0, SANDBOX_TIMEOUT)
        self.final_real_run = AGENT_FINAL_REAL_RUN if real_run is None else real_run

        if registry:
            logger.info(
                "🧠 AI-OS Modus aktiviert: %d Services, %d Skills verfügbar.",
                len(registry.all_services), len(registry.all_skills),
            )
        else:
            logger.info("Standard-Modus (kein AI-OS Netzwerk).")

    # -- public ------------------------------------------------------------

    def build(self, spec: BotSpec, out_dir: Path, progress: Progress | None = None) -> BuildResult:
        say = progress or (lambda _m: None)
        steps: list[StepLog] = []

        # 1) Tool-Plan
        say("Architekt plant Tools…")
        try:
            tasks = self.architect.plan_tools(spec)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArchitectAgent fehlgeschlagen: %s", exc)
            tasks = fallback_tooltasks(spec)
        steps.append(StepLog("architekt:tool-plan", "ok",
                             f"{len(tasks)} Tool(s) geplant: {', '.join(t.name for t in tasks) or '—'}"))

        # 2) Tools auflösen (Bibliothek) bzw. generieren (Coder)
        # Doppelte Namen und doppelt belegte Capabilities vorab bereinigen
        tasks = self._deduplicate_tasks(tasks)
        resolved: list[ResolvedTool] = []
        used_caps: set[str] = set()
        for task in tasks:
            # Wenn Capability schon von einem anderen Tool belegt: generieren statt Bibliothek
            if task.capability and task.capability in used_caps:
                task = task.model_copy(update={"capability": None, "needs_generation": True})
            if task.capability and not task.needs_generation:
                used_caps.add(task.capability)
            rt, log = self._resolve_tool(task, say)
            resolved.append(rt)
            steps.append(log)

        # 3) Generierte Tools einzeln verifizieren + reparieren
        for idx, rt in enumerate(resolved):
            if rt.from_library or rt.is_stub:
                continue
            steps.append(self._verify_and_fix_tool(spec, resolved, idx, say))

        # 4) Projekt-Gates (Import + Smoke) mit globaler Reparatur
        say("Verifiziere Gesamtpaket (Import + Smoke-Test)…")
        self._verify_project(spec, resolved, steps, say)

        # 5) Tool-Schleifen-Gate (falls Tools vorhanden): einmal end-to-end testen
        if resolved:
            self._verify_tool_loop(spec, resolved, steps)

        # 6) Dateien schreiben
        files = build_package(spec, resolved)
        self._write_files(files, out_dir)

        # 7) Finaler echter Lauf gegen das lokale Modell
        final_ok, final_out = self._final_real_run(spec, resolved, say)

        ok = all(s.status in ("ok", "fixed", "skipped") for s in steps)
        result = BuildResult(
            ok=ok,
            files=files,
            steps=steps,
            final_run_output=final_out,
            final_run_ok=final_ok,
        )
        report = render_report(spec, result)
        (out_dir / "BUILD_REPORT.md").write_text(report, encoding="utf-8")
        return result

    # -- deduplication -------------------------------------------------------

    @staticmethod
    def _deduplicate_tasks(tasks: list[ToolTask]) -> list[ToolTask]:
        """Entfernt doppelte Tool-Namen (erste Instanz gewinnt)."""
        seen: set[str] = set()
        out: list[ToolTask] = []
        for t in tasks:
            if t.name in seen:
                continue
            seen.add(t.name)
            out.append(t)
        return out

    # -- tool resolution ---------------------------------------------------

    def _resolve_tool(self, task: ToolTask, say: Progress) -> tuple[ResolvedTool, StepLog]:
        if not task.needs_generation and task.capability:
            entry = library.get(task.capability)
            if entry is not None:
                # Nutze den Namen aus dem Architekten-Plan (task.name), nicht den Bibliotheks-Namen.
                # So kann run_python als "run_python_code" und ähnliches sauber ko-existieren.
                rt = ResolvedTool(
                    name=task.name, func_source=entry.func_source,
                    definition={**entry.definition, "name": task.name},
                    sample_input=entry.sample_input,
                    from_library=True,
                )
                return rt, StepLog(f"tool:{task.name}", "ok", f"aus geprüfter Bibliothek ({task.capability})")

        say(f"Coder generiert Tool '{task.name}'…")
        src = self.coder.generate_tool(task)
        if not src:
            stub = package_builder._stub_tool(task.name, task.description)
            return stub, StepLog(f"tool:{task.name}", "degraded",
                                 "Generierung lieferte keinen Code → Stub", 1)
        # Beispiel-Input aus der TATSÄCHLICHEN Signatur ableiten (nicht vom Architekten raten lassen)
        sample = sample_from_code(src, task.name) or {"query": "test"}
        rt = ResolvedTool(
            name=task.name, func_source=src,
            definition=_definition_for(task.name, task.description, sample),
            sample_input=sample,
            from_library=False,
        )
        return rt, StepLog(f"tool:{task.name}", "ok", "generiert (vor Verifikation)")

    def _gate_tool(self, spec: BotSpec, resolved: list[ResolvedTool], idx: int):
        files = build_package(spec, resolved)
        with sandbox.materialized(files) as d:
            return gates.tool_gate(d, resolved[idx].name, resolved[idx].sample_input, self.timeout)

    def _verify_and_fix_tool(self, spec, resolved, idx, say) -> StepLog:
        name = resolved[idx].name
        res = self._gate_tool(spec, resolved, idx)
        if res.ok:
            return StepLog(f"tool:{name}", "ok", "generiert + getestet")

        for attempt in range(1, self.max_fix + 1):
            say(f"Repariere Tool '{name}' (Versuch {attempt}/{self.max_fix})…")
            fixed = self.fixer.fix(
                resolved[idx].func_source, res.error,
                context=f"Tool '{name}', Beispiel-Input {resolved[idx].sample_input}",
                require_function=name,
            )
            if fixed:
                resolved[idx].func_source = fixed
                new_sample = sample_from_code(fixed, name)
                if new_sample:
                    resolved[idx].sample_input = new_sample
                    resolved[idx].definition = _definition_for(
                        name, resolved[idx].definition.get("description", ""), new_sample)
                res = self._gate_tool(spec, resolved, idx)
                if res.ok:
                    return StepLog(f"tool:{name}", "fixed",
                                   f"nach {attempt} Reparatur(en) grün", attempt)

        last_err = (res.error or "").strip().replace("\n", " ")[:200]
        resolved[idx] = package_builder._stub_tool(
            name, resolved[idx].definition.get("description", ""))
        return StepLog(f"tool:{name}", "degraded",
                       f"nicht reparierbar → Stub. Letzter Fehler: {last_err}", self.max_fix)

    # -- project gates -----------------------------------------------------

    def _project_gates_pass(self, spec, resolved) -> tuple[bool, str]:
        files = build_package(spec, resolved)
        with sandbox.materialized(files) as d:
            imp = gates.import_gate(d, "bot.runner", self.timeout)
            if not imp.ok:
                return False, imp.error
            sm = gates.smoke_gate(d, self.timeout)
            if not sm.ok:
                return False, sm.error
        return True, ""

    def _verify_project(self, spec, resolved, steps, say) -> None:
        ok, err = self._project_gates_pass(spec, resolved)
        if ok:
            steps.append(StepLog("projekt:import+smoke", "ok",
                                 "Paket importiert, respond() läuft"))
            return

        gen_idx = [i for i, t in enumerate(resolved) if not t.from_library and not t.is_stub]
        for it in range(1, self.max_global + 1):
            if not gen_idx:
                break
            i = gen_idx.pop()
            say(f"Projekt-Reparatur {it}: setze Tool '{resolved[i].name}' auf Stub…")
            resolved[i] = package_builder._stub_tool(
                resolved[i].name, resolved[i].definition.get("description", ""))
            ok, err = self._project_gates_pass(spec, resolved)
            if ok:
                steps.append(StepLog("projekt:import+smoke", "fixed",
                                     f"nach {it} Reparatur(en) grün", it))
                return

        # letzte Rettung: alle generierten Tools auf Stub
        for i, t in enumerate(resolved):
            if not t.from_library and not t.is_stub:
                resolved[i] = package_builder._stub_tool(
                    t.name, t.definition.get("description", ""))
        ok, err = self._project_gates_pass(spec, resolved)
        steps.append(StepLog(
            "projekt:import+smoke",
            "fixed" if ok else "failed",
            "alle generierten Tools auf Stub gesetzt" if ok else err,
            self.max_global,
        ))

    def _verify_tool_loop(self, spec, resolved, steps) -> None:
        if not resolved:
            return
        target = resolved[0]
        files = build_package(spec, resolved)
        with sandbox.materialized(files) as d:
            res = gates.tool_loop_gate(d, target.name, target.sample_input, self.timeout)
        steps.append(StepLog(
            "laufzeit:tool-schleife",
            "ok" if res.ok else "degraded",
            "Tool-Dispatch zur Laufzeit funktioniert" if res.ok else res.error,
        ))

    # -- final real run ----------------------------------------------------

    def _final_real_run(self, spec, resolved, say) -> tuple[bool | None, str]:
        if not self.final_real_run:
            return None, ""
        say("Finaler Abnahme-Lauf gegen das echte lokale Modell…")
        files = build_package(spec, resolved)
        driver = (
            "import sys, traceback\n"
            "sys.path.insert(0, '.')\n"
            "try:\n"
            "    from bot.config import BotConfig\n"
            "    from bot.runner import BotRunner\n"
            "    bot = BotRunner(BotConfig())\n"
            "    out = bot.respond('Stell dich in einem Satz vor und sage, was du kannst.')\n"
            "    print('===OUTPUT===')\n"
            "    print(out)\n"
            "    print('===END===')\n"
            "except Exception:\n"
            "    traceback.print_exc()\n"
            "    sys.exit(1)\n"
        )
        with sandbox.materialized(files) as d:
            res = sandbox.run_driver(d, driver, self.real_run_timeout)
        captured = res.stdout
        if "===OUTPUT===" in captured and "===END===" in captured:
            captured = captured.split("===OUTPUT===", 1)[1].split("===END===", 1)[0].strip()
        if not res.ok and not captured.strip():
            captured = res.output
        return res.ok, captured

    # -- io ----------------------------------------------------------------

    def _write_files(self, files: dict[str, str], out_dir: Path) -> None:
        for rel_path, content in files.items():
            target = out_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3: WORLD-LOOP STATE-MACHINE
    # Der autonome Dauerbetrieb-Modus — der Orchestrator arbeitet endlos:
    # ══════════════════════════════════════════════════════════════════════════

    def run_world_loop(
        self,
        *,
        goals: list[dict] | None = None,
        out_dir: Path | None = None,
        max_cycles: int = 0,
        progress: Progress | None = None,
    ) -> list[dict]:
        """Startet die autonome World-Loop über den neuen Workflow-Kernel."""
        from .workflow.store import StateStore
        from .workflow.router import JobRouter
        from .workflow.engine import WorkflowKernel
        from .workflow.models import JobStatus

        say = progress or (lambda _m: None)
        say("Starte neuen Workflow-Kernel (Durable Execution)...")

        # Initialisiere Kernel
        from pathlib import Path
        import sys
        
        # Sicherstellen dass BOT1_ROOT existiert
        BOT1_ROOT = Path(__file__).resolve().parent.parent.parent
        store_path = BOT1_ROOT / "output" / "state.db"
        store = StateStore(store_path)
        kernel = WorkflowKernel(store)

        if not goals:
            say("Keine Ziele übergeben. Beende Workflow-Kernel.")
            return []

        completed_cycles = []

        for goal_dict in goals:
            goal_desc = goal_dict.get("description", goal_dict.get("name", "Unknown Goal"))
            spec = goal_dict.get("spec")
            
            spec_dict = None
            if spec:
                if hasattr(spec, "model_dump"):
                    spec_dict = spec.model_dump()
                elif hasattr(spec, "dict"):
                    spec_dict = spec.dict()
                else:
                    spec_dict = spec.__dict__
                    
            say(f"Router klassifiziert Ziel: {goal_desc}")
            job = JobRouter.classify_and_route(goal_desc, spec=spec_dict)
            
            say(f"Speichere Job {job.id} mit {len(job.tasks)} Tasks...")
            store.save_job(job)
            
            say(f"Führe Job {job.id} aus...")
            kernel.execute_job(job.id)
            
            # Überprüfe Ergebnis
            updated_job = store.get_job(job.id)
            if updated_job:
                say(f"Job beendet mit Status: {updated_job.status.value}")
                completed_cycles.append({
                    "goal": goal_dict,
                    "job_id": updated_job.id,
                    "status": updated_job.status.value
                })

        return completed_cycles
    # -- World-Loop Helpers ------------------------------------------------

    def _check_incoming_messages(self) -> list[dict]:
        """Prüft eingehende Messenger-Nachrichten und konvertiert sie in Ziele.

        Quellen (in Reihenfolge):
          1. Webhook-Listener Queue (Port 9999) — primäre Quelle
          2. LangBot HTTP-API — falls Service läuft
        """
        goals: list[dict] = []

        # 1) Webhook-Listener Queue
        try:
            from .services.webhook_listener import get_pending_messages
            raw_msgs = get_pending_messages(max_count=5)
            for msg in raw_msgs:
                if msg.get("text"):
                    goals.append({
                        "name": f"msg_{msg.get('platform', 'webhook')}_{len(goals)}",
                        "description": msg["text"],
                        "priority": 5,
                        "source": msg.get("platform", "webhook"),
                        "sender": msg.get("sender", ""),
                    })
        except Exception as exc:
            logger.debug("Webhook-Queue-Check fehlgeschlagen: %s", exc)

        # 2) LangBot HTTP-API als Fallback
        if not goals and self._registry:
            messenger = self._registry.get_service("langbot")
            if messenger:
                try:
                    result = messenger.execute("messages/pending", {})
                    if result.ok and result.data:
                        msgs = result.data if isinstance(result.data, list) else [result.data]
                        for msg in msgs:
                            if isinstance(msg, dict) and msg.get("text"):
                                goals.append({
                                    "name": f"langbot_{len(goals)}",
                                    "description": msg["text"],
                                    "priority": 5,
                                    "source": msg.get("platform", "langbot"),
                                })
                except Exception as exc:
                    logger.debug("LangBot-Check fehlgeschlagen: %s", exc)

        return goals

    def _ingest_cycle_learnings(self, goal: dict, data: dict) -> None:  # noqa: C901
        """Speist die Erkenntnisse eines Zyklus in das Langzeitgedächtnis (MaxKB) ein."""
        if not self._registry:
            return

        try:
            self.researcher.ingest_knowledge(
                title=f"World-Loop Zyklus: {goal.get('name', '?')}",
                content=(
                    f"Ziel: {goal.get('description', '')}\n"
                    f"Build-Ergebnis: {data.get('build_result', {})}\n"
                    f"Review: {data.get('review', {})}\n"
                    f"Deploy: {data.get('deploy', {})}\n"
                ),
                source="world_loop",
                tags=["learning", "cycle", goal.get("name", "unknown")],
            )
        except Exception as exc:
            logger.debug("Wissens-Injektion fehlgeschlagen: %s", exc)


# ── Modul-Hilfsfunktionen ─────────────────────────────────────────────────────

_SCIENCE_KEYWORDS = {
    "protein", "molekül", "molecule", "gen", "gene", "dna", "rna", "mrna",
    "inhibitor", "enzym", "enzyme", "antibody", "antikörper", "peptide",
    "cancer", "krebs", "tumor", "alzheimer", "parkinson", "diabetes",
    "crispr", "alphafold", "uniprot", "pubmed", "arxiv", "clinical trial",
    "klinische studie", "bioaktiv", "bioactive", "chembl", "ligand",
    "receptor", "rezeptor", "mutation", "sequenz", "genome", "genomik",
    "drug", "medikament", "wirkstoff", "pharma", "therapie", "therapy",
    "protein folding", "proteinfaltung", "struct", "binding",
}


def _is_science_goal(description: str) -> bool:
    """Erkennt ob ein Ziel wissenschaftlicher Natur ist (→ ScienceAgent)."""
    d = description.lower()
    return any(kw in d for kw in _SCIENCE_KEYWORDS)
