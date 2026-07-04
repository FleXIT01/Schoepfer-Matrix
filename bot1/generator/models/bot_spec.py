from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BotType(str, Enum):
    CUSTOMER_SUPPORT = "customer_support"
    DATA_EXTRACTION = "data_extraction"
    TASK_AUTOMATION = "task_automation"
    QA_ASSISTANT = "qa_assistant"
    CODING_ASSISTANT = "coding_assistant"
    DOCUMENT_PROCESSOR = "document_processor"
    CUSTOM = "custom"


class MemoryStrategy(str, Enum):
    NONE = "none"
    IN_SESSION = "in_session"
    PERSISTENT_JSON = "persistent_json"
    PERSISTENT_DB = "persistent_db"


class LLMProviderSpec(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2048, ge=128, le=8192)


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    returns: str = "string"


class SchemaField(BaseModel):
    name: str
    type: str
    required: bool = True
    description: str = ""


class InputSchemaSpec(BaseModel):
    fields: list[SchemaField] = Field(default_factory=list)


class OutputSchemaSpec(BaseModel):
    fields: list[SchemaField] = Field(default_factory=list)


class StateSchemaSpec(BaseModel):
    fields: list[SchemaField] = Field(default_factory=list)


class ExampleTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ExampleConversation(BaseModel):
    description: str
    turns: list[ExampleTurn] = Field(default_factory=list)


class BotSpec(BaseModel):
    # Identity
    name: str = "UnbenanntBot"
    description: str = "# TODO: Beschreibung fehlt"
    bot_type: BotType = BotType.CUSTOM
    language: str = "de"

    # Block 1 — Anforderungen
    use_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    target_users: str = "# TODO: Zielgruppe nicht spezifiziert"

    # Block 2 — Architektur
    llm: LLMProviderSpec = Field(default_factory=LLMProviderSpec)
    memory_strategy: MemoryStrategy = MemoryStrategy.IN_SESSION
    tools: list[ToolSpec] = Field(default_factory=list)
    integration_points: list[str] = Field(default_factory=list)

    # Block 3 — Prompt-Paket
    system_prompt: str = "# TODO: System-Prompt generieren"
    developer_notes: str = "# TODO: Entwickler-Hinweise"
    example_conversations: list[ExampleConversation] = Field(default_factory=list)

    # Block 4 — Schemas
    input_schema: InputSchemaSpec = Field(default_factory=InputSchemaSpec)
    output_schema: OutputSchemaSpec = Field(default_factory=OutputSchemaSpec)
    state_schema: StateSchemaSpec = Field(default_factory=StateSchemaSpec)

    # Metadata
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    generated_at: str = ""

    def python_identifier(self) -> str:
        """Returns a valid Python identifier derived from the bot name."""
        import re
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", self.name)
        if slug and slug[0].isdigit():
            slug = "bot_" + slug
        return slug or "UnbenanntBot"
