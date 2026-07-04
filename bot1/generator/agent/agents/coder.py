"""CoderAgent: schreibt den Body eines einzelnen generierten Tools.

Erweitert: Wenn die AI-OS ServiceRegistry verfügbar ist, nutzt der Coder
agenticSeek für autonomes Coding und die Knowledge-Service (MaxKB), um
vor der Code-Generierung relevante API-Dokumentation zu recherchieren.
"""
from __future__ import annotations

import ast
import json
import logging
import re

from ...interview.prompts import CODE_AGENT_SYSTEM_PROMPT, CODER_TOOL_PROMPT
from ..build_plan import ToolTask
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


def _top_level_functions(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _value_for_annotation(annotation) -> object:
    name = ""
    if isinstance(annotation, ast.Name):
        name = annotation.id
    elif isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        name = annotation.value.id
    name = name.lower()
    if name in ("int",):
        return 3
    if name in ("float",):
        return 1.5
    if name in ("bool",):
        return True
    if name in ("list", "tuple", "sequence"):
        return ["test"]
    if name in ("dict", "mapping"):
        return {"k": "v"}
    return "test"


def sample_from_code(code: str, name: str) -> dict:
    """Baut Beispiel-Argumente aus der TATSÄCHLICHEN Signatur der Funktion.

    So testet das Gate die Funktion korrekt, egal was der Architekt geraten hat.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            a = node.args
            all_args = list(getattr(a, "posonlyargs", [])) + list(a.args)
            sample: dict = {}
            for arg in all_args:
                if arg.arg == "self":
                    continue
                sample[arg.arg] = _value_for_annotation(arg.annotation)
            return sample
    return {}


def _salvage_name(code: str, name: str) -> str | None:
    """Akzeptiert Code mit genau einer Top-Level-Funktion und benennt sie auf `name` um."""
    funcs = _top_level_functions(code)
    if name in funcs:
        return code.strip()
    if len(funcs) == 1:
        old = funcs[0]
        renamed = re.sub(rf"\bdef\s+{re.escape(old)}\s*\(", f"def {name}(", code, count=1)
        if name in _top_level_functions(renamed):
            return renamed.strip()
    return None


class CoderAgent(BaseAgent):
    def generate_tool(self, task: ToolTask) -> str | None:
        """Gibt validen Funktions-Quelltext zurück oder None bei Fehlschlag.

        AI-OS Modus: Nutzt agenticSeek für komplexe Code-Generierung und
        recherchiert über MaxKB relevante API-Dokumentation.
        """
        # --- AI-OS Modus: agenticSeek für autonomes Coding ---
        if self.has_registry:
            code = self._generate_via_service(task)
            if code:
                return code
            logger.info(
                "agenticSeek nicht verfügbar für '%s', Fallback auf lokales LLM.",
                task.name,
            )

        # --- Standard-Modus: lokaler LLM-Call ---
        return self._generate_via_llm(task)

    def _generate_via_service(self, task: ToolTask) -> str | None:
        """Versucht, Code über agenticSeek + Knowledge-Recherche zu generieren."""
        # 1) Recherchiere relevante API-Doku
        api_context = self._research_for_task(task)

        # 2) Versuche agenticSeek
        coding_svc = self.registry.get_service("agenticseek")
        if coding_svc is None:
            return None

        try:
            if not coding_svc.ensure_running(timeout_seconds=5.0):
                return None

            prompt = (
                f"Schreibe eine Python-Funktion mit exakt dieser Signatur:\n"
                f"  {task.signature or f'def {task.name}(query: str) -> str'}\n\n"
                f"Beschreibung: {task.description}\n"
                f"Beispiel-Input: {json.dumps(task.sample_input, ensure_ascii=False)}\n"
            )
            if api_context:
                prompt += f"\nRelevante API-Dokumentation:\n{api_context}\n"

            result = coding_svc.execute("generate", {
                "task": prompt,
                "language": "python",
            })
            if result.ok and result.data:
                code = str(result.data)
                from .base_agent import extract_code
                code = extract_code(code) or code
                return _salvage_name(code, task.name)
        except Exception as exc:
            logger.debug("agenticSeek Code-Generierung fehlgeschlagen: %s", exc)

        return None

    def _research_for_task(self, task: ToolTask) -> str:
        """Recherchiert relevante Informationen für die Code-Generierung."""
        if not self.has_registry:
            return ""

        knowledge_svc = self.registry.get_service("maxkb")
        if knowledge_svc is None:
            return ""

        try:
            result = knowledge_svc.execute("search", {
                "query": f"Python implementation: {task.description}",
                "top_k": 2,
                "dataset": "api_catalog",
            })
            if result.ok and result.data:
                return str(result.data)[:1500]
        except Exception as exc:
            logger.debug("Knowledge-Recherche für Coder fehlgeschlagen: %s", exc)

        return ""

    def _generate_via_llm(self, task: ToolTask) -> str | None:
        """Standard-Modus: generiert Code über den lokalen LLM-Call."""
        user = CODER_TOOL_PROMPT.format(
            name=task.name,
            description=task.description,
            signature=task.signature or f"def {task.name}(query: str) -> str",
            sample_input=json.dumps(task.sample_input, ensure_ascii=False),
        )
        code = self.ask_code(CODE_AGENT_SYSTEM_PROMPT, user)
        if not code:
            return None
        return _salvage_name(code, task.name)

