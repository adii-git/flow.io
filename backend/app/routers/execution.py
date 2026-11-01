import json
import time
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .. import followup_service, planning_service, task_service as svc
from ..config import get_settings
from ..db import get_db, session_scope
from ..deps import current_user
from ..dispatch import dispatch
from ..models import ContextTransfer, Result, Subtask, Task, TaskEvent, Tool, ToolConnection, User
from ..ratelimit import rate_limit
from ..repositories import audit
from ..schemas import TaskDetail

router = APIRouter(prefix="/api")


class PlanIn(BaseModel):
    priority: Literal["balanced", "quality", "cheap", "fast"] = "balanced"


class PlanOut(BaseModel):
    task: TaskDetail
    blockers: list[dict]
    notes: list[str]


@router.post("/tasks/{task_id}/plan", response_model=PlanOut)
def plan(task_id: uuid.UUID, body: PlanIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = svc.get_owned(db, user, task_id)
    if t.status == "running":
        raise HTTPException(409, "This task is running. Wait for it to finish before planning again.")
    out = planning_service.plan_task(db, user, t, (body or PlanIn()).priority)
    return {"task": svc.detail(db, t), **out}


def _missing_keys(db: Session, user: User, task: Task) -> list[str]:
    if get_settings().execution_mode == "demo":
        return []
    have = set(db.scalars(select(ToolConnection.provider).where(ToolConnection.user_id == user.id)))
    need = set()
    for s in db.scalars(select(Subtask).where(Subtask.task_id == task.id, Subtask.status == "planned")):
        tool = db.get(Tool, s.tool_id) if s.tool_id else None
        if tool and tool.requires_key and tool.provider not in have:
            need.add(tool.provider)
    return sorted(need)


@router.post("/tasks/{task_id}/execute", status_code=202, dependencies=[Depends(rate_limit("execute", 20))])
def execute(task_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = svc.get_owned(db, user, task_id)
    if t.status in ("draft",):
        raise HTTPException(409, "Plan this task first.")
    _start_run(db, user, t, request)
    return {"status": "running"}


def _start_run(db: Session, user: User, t: Task, request: Request) -> None:
    missing = _missing_keys(db, user, t)
    if missing:
        raise HTTPException(409, f"Add a key for {', '.join(missing)} in Tools, then run the task.")
    # Claim the run atomically so a double click cannot start two.
    claimed = db.execute(update(Task).where(Task.id == t.id, Task.status != "running").values(status="running")).rowcount
    if not claimed:
        raise HTTPException(409, "This task is already running.")
    db.commit()
    db.refresh(t)
    planning_service.reset_run(db, t)
    for s in db.scalars(select(Subtask).where(Subtask.task_id == t.id)):
        s.status = "skipped" if (s.routing or {}).get("skipped") else "planned"
    t.status = "running"
    audit(db, "task.execute", user.id, request.client.host if request.client else "", task_id=str(t.id))
    db.commit()
    dispatch(t.id)


class FollowUpIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    priority: Literal["balanced", "quality", "cheap", "fast"] = "balanced"


@router.get("/tasks/{task_id}/followups")
def followups(task_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return followup_service.history(db, svc.get_owned(db, user, task_id))


@router.post("/tasks/{task_id}/followup", status_code=202, dependencies=[Depends(rate_limit("execute", 20))])
def followup(task_id: uuid.UUID, body: FollowUpIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Continue the task: keep its history and previous answer, apply the new instruction, run again."""
    t = svc.get_owned(db, user, task_id)
    added = followup_service.add_follow_up(db, t, body.message)
    out = planning_service.plan_task(db, user, t, body.priority)  # re-route, including any new step
    if out["blockers"]:
        need = ", ".join(b["provider"] for b in out["blockers"])
        raise HTTPException(409, f"Your message is saved. Add a key for {need} in Tools, then press Run again.")
    _start_run(db, user, t, request)
    return {"status": "running", "added_steps": added, "notes": out["notes"]}


def _sse(e: TaskEvent) -> str:
    return f"id: {e.id}\nevent: {e.type}\ndata: {json.dumps({**e.payload, 'type': e.type})}\n\n"


@router.get("/tasks/{task_id}/stream")
def stream(task_id: uuid.UUID, last_event_id: str | None = Header(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.get_owned(db, user, task_id)
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    def gen():
        last, beat, end = start, time.time(), time.time() + 600
        while time.time() < end:
            with session_scope() as s:
                evs = list(s.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.id > last).order_by(TaskEvent.id).limit(100)))
                row = s.get(Task, task_id)
                status = row.status if row else "gone"
            for e in evs:
                last = e.id
                yield _sse(e)
            if status != "running" and not evs:
                return
            if not evs:
                if time.time() - beat > 15:
                    beat = time.time(); yield ": keep-alive\n\n"
                time.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/tasks/{task_id}/result")
def result(task_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.get_owned(db, user, task_id)
    r = db.scalar(select(Result).where(Result.task_id == task_id).order_by(Result.created_at.desc()))
    if not r:
        raise HTTPException(404, "There is no result yet. Run the task first.")
    return r.payload


@router.get("/context/{task_id}")
def context(task_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.get_owned(db, user, task_id)
    subs = {s.id: s for s in db.scalars(select(Subtask).where(Subtask.task_id == task_id))}
    rows = db.scalars(select(ContextTransfer).where(ContextTransfer.task_id == task_id).order_by(ContextTransfer.created_at)).all()
    return [{"subtask_id": str(r.to_subtask_id), "step": subs[r.to_subtask_id].capability if r.to_subtask_id in subs else None,
             "tool": subs[r.to_subtask_id].tool_id if r.to_subtask_id in subs else None, "sent": r.sent, "withheld": r.withheld} for r in rows]
