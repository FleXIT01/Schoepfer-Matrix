from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..llm.base import LLMAdapter, LLMError, LLMMessage
from ..models.interview import InterviewState
from .extractor import InterviewExtractor
from .prompts import (
    FOLLOWUP_PROMPT_TEMPLATE,
    INTERVIEW_SYSTEM_PROMPT,
    OPENING_QUESTION,
)

logger = logging.getLogger(__name__)

_FIELD_LABELS = {
    "bot_purpose": "Zweck des Bots",
    "target_users": "Zielgruppe",
    "primary_actions": "Hauptfunktionen",
    "needs_memory": "Memory/Gedächtnis benötigt?",
    "needs_tools": "Externe Tools benötigt?",
}

_SKIP_INPUTS = {"fertig", "weiter", "skip", "überspringen", ""}


@dataclass
class InterviewResult:
    state: InterviewState
    conversation_history: list[dict] = field(default_factory=list)


class InterviewConductor:
    def __init__(self, llm: LLMAdapter, max_followups: int = 5) -> None:
        self._llm = llm
        self._max_followups = max_followups
        self._extractor = InterviewExtractor(llm)

    def run(self, cli) -> InterviewResult:
        state = InterviewState()

        cli.display(f"\n{OPENING_QUESTION}\n", markdown=True)
        initial_answer = cli.prompt_input("> ")
        state.raw_initial_description = initial_answer
        state.conversation_history.append(
            {"role": "user", "content": initial_answer}
        )

        if not initial_answer.strip():
            state.is_complete = True
            return InterviewResult(state=state)

        with cli.status("Analysiere Beschreibung..."):
            try:
                state = self._extractor.extract_from_initial(state)
            except LLMError as exc:
                logger.warning("Extraktion fehlgeschlagen: %s", exc)
                cli.display(f"\n[Hinweis: Automatische Analyse fehlgeschlagen — fahre mit Rückfragen fort.]")

        missing = self._compute_missing(state)
        followup_count = 0

        while missing and followup_count < self._max_followups:
            try:
                with cli.status("Formuliere Rückfrage..."):
                    question = self._generate_followup(state, missing)
            except LLMError as exc:
                logger.warning("Rückfrage-Generierung fehlgeschlagen: %s", exc)
                break

            cli.display(f"\n{question}\n", markdown=True)

            answer = cli.prompt_input("> ")

            if answer.strip().lower() in _SKIP_INPUTS:
                break

            state.conversation_history.append(
                {"role": "assistant", "content": question}
            )
            state.conversation_history.append(
                {"role": "user", "content": answer}
            )

            try:
                with cli.status("Analysiere Antwort..."):
                    state = self._extractor.update_from_answer(state, question, answer)
            except LLMError as exc:
                logger.warning("Antwort-Extraktion fehlgeschlagen: %s", exc)

            missing = self._compute_missing(state)
            followup_count += 1
            state.questions_asked = followup_count

        state.is_complete = True
        return InterviewResult(
            state=state,
            conversation_history=state.conversation_history,
        )

    def _compute_missing(self, state: InterviewState) -> list[str]:
        missing = []
        if not state.bot_purpose:
            missing.append("bot_purpose")
        if not state.target_users:
            missing.append("target_users")
        if not state.primary_actions:
            missing.append("primary_actions")
        if state.needs_memory is None:
            missing.append("needs_memory")
        if state.needs_tools is None:
            missing.append("needs_tools")
        return missing

    def _generate_followup(
        self, state: InterviewState, missing: list[str]
    ) -> str:
        state_summary = self._summarize_state(state)
        missing_labels = ", ".join(
            _FIELD_LABELS.get(f, f) for f in missing
        )
        prompt = FOLLOWUP_PROMPT_TEMPLATE.format(
            state_summary=state_summary,
            missing_fields=missing_labels,
        )
        return self._llm.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            system=INTERVIEW_SYSTEM_PROMPT,
            temperature=0.4,
        ).strip()

    def _summarize_state(self, state: InterviewState) -> str:
        lines = [f"Beschreibung: {state.raw_initial_description}"]
        if state.bot_name:
            lines.append(f"Name: {state.bot_name}")
        if state.bot_purpose:
            lines.append(f"Zweck: {state.bot_purpose}")
        if state.target_users:
            lines.append(f"Zielgruppe: {state.target_users}")
        if state.primary_actions:
            lines.append(f"Aktionen: {', '.join(state.primary_actions)}")
        if state.needs_memory is not None:
            lines.append(f"Memory: {'ja' if state.needs_memory else 'nein'}")
        if state.needs_tools is not None:
            lines.append(f"Tools: {'ja' if state.needs_tools else 'nein'}")
        return "\n".join(lines)
