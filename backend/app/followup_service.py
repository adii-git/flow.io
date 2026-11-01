"""Follow-ups: continue a finished task in the same session.

A follow-up is stored as a requirement (every step reads requirements, image prompts included),
the previous answer is kept as context so text steps can revise it, and any capability the
follow-up clearly asks for ("now write an Instagram caption") becomes a new step before
validation. The caller then plans and runs the task again.
"""
import uuid
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .models import ContextItem, Result, Subtask, Task
from .understanding import counts, detect, step_text

FOLLOW_UP = "Follow-up"
PREVIOUS = "Previous answer"
PREFIX = "Change requested by the user (apply it to the previous answer): "
MAX_FOLLOW_UPS = 20
MAX_PREVIOUS_CHARS = 6000


def history(db: Session, task: Task) -> list[dict]:
    rows = db.scalars(select(ContextItem).where(ContextItem.task_id == task.id, ContextItem.label == FOLLOW_UP)
                      .order_by(ContextItem.created_at)).all()
    return [{"id": str(r.id), "message": r.content.removeprefix(PREFIX), "created_at": r.created_at.isoformat()} for r in rows]


def _previous_answer(db: Session, task: Task) -> str:
    r = db.scalar(select(Result).where(Result.task_id == task.id).order_by(Result.created_at.desc()))
    if not r:
        return ""
    p = r.payload or {}
    text = p.get("markdown") or "\n\n".join(f"## {s.get('label')}\n{s.get('text', '')}" for s in p.get("sections", []))
    if p.get("images"):
        text += f"\n\n[The previous answer included {len(p['images'])} image(s).]"
    return text[:MAX_PREVIOUS_CHARS]


def add_follow_up(db: Session, task: Task, message: str) -> list[str]:
    """Records the follow-up and returns the capabilities of any steps it added."""
    message = message.strip()
    if not message:
        raise HTTPException(422, "Type what you want to change or add.")
    if task.status == "running":
        raise HTTPException(409, "This task is still running. Wait for it to finish, then send your message.")
    if task.status == "draft":
        raise HTTPException(409, "Run this task first, then continue it.")
    if len(history(db, task)) >= MAX_FOLLOW_UPS:
        raise HTTPException(409, "This task has reached its follow-up limit. Start a new task to keep going.")

    prev = _previous_answer(db, task)
    db.execute(delete(ContextItem).where(ContextItem.task_id == task.id, ContextItem.label == PREVIOUS))
    if prev:
        # kind "output" with no producing step: survives reset_run and reaches the text steps that revise it
        db.add(ContextItem(task_id=task.id, kind="output", label=PREVIOUS, content=prev))
    db.add(ContextItem(task_id=task.id, kind="requirement", label=FOLLOW_UP, content=PREFIX + message))

    subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)))
    have = {s.capability for s in subs}
    said = counts(message)
    if said:  # "make it 3 photos" / "make it 800 words" updates the numbers every step reads
        task.plan = {**(task.plan or {}), "counts": {**((task.plan or {}).get("counts") or {}), **said}}
        for s in subs:
            if s.capability in ("writing", "image_generation"):
                s.description = step_text(s.capability, task.plan["counts"])
    new_caps = [c for c in detect(message) if c not in have]
    insert_steps(db, task, subs, new_caps)
    db.flush()
    return new_caps


def insert_steps(db: Session, task: Task, subs: list[Subtask], new_caps: list[str]) -> list[Subtask]:
    """Adds steps for capabilities the task is missing, after the last work step and before the
    check, which then also waits for them. Used by follow-ups and by the check itself when it
    finds a whole part of the ask missing. Returns the new (unrouted, pending) steps."""
    if not new_caps:
        return []
    c = (task.plan or {}).get("counts") or {}
    val = next((s for s in subs if s.capability == "validation"), None)
    work = [s for s in subs if s.capability != "validation"]
    after = [str(work[-1].id)] if work else []
    pos = val.position if val else len(subs)
    added = []
    for cap in new_caps:
        sub = Subtask(id=uuid.uuid4(), task_id=task.id, position=pos, capability=cap, description=step_text(cap, c),
                      depends_on=after, status="pending")
        db.add(sub)
        added.append(sub)
        after, pos = [str(sub.id)], pos + 1
    if val:
        val.position = pos
        val.depends_on = [*(val.depends_on or []), *(str(a.id) for a in added)]
    caps = list((task.plan or {}).get("capabilities", []))
    task.plan = {**(task.plan or {}), "capabilities": [*caps, *new_caps]}
    db.flush()
    return added
