import logging
import time
from typing import Optional

from .adapters import BaseAdapter, BotGenerationAdapter, NoopAdapter, ResearchAdapter, ReviewAdapter
from .models import Job, JobStatus, Task, TaskStatus
from .policy import PolicyEngine
from .store import StateStore

logger = logging.getLogger(__name__)

class WorkflowKernel:
    """Der Kern-Executor des Multi-Agent Systems."""
    
    def __init__(self, store: StateStore):
        self.store = store
        self.adapters: dict[str, BaseAdapter] = {
            "research": ResearchAdapter(),
            "bot_generation": BotGenerationAdapter(),
            "review": ReviewAdapter(),
            "noop": NoopAdapter(),
        }

    def execute_job(self, job_id: str):
        job = self.store.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} nicht gefunden.")
            return

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            logger.info(f"Job {job_id} ist bereits beendet ({job.status.value}).")
            return

        if not PolicyEngine.check_job_can_run(job):
            logger.warning(f"Job {job_id} hat sein Budget überschritten oder die Deadline erreicht.")
            job.status = JobStatus.FAILED
            self.store.save_job(job)
            return

        job.status = JobStatus.RUNNING
        self.store.save_job(job)

        # Recovery Phase: Detect stale RUNNING tasks (assume single-process -> if it's RUNNING now, it crashed)
        for t_id, t in job.tasks.items():
            if t.status == TaskStatus.RUNNING:
                logger.warning(f"Task {t.id} war noch im Status RUNNING. Setze auf READY_FOR_RECOVERY zurück.")
                t.status = TaskStatus.READY_FOR_RECOVERY
                self.store.save_task(job.id, t)

        while True:
            # Finde ausführbare Tasks
            pending_tasks = self._get_executable_tasks(job)
            
            if not pending_tasks:
                # Keine ausführbaren Tasks mehr. Ist der Job fertig?
                all_done = all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in job.tasks.values())
                any_failed = any(t.status == TaskStatus.FAILED for t in job.tasks.values())
                any_waiting = any(t.status == TaskStatus.WAITING_FOR_APPROVAL for t in job.tasks.values())
                
                if any_waiting:
                    logger.info(f"Job {job_id} pausiert (wartet auf Human Approval).")
                    job.status = JobStatus.WAITING_FOR_APPROVAL
                elif all_done:
                    job.status = JobStatus.FAILED if any_failed else JobStatus.COMPLETED
                    logger.info(f"Job {job_id} abgeschlossen mit Status: {job.status.value}")
                else:
                    # Es gibt noch Tasks, aber Dependencies blockieren (Deadlock)
                    logger.error(f"Job {job_id} blockiert! Zyklische Abhängigkeit oder unlösbarer Status.")
                    job.status = JobStatus.FAILED
                    
                self.store.save_job(job)
                break

            # Führe einen Task aus (sequenziell für Phase 1)
            current_task = pending_tasks[0]
            self._execute_task(job, current_task)

    def _get_executable_tasks(self, job: Job) -> list[Task]:
        executable = []
        for task in job.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.RETRY, TaskStatus.READY_FOR_RECOVERY):
                deps_met = all(job.tasks[d].status == TaskStatus.COMPLETED for d in task.dependencies)
                if deps_met:
                    executable.append(task)
        return executable

    def _execute_task(self, job: Job, task: Task):
        adapter = self.adapters.get(task.task_type, self.adapters["noop"])
        
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self.store.save_task(job.id, task)
        
        try:
            # Hier könnten wir Kontext aus dem Job mitgeben, komprimiert.
            context = job.context
            result = adapter.run(task, context)
            
            task.result = result
            task.status = result.status
            
            if task.status == TaskStatus.FAILED and PolicyEngine.can_retry_task(job, task):
                logger.warning(f"Task {task.id} fehlgeschlagen. Retry markiert.")
                task.status = TaskStatus.RETRY
                task.retries += 1
            elif task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.finished_at = time.time()
                
        except Exception as e:
            logger.exception(f"Unerwarteter Fehler bei Task {task.id}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            if PolicyEngine.can_retry_task(job, task):
                task.status = TaskStatus.RETRY
                task.retries += 1
            else:
                task.finished_at = time.time()
                
        self.store.save_task(job.id, task)
