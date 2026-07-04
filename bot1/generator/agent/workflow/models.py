from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_FOR_APPROVAL = "waiting_for_approval"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    READY_FOR_RECOVERY = "ready_for_recovery"

@dataclass
class PolicyBudget:
    max_retries: int = 3
    max_steps_per_job: int = 15
    deadline_ts: float | None = None
    allowed_tools: list[str] = field(default_factory=list)

@dataclass
class TaskResult:
    status: TaskStatus
    output: Any = None
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    next_hint: str | None = None

@dataclass
class Task:
    id: str
    task_type: str
    input_data: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    result: TaskResult | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0

@dataclass
class Job:
    id: str
    goal: str
    context: dict[str, Any] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    budget: PolicyBudget = field(default_factory=PolicyBudget)
    created_at: float = 0.0
    updated_at: float = 0.0
