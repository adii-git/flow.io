import uuid
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import ContextItem, Execution, Project, Subtask, Task, User
from .repositories import audit
from . import ai_understanding
from .planner import build_steps
from .understanding import LABELS, STEP_TEXT, step_text, understand


def _owned_project(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id and not db.scalar(select(Project.id).where(Project.id == project_id, Project.user_id == user.id)):
        raise HTTPException(404, "That project doesn't exist. Pick another or create the task without one.")


def create_task(db: Session, user: User, objective: str, project_id: uuid.UUID | None, ip: str, files: list | None = None) -> Task:
    _owned_project(db, user, project_id)
    u = ai_understanding.refine(db, user.id, objective, understand(objective))
    task = Task(id=uuid.uuid4(), user_id=user.id, project_id=project_id, objective=objective.strip(),
                status="draft", plan=u.to_dict())
    db.add(task)
    db.flush()
    spec = build_steps(u.capabilities)
    subs = [Subtask(id=uuid.uuid4(), task_id=task.id, position=i, capability=st["capability"],
                    description=step_text(st["capability"], u.counts))
            for i, st in enumerate(spec)]
    for sub, st in zip(subs, spec):
        sub.depends_on = [str(subs[d].id) for d in st["deps"]]
        db.add(sub)
    for r in u.requirements:
        db.add(ContextItem(task_id=task.id, kind="requirement", content=r, label="Requirement"))
    db.add(ContextItem(task_id=task.id, kind="objective", content=task.objective, label="Your objective"))
    for f in files or []:
        f.task_id = task.id
        db.add(ContextItem(task_id=task.id, kind="file", content=f.excerpt, label=f.filename))
    audit(db, "task.create", user.id, ip, task_id=str(task.id))
    db.commit()
    return task


def get_owned(db: Session, user: User, task_id: uuid.UUID) -> Task:
    t = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not t:  # 404, not 403: don't reveal that someone else's task exists
        raise HTTPException(404, "That task doesn't exist or isn't yours.")
    return t


def detail(db: Session, task: Task) -> dict:
    subs = db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)).all()
    ctx = db.scalar(select(func.count()).select_from(ContextItem).where(ContextItem.task_id == task.id)) or 0
    return {
        "id": task.id, "objective": task.objective, "status": task.status, "project_id": task.project_id,
        "plan": task.plan, "created_at": task.created_at, "context_count": ctx,
        "tools_used": sorted(set(db.scalars(select(Execution.tool_id).where(Execution.task_id == task.id, Execution.status == "done")))),
        "subtasks": [{"id": s.id, "position": s.position, "capability": s.capability, "label": LABELS[s.capability],
                      "description": s.description, "tool_id": s.tool_id, "status": s.status,
                      "depends_on": s.depends_on, "routing": s.routing,
                      "output_preview": ((s.output or {}).get("text") or "")[:240] or None} for s in subs],
        "error": task.error,
    }
