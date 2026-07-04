"""ArchitectAgent: plant die Tools des Bots (Bibliothek vs. generieren).

Erweitert: Wenn die AI-OS ServiceRegistry verfügbar ist, nutzt der Architekt
den dynamischen Skill-Katalog (ClawHub) statt der statischen Bibliothek und
zieht Architektur-Wissen aus MaxKB (system-design-primer, developer-roadmap).
"""
from __future__ import annotations

import logging
import re

from ...interview.prompts import ARCHITECT_AGENT_PROMPT, ARCHITECT_AGENT_SYSTEM_PROMPT
from ...models.bot_spec import BotSpec
from ..build_plan import ToolTask
from ..tools import library
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip().lower()).strip("_")
    s = re.sub(r"_+", "_", s)
    return s or "tool"


def fallback_tooltasks(spec: BotSpec) -> list[ToolTask]:
    """Deterministische Auflösung ohne LLM (Bibliothek wenn Name passt, sonst Stub)."""
    tasks: list[ToolTask] = []
    for t in spec.tools:
        cap = t.name if library.get(t.name) else None
        tasks.append(ToolTask(
            name=_slug(t.name),
            description=t.description,
            capability=cap,
            needs_generation=cap is None,
            signature=f"def {_slug(t.name)}(query: str) -> str",
            sample_input={"query": "test"},
        ))
    return tasks


class ArchitectAgent(BaseAgent):
    def plan_tools(self, spec: BotSpec) -> list[ToolTask]:
        existing = "\n".join(f"- {t.name}: {t.description}" for t in spec.tools) \
            or "(keine ausdrücklich genannt)"

        # AI-OS Modus: erweiterter Katalog aus der Registry + Wissensabfrage
        catalog = self._build_catalog()
        knowledge_context = self._query_architecture_knowledge(spec)

        user = ARCHITECT_AGENT_PROMPT.format(
            bot_name=spec.name,
            bot_type=spec.bot_type.value,
            description=spec.description,
            use_cases=", ".join(spec.use_cases) or "—",
            existing_tools=existing,
            catalog=catalog,
        )

        # Wenn wir Architektur-Wissen haben, fügen wir es dem Prompt hinzu
        if knowledge_context:
            user += (
                "\n\n--- ARCHITEKTUR-WISSEN (aus dem AI-OS Gedächtnis) ---\n"
                f"{knowledge_context}\n"
                "Nutze dieses Wissen, um besonders robuste und skalierbare "
                "Tool-Architekturen zu planen."
            )

        data = self.ask_json(ARCHITECT_AGENT_SYSTEM_PROMPT, user)
        tasks = self._parse(data)
        # Wenn der Architekt nichts Brauchbares liefert, aber der Nutzer Tools wollte:
        if not tasks and spec.tools:
            return fallback_tooltasks(spec)
        return tasks

    def _build_catalog(self) -> str:
        """Baut den Skill-Katalog — dynamisch aus Registry oder statisch aus library."""
        if self.has_registry:
            # Dynamischer Katalog: alle registrierten Skills + Legacy-Tools
            catalog = self.registry.skill_catalog()
            logger.info("Architekt nutzt AI-OS Registry (%d Skills)", len(self.registry.all_skills))
            return catalog
        # Fallback: nur die alten 6 Tools
        return library.capability_catalog()

    def _query_architecture_knowledge(self, spec: BotSpec) -> str:
        """Fragt die Wissensbasis nach relevantem Architektur-Wissen ab.

        Nutzt MaxKB/WeKnora, um Inhalte aus system-design-primer,
        developer-roadmap etc. zu durchsuchen.
        """
        if not self.has_registry:
            return ""

        knowledge_svc = self.registry.get_service("maxkb")
        if knowledge_svc is None:
            return ""

        # Versuche, relevantes Architektur-Wissen abzufragen
        try:
            query = (
                f"Architektur und Design-Patterns für: {spec.description}. "
                f"Bot-Typ: {spec.bot_type.value}. "
                f"Use Cases: {', '.join(spec.use_cases)}."
            )
            result = knowledge_svc.execute("search", {
                "query": query,
                "top_k": 3,
                "dataset": "software_architecture",
            })
            if result.ok and result.data:
                return str(result.data)[:2000]
        except Exception as exc:
            logger.debug("Knowledge-Abfrage fehlgeschlagen (nicht kritisch): %s", exc)

        return ""

    def _parse(self, data: dict) -> list[ToolTask]:
        raw_tools = data.get("tools") if isinstance(data, dict) else None
        if not isinstance(raw_tools, list):
            return []
        tasks: list[ToolTask] = []
        seen: set[str] = set()

        # Gültige Capabilities: aus Registry ODER aus statischer Bibliothek
        if self.has_registry:
            valid_caps = {s.name for s in self.registry.all_skills}
            valid_caps.update(library.available_capabilities())
        else:
            valid_caps = set(library.available_capabilities())

        for item in raw_tools:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = _slug(item["name"])
            if name in seen:
                continue
            seen.add(name)
            cap = item.get("capability")
            if cap not in valid_caps:
                cap = None
            needs_gen = cap is None
            sample = item.get("sample_input")
            tasks.append(ToolTask(
                name=name,
                description=str(item.get("description", "")),
                capability=cap,
                needs_generation=needs_gen,
                signature=str(item.get("signature") or f"def {name}(query: str) -> str"),
                sample_input=sample if isinstance(sample, dict) else {"query": "test"},
            ))
        return tasks

