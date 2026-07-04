import os
import sys
import time
import subprocess
import shutil
import logging
from pathlib import Path

# Fix import paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot1.generator.agent.workflow.store import StateStore
from bot1.generator.agent.workflow.models import Job, Task, TaskStatus, JobStatus
from bot1.generator.agent.workflow.router import JobRouter
from bot1.generator.agent.workflow.engine import WorkflowKernel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s')
logger = logging.getLogger("test_recovery")

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "output" / "test_state.db"

def setup_store():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    return StateStore(TEST_DB_PATH)

def test_idempotency(store: StateStore):
    logger.info("=== RUNNING: test_idempotency ===")
    
    # Simulate a job
    job = JobRouter.classify_and_route("suche infos idempotency")
    store.save_job(job)
    
    # Save the exact same job again
    store.save_job(job)
    
    # Fetch job and check
    fetched = store.get_job(job.id)
    assert fetched is not None
    assert len(fetched.tasks) == 2, "Job should still have exactly 2 tasks"
    
    # Save tasks multiple times
    task1 = list(job.tasks.values())[0]
    store.save_task(job.id, task1)
    store.save_task(job.id, task1)
    
    # Ensure task events weren't duplicated for no reason (status didn't change)
    cursor = store.conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM task_events WHERE task_id = ?", (task1.id,))
    count = cursor.fetchone()["c"]
    assert count == 1, f"Expected exactly 1 event (initial creation), got {count}"
    
    logger.info("✅ test_idempotency passed.\n")

def test_retry_logic(store: StateStore):
    logger.info("=== RUNNING: test_retry_logic ===")
    kernel = WorkflowKernel(store)
    
    job = JobRouter.classify_and_route("suche infos retry test")
    
    # Inject crash flag to force retries
    task1_id = list(job.tasks.keys())[0]
    job.tasks[task1_id].input_data["_crash_test"] = True
    
    # Set max_retries to 2 so we fail completely on the 3rd try
    job.budget.max_retries = 2
    store.save_job(job)
    
    kernel.execute_job(job.id)
    
    updated_job = store.get_job(job.id)
    assert updated_job.status == JobStatus.FAILED
    
    task1 = updated_job.tasks[task1_id]
    assert task1.status == TaskStatus.FAILED
    assert task1.retries == 2
    
    logger.info("✅ test_retry_logic passed.\n")

def test_terminal_state(store: StateStore):
    logger.info("=== RUNNING: test_terminal_state ===")
    kernel = WorkflowKernel(store)
    
    job = JobRouter.classify_and_route("suche infos terminal state")
    store.save_job(job)
    
    # Execute normal
    kernel.execute_job(job.id)
    
    updated_job = store.get_job(job.id)
    assert updated_job.status == JobStatus.COMPLETED
    
    # Now execute again
    kernel.execute_job(job.id)
    
    # Check that events didn't grow, meaning nothing was done
    cursor = store.conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM task_events")
    count_after_first = cursor.fetchone()["c"]
    
    kernel.execute_job(job.id)
    
    cursor.execute("SELECT COUNT(*) as c FROM task_events")
    count_after_second = cursor.fetchone()["c"]
    
    assert count_after_first == count_after_second, "Terminal job should not spawn new events."
    logger.info("✅ test_terminal_state passed.\n")

def test_crash_recovery(store: StateStore):
    logger.info("=== RUNNING: test_crash_recovery (via subprocess) ===")
    
    job = JobRouter.classify_and_route("suche infos crash test")
    
    # Setze den ersten Task manuell auf RUNNING um einen Crash während der Ausführung zu simulieren
    task1_id = list(job.tasks.keys())[0]
    job.tasks[task1_id].status = TaskStatus.RUNNING
    store.save_job(job)
    
    # Starte den Kernel regulär – er muss das RUNNING detektieren und fixen
    kernel = WorkflowKernel(store)
    logger.info("Starte Kernel zur Recovery...")
    kernel.execute_job(job.id)
    
    recovered_job = store.get_job(job.id)
    assert recovered_job.status == JobStatus.COMPLETED
    
    task1 = recovered_job.tasks[task1_id]
    assert task1.status == TaskStatus.COMPLETED
    
    cursor = store.conn.cursor()
    cursor.execute("SELECT status_to FROM task_events WHERE task_id = ? ORDER BY id ASC", (task1_id,))
    events = [row["status_to"] for row in cursor.fetchall()]
    
    assert "ready_for_recovery" in events, "Task should have transitioned to READY_FOR_RECOVERY"
    assert events[-1] == "completed", "Task should have ultimately COMPLETED"
    
    logger.info("✅ test_crash_recovery passed.\n")

if __name__ == "__main__":
    logger.info("Starting Workflow Kernel Validation Suite...")
    main_store = setup_store()
    try:
        test_idempotency(main_store)
        test_retry_logic(main_store)
        test_terminal_state(main_store)
        test_crash_recovery(main_store)
        logger.info("🎉 All tests passed successfully!")
    finally:
        main_store.conn.close()
