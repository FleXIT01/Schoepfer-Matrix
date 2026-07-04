from __future__ import annotations

import json
import re

from ..llm.base import LLMAdapter, LLMMessage
from ..models.interview import InterviewState
from .prompts import EXTRACTION_SYSTEM_PROMPT


def parse_json_robust(raw: str) -> dict:
    """Extract JSON from LLM output. Handles markdown fences and leading text."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = cleaned.replace("```", "").strip()

    # Try full string first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find outermost {...} block (balanced braces via counting)
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return {}


def _merge_list(existing: list, incoming) -> list:
    if not incoming:
        return existing
    if isinstance(incoming, list):
        merged = list(existing)
        for item in incoming:
            if item and item not in merged:
                merged.append(item)
        return merged
    return existing


class InterviewExtractor:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm

    def extract_from_initial(self, state: InterviewState) -> InterviewState:
        prompt = (
            f"Beschreibung des gewünschten Bots:\n\n{state.raw_initial_description}"
        )
        raw = self._llm.chat_structured(
            messages=[LLMMessage(role="user", content=prompt)],
            system=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1,
        )
        extracted = parse_json_robust(raw)
        return self._apply_extraction(state, extracted)

    def update_from_answer(
        self, state: InterviewState, question: str, answer: str
    ) -> InterviewState:
        context = (
            f"Ursprüngliche Beschreibung: {state.raw_initial_description}\n\n"
            f"Rückfrage: {question}\n"
            f"Antwort: {answer}"
        )
        raw = self._llm.chat_structured(
            messages=[LLMMessage(role="user", content=context)],
            system=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1,
        )
        extracted = parse_json_robust(raw)
        return self._apply_extraction(state, extracted)

    def _apply_extraction(self, state: InterviewState, data: dict) -> InterviewState:
        if not data:
            return state

        updated = state.model_copy()

        if data.get("bot_name") and not updated.bot_name:
            updated.bot_name = str(data["bot_name"])
        if data.get("bot_purpose"):
            updated.bot_purpose = str(data["bot_purpose"])
        if data.get("target_users"):
            updated.target_users = str(data["target_users"])
        if data.get("language_preference"):
            updated.language_preference = str(data["language_preference"])
        if data.get("memory_duration"):
            updated.memory_duration = str(data["memory_duration"])

        if data.get("needs_memory") is not None and updated.needs_memory is None:
            updated.needs_memory = bool(data["needs_memory"])
        if data.get("needs_tools") is not None and updated.needs_tools is None:
            updated.needs_tools = bool(data["needs_tools"])

        updated.primary_actions = _merge_list(
            updated.primary_actions, data.get("primary_actions")
        )
        updated.input_types = _merge_list(
            updated.input_types, data.get("input_types")
        )
        updated.output_types = _merge_list(
            updated.output_types, data.get("output_types")
        )
        updated.tool_descriptions = _merge_list(
            updated.tool_descriptions, data.get("tool_descriptions")
        )
        updated.integrations = _merge_list(
            updated.integrations, data.get("integrations")
        )
        updated.constraints = _merge_list(
            updated.constraints, data.get("constraints")
        )
        updated.use_cases = _merge_list(
            updated.use_cases, data.get("use_cases")
        )
        updated.error_scenarios = _merge_list(
            updated.error_scenarios, data.get("error_scenarios")
        )

        return updated
