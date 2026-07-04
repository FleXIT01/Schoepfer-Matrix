import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .models import Job, JobStatus, PolicyBudget, Task, TaskResult, TaskStatus

class StateStore:
    """SQLite-based persistent state store for durable execution."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # busy_timeout: 30s um Lock-Fehler bei Last zu vermeiden
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    goal TEXT,
                    context TEXT,
                    status TEXT,
                    budget TEXT,
                    created_at REAL,
                    updated_at REAL
                );
                
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    task_type TEXT,
                    input_data TEXT,
                    dependencies TEXT,
                    status TEXT,
                    retries INTEGER,
                    result TEXT,
                    created_at REAL,
                    updated_at REAL,
                    started_at REAL,
                    finished_at REAL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    status_from TEXT,
                    status_to TEXT,
                    timestamp REAL,
                    details TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
            """)

    def _log_event(self, task_id: str, status_from: str, status_to: str, details: str = ""):
        # Kurze Write-Transaktion
        with self.conn:
            self.conn.execute(
                "INSERT INTO task_events (task_id, status_from, status_to, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                (task_id, status_from, status_to, time.time(), details)
            )

    def save_job(self, job: Job):
        now = time.time()
        if not job.created_at:
            job.created_at = now
        job.updated_at = now

        budget_dict = {
            "max_retries": job.budget.max_retries,
            "max_steps_per_job": job.budget.max_steps_per_job,
            "deadline_ts": job.budget.deadline_ts,
            "allowed_tools": job.budget.allowed_tools,
        }

        with self.conn:
            self.conn.execute("""
                INSERT INTO jobs (id, goal, context, status, budget, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    context=excluded.context,
                    updated_at=excluded.updated_at
            """, (
                job.id, job.goal, json.dumps(job.context, default=str), job.status.value,
                json.dumps(budget_dict, default=str), job.created_at, job.updated_at
            ))

            for task in job.tasks.values():
                self.save_task(job.id, task)

    def save_task(self, job_id: str, task: Task):
        now = time.time()
        if not task.created_at:
            task.created_at = now
        
        # Check if status changed to log event
        cursor = self.conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task.id,))
        row = cursor.fetchone()
        old_status = row["status"] if row else None

        task.updated_at = now
        res_dict = None
        if task.result:
            res_dict = {
                "status": task.result.status.value,
                "output": task.result.output,
                "artifacts": task.result.artifacts,
                "metrics": task.result.metrics,
                "error": task.result.error,
                "next_hint": task.result.next_hint
            }

        with self.conn:
            self.conn.execute("""
                INSERT INTO tasks (id, job_id, task_type, input_data, dependencies, status, retries, result, created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    retries=excluded.retries,
                    result=excluded.result,
                    updated_at=excluded.updated_at,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at
            """, (
                task.id, job_id, task.task_type, json.dumps(task.input_data, default=str),
                json.dumps(task.dependencies, default=str), task.status.value, task.retries,
                json.dumps(res_dict, default=str) if res_dict else None,
                task.created_at, task.updated_at, task.started_at, task.finished_at
            ))

        if old_status != task.status.value:
            self._log_event(task.id, old_status or "none", task.status.value, f"Task transitioned to {task.status.value}")

    def get_job(self, job_id: str) -> Optional[Job]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None

        budget_dict = json.loads(row["budget"])
        budget = PolicyBudget(
            max_retries=budget_dict.get("max_retries", 3),
            max_steps_per_job=budget_dict.get("max_steps_per_job", 15),
            deadline_ts=budget_dict.get("deadline_ts"),
            allowed_tools=budget_dict.get("allowed_tools", [])
        )

        job = Job(
            id=row["id"],
            goal=row["goal"],
            context=json.loads(row["context"]),
            status=JobStatus(row["status"]),
            budget=budget,
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

        cursor.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
        for trow in cursor.fetchall():
            res_dict = json.loads(trow["result"]) if trow["result"] else None
            result = None
            if res_dict:
                result = TaskResult(
                    status=TaskStatus(res_dict["status"]),
                    output=res_dict.get("output"),
                    artifacts=res_dict.get("artifacts", {}),
                    metrics=res_dict.get("metrics", {}),
                    error=res_dict.get("error"),
                    next_hint=res_dict.get("next_hint")
                )

            task = Task(
                id=trow["id"],
                task_type=trow["task_type"],
                input_data=json.loads(trow["input_data"]),
                dependencies=json.loads(trow["dependencies"]),
                status=TaskStatus(trow["status"]),
                retries=trow["retries"],
                result=result,
                created_at=trow["created_at"],
                updated_at=trow["updated_at"],
                started_at=trow["started_at"] if "started_at" in trow.keys() and trow["started_at"] is not None else 0.0,
                finished_at=trow["finished_at"] if "finished_at" in trow.keys() and trow["finished_at"] is not None else 0.0
            )
            job.tasks[task.id] = task

        return job
