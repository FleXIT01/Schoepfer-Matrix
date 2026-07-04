from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from ..blocks._base import get_jinja_env
from ..llm.base import LLMAdapter, LLMMessage
from ..models.bot_spec import (
    BotSpec,
    BotType,
    ExampleConversation,
    ExampleTurn,
    InputSchemaSpec,
    LLMProviderSpec,
    MemoryStrategy,
    OutputSchemaSpec,
    SchemaField,
    StateSchemaSpec,
    ToolSpec,
)
from ..models.interview import InterviewState
from ..interview.prompts import (
    SPEC_GENERATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT_GENERATION_TEMPLATE,
    EXAMPLES_GENERATION_TEMPLATE,
)

_BOT_TYPE_KEYWORDS = {
    BotType.CUSTOMER_SUPPORT: ["kundenservice", "support", "hilfe", "anfrage", "service"],
    BotType.DATA_EXTRACTION: ["extraktion", "daten", "parsen", "scraping", "extrahieren"],
    BotType.TASK_AUTOMATION: ["automatisierung", "workflow", "prozess", "automation"],
    BotType.QA_ASSISTANT: ["fragen", "antworten", "wissen", "faq", "quiz"],
    BotType.CODING_ASSISTANT: ["code", "programmierung", "entwicklung", "debug"],
    BotType.DOCUMENT_PROCESSOR: ["dokument", "pdf", "datei", "zusammenfassung"],
}


def _infer_bot_type(purpose: str) -> BotType:
    lower = (purpose or "").lower()
    for bot_type, keywords in _BOT_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return bot_type
    return BotType.CUSTOM


def _infer_memory_strategy(state: InterviewState) -> MemoryStrategy:
    if not state.needs_memory:
        return MemoryStrategy.NONE
    if state.memory_duration == "permanent":
        return MemoryStrategy.PERSISTENT_JSON
    return MemoryStrategy.IN_SESSION


def _compute_confidence(state: InterviewState) -> float:
    checkable = [
        state.bot_purpose,
        state.target_users,
        state.primary_actions,
        state.needs_memory,
        state.needs_tools,
        state.language_preference,
    ]
    filled = sum(
        1 for v in checkable
        if v is not None and v != [] and v != ""
    )
    return round(filled / len(checkable), 2)


class BotSpecBuilder:
    def __init__(self, llm: LLMAdapter, provider: str = "anthropic", model: str = "claude-sonnet-4-6") -> None:
        self._llm = llm
        self._provider = provider
        self._model = model

    def build(self, state: InterviewState) -> BotSpec:
        spec = BotSpec()
        missing: list[str] = []

        # --- Direct field mappings ---
        spec.name = state.bot_name or self._infer_name(state)
        spec.language = state.language_preference or "de"
        spec.use_cases = list(state.use_cases) or list(state.primary_actions)
        spec.constraints = list(state.constraints)
        spec.integration_points = list(state.integrations)

        if state.bot_purpose:
            spec.description = state.bot_purpose
        else:
            missing.append("description")

        if state.target_users:
            spec.target_users = state.target_users
        else:
            missing.append("target_users")

        spec.bot_type = _infer_bot_type(state.bot_purpose or "")
        spec.memory_strategy = _infer_memory_strategy(state)
        spec.llm = LLMProviderSpec(provider=self._provider, model=self._model)

        # --- Tool specs ---
        if state.needs_tools and state.tool_descriptions:
            spec.tools = self._build_tools(state.tool_descriptions)
        elif state.needs_tools:
            missing.append("tool_descriptions")

        # --- LLM-assisted generation ---
        spec.system_prompt = self._generate_system_prompt(state, spec.name)
        spec.example_conversations = self._generate_examples(state, spec.name)
        spec.developer_notes = self._generate_developer_notes(spec)

        # --- Schemas ---
        spec.input_schema = self._build_input_schema(state)
        spec.output_schema = self._build_output_schema(state)
        spec.state_schema = self._build_state_schema(state)

        # --- Metadata ---
        spec.confidence_score = _compute_confidence(state)
        spec.missing_fields = missing
        spec.generated_at = datetime.now(timezone.utc).isoformat()

        return spec

    def _infer_name(self, state: InterviewState) -> str:
        purpose = state.bot_purpose or ""
        if "kundenservice" in purpose.lower():
            return "KundenserviceBot"
        if "support" in purpose.lower():
            return "SupportBot"
        words = purpose.split()[:3]
        if words:
            return "".join(w.capitalize() for w in words) + "Bot"
        return "MeinBot"

    def _build_tools(self, descriptions: list[str]) -> list[ToolSpec]:
        tools = []
        for desc in descriptions:
            name = re.sub(r"[^a-zA-Z0-9_]", "_", desc.lower()[:40]).strip("_")
            name = re.sub(r"_+", "_", name)
            tools.append(ToolSpec(
                name=name,
                description=desc,
                parameters={"query": {"type": "string", "description": "Eingabe für das Tool"}},
                returns="string",
            ))
        return tools

    def _generate_system_prompt(self, state: InterviewState, bot_name: str) -> str:
        if not state.bot_purpose:
            return f"# TODO: Bot-Zweck nicht definiert — System-Prompt für {bot_name} manuell erstellen"

        prompt = SYSTEM_PROMPT_GENERATION_TEMPLATE.format(
            bot_name=bot_name,
            bot_purpose=state.bot_purpose,
            target_users=state.target_users or "Allgemeine Nutzer",
            primary_actions=", ".join(state.primary_actions) or "Fragen beantworten",
            language=state.language_preference or "de",
            constraints=", ".join(state.constraints) if state.constraints else "keine",
        )
        return self._llm.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            system=SPEC_GENERATION_SYSTEM_PROMPT,
            temperature=0.3,
        ).strip()

    def _generate_examples(self, state: InterviewState, bot_name: str) -> list[ExampleConversation]:
        if not state.bot_purpose:
            return []

        prompt = EXAMPLES_GENERATION_TEMPLATE.format(
            bot_name=bot_name,
            bot_purpose=state.bot_purpose,
            target_users=state.target_users or "Allgemeine Nutzer",
            primary_actions=", ".join(state.primary_actions) or "Fragen beantworten",
            use_cases=", ".join(state.use_cases) if state.use_cases else "allgemeine Nutzung",
            language=state.language_preference or "de",
        )
        raw = self._llm.chat_structured(
            messages=[LLMMessage(role="user", content=prompt)],
            system=SPEC_GENERATION_SYSTEM_PROMPT,
            temperature=0.3,
        )

        data = self._parse_examples_json(raw)
        if not data:
            return []

        examples = []
        for item in data:
            if not isinstance(item, dict):
                continue
            turns = [
                ExampleTurn(role=t.get("role", "user"), content=t.get("content", ""))
                for t in item.get("turns", [])
                if isinstance(t, dict)
            ]
            examples.append(ExampleConversation(
                description=item.get("description", ""),
                turns=turns,
            ))
        return examples

    def _parse_examples_json(self, raw: str) -> list:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().replace("```", "").strip()
        # Try to find [...] array
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []

    def _generate_developer_notes(self, spec: "BotSpec") -> str:
        env = get_jinja_env()
        template = env.get_template("block3_developer_notes.md.j2")
        return template.render(spec=spec).strip()

    def _build_input_schema(self, state: InterviewState) -> InputSchemaSpec:
        fields = [SchemaField(name="message", type="string", required=True, description="Nutzernachricht")]
        if "datei" in " ".join(state.input_types).lower() or "file" in " ".join(state.input_types).lower():
            fields.append(SchemaField(name="file_path", type="string", required=False, description="Optionaler Dateipfad"))
        return InputSchemaSpec(fields=fields)

    def _build_output_schema(self, state: InterviewState) -> OutputSchemaSpec:
        fields = [SchemaField(name="response", type="string", required=True, description="Bot-Antwort")]
        if state.needs_tools:
            fields.append(SchemaField(name="tool_calls", type="array", required=False, description="Ausgeführte Tool-Aufrufe"))
        return OutputSchemaSpec(fields=fields)

    def _build_state_schema(self, state: InterviewState) -> StateSchemaSpec:
        fields = [SchemaField(name="conversation_history", type="array", required=True, description="Gesprächsverlauf")]
        if state.needs_memory:
            fields.append(SchemaField(name="user_context", type="object", required=False, description="Nutzer-spezifischer Kontext"))
        for integration in state.integrations:
            field_name = re.sub(r"[^a-z0-9_]", "_", integration.lower())[:30]
            fields.append(SchemaField(name=f"{field_name}_cache", type="object", required=False, description=f"Cache für {integration}"))
        return StateSchemaSpec(fields=fields)
