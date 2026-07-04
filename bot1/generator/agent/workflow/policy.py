import time
from .models import Job, JobStatus, Task, TaskStatus

class PolicyEngine:
    """Enforces guardrails, timeouts, and iteration limits for durable execution."""

    @staticmethod
    def check_job_can_run(job: Job) -> bool:
        """Prüft, ob der Job laut Budget noch laufen darf."""
        if job.budget.deadline_ts and time.time() > job.budget.deadline_ts:
            return False
            
        completed_tasks = sum(1 for t in job.tasks.values() if t.status == TaskStatus.COMPLETED)
        if completed_tasks >= job.budget.max_steps_per_job:
            return False
            
        return True

    @staticmethod
    def can_retry_task(job: Job, task: Task) -> bool:
        """Prüft, ob der Task noch einmal probiert werden darf."""
        if task.retries >= job.budget.max_retries:
            return False
        return True
