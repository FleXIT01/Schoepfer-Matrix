"""Factory: Baut das gesamte AI-OS Service-Netzwerk auf.

Diese Datei ist der Dreh- und Angelpunkt. Sie instanziiert alle
36+ Services, registriert sie in der ServiceRegistry und gibt
dem Orchestrator ein fertiges, voll vernetztes Ökosystem.
"""
from __future__ import annotations

import logging

from .service_registry import ServiceRegistry, SkillEntry

# Service-Imports
from .openclaw_service import OpenClawService
from .knowledge_service import (
    KnowledgeService, KNOWLEDGE_REPOS,
    create_weknora_config, create_khoj_config,
)
from .coding_service import CodingService, create_superagi_config
from .review_service import ReviewService
from .research_service import (
    ResearchService, create_surfsense_config, create_deepwiki_config,
)
from .media_service import MediaService, PDFTranslateService
from .chimera_service import ChimeraService, ResourcePlannerService
from .messenger_service import MessengerService, create_cowagent_config
from .docker_service import DockerControlService
from .http_service import HttpService

logger = logging.getLogger(__name__)

# Basis-Pfad: erkennt den Projekt-Root automatisch
# (3 Ebenen über dieser Datei: services -> agent -> generator -> bot1 -> allinall)
import sys
from pathlib import Path as _Path
_ALLINALL_BASE = str(_Path(__file__).resolve().parent.parent.parent.parent.parent)


def build_registry(
    *,
    base_path: str = _ALLINALL_BASE,
    load_legacy: bool = True,
    auto_start_core: bool = False,
) -> ServiceRegistry:
    """Erstellt und konfiguriert die vollständige Service-Registry.

    Args:
        base_path: Basisverzeichnis, in dem alle 36 Repos liegen.
        load_legacy: Importiert die alten 6 library.py-Tools als Skills.
        auto_start_core: Startet die Kern-Services sofort.

    Returns:
        Eine vollständig konfigurierte ServiceRegistry.
    """
    registry = ServiceRegistry()

    # ─── Layer 0: Hardware & Control ─────────────────────────────────────
    planner = ResourcePlannerService(f"{base_path}\\local-llm-planner")
    chimera = ChimeraService(f"{base_path}\\projekt_für_ollama")
    docker_ctl = DockerControlService(f"{base_path}\\ai_agent_0")
    registry.register_service(planner)
    registry.register_service(chimera)
    registry.register_service(docker_ctl)

    # gpt_from_scratch: trainiert kleine Sub-Modelle (Python-Bibliothek → Skill)
    registry.register_skill(SkillEntry(
        name="gpt_from_scratch",
        description="Trainiert kleine GPT-Sub-Modelle von Grund auf (nanoGPT-Stil)",
        source_type="local",
        capabilities=["model_training", "fine_tuning", "micro_model"],
        tags=["core", "training", "meta"],
    ))

    # ─── Layer 1: Memory & Knowledge ─────────────────────────────────────
    knowledge = KnowledgeService(f"{base_path}\\MaxKB-2")
    registry.register_service(knowledge)

    # WeKnora und Khoj als zusätzliche Wissens-Services
    weknora = HttpService(create_weknora_config(f"{base_path}\\WeKnora-main"))
    khoj = HttpService(create_khoj_config(f"{base_path}\\khoj-master"))
    registry.register_service(weknora)
    registry.register_service(khoj)

    # ─── Layer 2: Core Brain ─────────────────────────────────────────────
    openclaw = OpenClawService(f"{base_path}\\openclaw-main")
    registry.register_service(openclaw)

    # ─── Layer 3: Orchestration (Swarm, Agent Framework) ─────────────────
    # Diese sind Python-Libraries, kein HTTP-Service → als Skills registrieren
    registry.register_skill(SkillEntry(
        name="swarm_orchestration",
        description="Multi-Agent Task-Zerlegung und Delegation (OpenAI Swarm)",
        source_type="local",
        capabilities=["task_decomposition", "multi_agent", "delegation"],
        tags=["orchestration", "swarm"],
    ))
    registry.register_skill(SkillEntry(
        name="agent_framework",
        description="Agent-Framework für spezialisierte Sub-Agenten",
        source_type="local",
        capabilities=["agent_creation", "agent_management"],
        tags=["orchestration", "framework"],
    ))

    # ─── Layer 4: Worker Services ────────────────────────────────────────
    coding = CodingService(f"{base_path}\\agenticSeek-main")
    superagi = HttpService(create_superagi_config(f"{base_path}\\SuperAGI-main"))
    reviewer = ReviewService(f"{base_path}\\repo-critic-ai")
    researcher = ResearchService(f"{base_path}\\gpt-researcher-main")
    surfsense = HttpService(create_surfsense_config(f"{base_path}\\SurfSense-main"))
    deepwiki = HttpService(create_deepwiki_config(f"{base_path}\\deepwiki-open-main"))
    media = MediaService(f"{base_path}\\ComfyUI_portable")
    pdf_translate = PDFTranslateService(f"{base_path}\\PDFMathTranslate-main")

    for svc in [coding, superagi, reviewer, researcher, surfsense,
                deepwiki, media, pdf_translate]:
        registry.register_service(svc)

    # ─── Layer 5: Interfaces ─────────────────────────────────────────────
    messenger = MessengerService(f"{base_path}\\LangBot-master")
    cowagent = HttpService(create_cowagent_config(f"{base_path}\\CowAgent-master"))
    registry.register_service(messenger)
    registry.register_service(cowagent)

    # UI-Services (open-webui, cherry-studio, shell_gpt) als Skills
    registry.register_skill(SkillEntry(
        name="open_webui",
        description="Web-basiertes Chat-Interface (wie ChatGPT)",
        source_type="service",
        service_name="open-webui",
        capabilities=["web_ui", "chat_interface"],
        tags=["interface", "web"],
    ))
    registry.register_skill(SkillEntry(
        name="cherry_studio",
        description="Desktop-App für LLM-Interaktion mit MCP-Support",
        source_type="service",
        service_name="cherry-studio",
        capabilities=["desktop_ui", "mcp_client"],
        tags=["interface", "desktop"],
    ))
    registry.register_skill(SkillEntry(
        name="shell_gpt",
        description="Terminal/CLI-Interface — führt Shell-Befehle über LLM aus",
        source_type="local",
        capabilities=["cli", "shell_commands", "devops"],
        tags=["interface", "terminal", "devops"],
    ))

    # ─── Wissens-Repos als Skills registrieren ───────────────────────────
    for repo_name, repo_info in KNOWLEDGE_REPOS.items():
        registry.register_skill(SkillEntry(
            name=f"knowledge_{repo_name}",
            description=repo_info["description"],
            source_type="local",
            capabilities=["knowledge_source"],
            tags=["knowledge", repo_info["dataset"]],
        ))

    # ─── ClawHub als Meta-Skill ──────────────────────────────────────────
    registry.register_skill(SkillEntry(
        name="clawhub",
        description="Skill-Marktplatz: Registriert und teilt Agenten-Fähigkeiten",
        source_type="service",
        service_name="clawhub",
        capabilities=["skill_marketplace", "plugin_registry"],
        tags=["meta", "marketplace"],
    ))

    # ─── Legacy-Bibliothek importieren ───────────────────────────────────
    if load_legacy:
        registry.load_legacy_library()

    # ─── Scale-to-Zero Hintergrund-Thread starten ────────────────────────
    registry.start_idle_checker(interval_seconds=60)

    # ─── Kern-Services starten (optional) ────────────────────────────────
    if auto_start_core:
        for svc in registry.all_services:
            if svc.config.auto_start:
                svc.start()

    logger.info(
        "AI-OS Registry initialisiert: %d Services, %d Skills",
        len(registry.all_services), len(registry.all_skills),
    )

    return registry
