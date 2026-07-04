import uuid
from typing import Optional
from .models import Job, JobStatus, Task, TaskStatus

class JobRouter:
    """Deterministischer, regelbasierter Router für Workflows."""
    
    @staticmethod
    def classify_and_route(goal: str, spec: Optional[dict] = None) -> Job:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, goal=goal)
        
        # 1. Fall: Reine Recherche
        if "suche" in goal.lower() or "recherche" in goal.lower():
            t1 = Task(id=f"{job_id}_t1", task_type="research", input_data={"query": goal})
            t2 = Task(id=f"{job_id}_t2", task_type="review", input_data={"content": "research_report"}, dependencies=[t1.id])
            
            job.tasks = {t1.id: t1, t2.id: t2}
            
        # 2. Fall: Bot-Generierung
        elif spec or "bot" in goal.lower() or "app" in goal.lower():
            # Sequenzieller Flow: Research -> BotGeneration -> Review
            t1 = Task(id=f"{job_id}_t1", task_type="research", input_data={"query": goal})
            t2 = Task(id=f"{job_id}_t2", task_type="bot_generation", input_data={"spec": spec or {}}, dependencies=[t1.id])
            t3 = Task(id=f"{job_id}_t3", task_type="review", input_data={"content": "bot_code"}, dependencies=[t2.id])
            
            job.tasks = {t1.id: t1, t2.id: t2, t3.id: t3}
            
        # 3. Fallback
        else:
            t1 = Task(id=f"{job_id}_t1", task_type="noop", input_data={"query": goal})
            job.tasks = {t1.id: t1}
            
        return job
