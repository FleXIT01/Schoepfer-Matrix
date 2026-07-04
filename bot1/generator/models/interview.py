from __future__ import annotations

from pydantic import BaseModel, Field


class InterviewState(BaseModel):
    raw_initial_description: str = ""

    # Inferred/confirmed fields
    bot_name: str | None = None
    bot_purpose: str | None = None
    target_users: str | None = None
    primary_actions: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    needs_memory: bool | None = None
    memory_duration: str | None = None  # "session" | "permanent"
    needs_tools: bool | None = None
    tool_descriptions: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    language_preference: str | None = None
    use_cases: list[str] = Field(default_factory=list)
    error_scenarios: list[str] = Field(default_factory=list)

    # Interview tracking
    questions_asked: int = 0
    conversation_history: list[dict] = Field(default_factory=list)
    is_complete: bool = False
