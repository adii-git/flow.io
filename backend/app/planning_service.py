from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from . import replanner
from .config import get_settings
from .context_manager import build_package
from .models import ContextItem, ContextTransfer, Result, Subtask, Task, TaskEvent, Tool, ToolConnection, User
from .routing import route_step


def reset_run(db: Session, task: Task) -> None:
    """Clears everything a previous run produced, keeping the objective, requirements and files."""
    sub_ids = [s.id for s in db.scalars(select(Subtask).where(Subtask.task_id == task.id))]
    if sub_ids:
        db.execute(delete(ContextItem).where(ContextItem.task_id == task.id, ContextItem.kind.in_(["output", "research", "decision"]),
                                             ContextItem.subtask_id.in_(sub_ids)))
    db.execute(delete(ContextItem).where(ContextItem.task_id == task.id, ContextItem.label == "Validator feedback"))
    db.execute(delete(ContextTransfer).where(ContextTransfer.task_id == task.id))
    db.execute(delete(Result).where(Result.task_id == task.id))
    db.execute(delete(TaskEvent).where(TaskEvent.task_id == task.id))
    for s in db.scalars(select(Subtask).where(Subtask.task_id == task.id)):
        s.output, s.status = None, "pending"
    task.error = None


def route_new(db: Session, task: Task, new_subs: list[Subtask], priority: str = "balanced") -> list[Subtask]:
    """Routes steps added mid-run (the check found a part missing). Returns the ones that got a tool;
    a step with no usable tool is skipped with a note instead of failing the run."""
    demo = get_settings().execution_mode == "demo"
    tools = list(db.scalars(select(Tool).where(Tool.availability != "retired")))
    have = set(db.scalars(select(ToolConnection.provider).where(ToolConnection.user_id == task.user_id)))
    subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)))
    ok = []
    for sub in new_subs:
        d = route_step(sub.capability, tools, ready_providers=have, demo=demo, priority=priority)
        if d.tool_id is None:
            sub.status, sub.tool_id, sub.routing = "skipped", None, {"skipped": True, "note": d.reasons[0]}
            continue
        tool = next(t for t in tools if t.id == d.tool_id)
        pkg = build_package(db, task, sub, subs, tool, persist=False)
        sub.tool_id, sub.status = d.tool_id, "planned"
        sub.routing = {"tool_id": d.tool_id, "tool_name": tool.name, "confidence": d.confidence, "reasons": d.reasons,
                       "alternatives": d.alternatives, "context_items": len(pkg.sent), "priority": priority}
        ok.append(sub)
    db.flush()
    return ok


def plan_task(db: Session, user: User, task: Task, priority: str = "balanced") -> dict:
    demo = get_settings().execution_mode == "demo"
    reset_run(db, task)
    tools = list(db.scalars(select(Tool).where(Tool.availability != "retired")))
    have = set(db.scalars(select(ToolConnection.provider).where(ToolConnection.user_id == user.id)))
    subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)))
    by_id = {str(s.id): s for s in subs}
    items = list(db.scalars(select(ContextItem).where(ContextItem.task_id == task.id)))
    need = sum(len(i.content) for i in items if i.kind in ("objective", "file", "requirement")) // 4
    has_files = any(i.kind == "file" for i in items)
    chosen: dict[str, str] = {}
    notes, blockers = [], {}
    for sub in subs:
        deps = [by_id[d] for d in sub.depends_on if d in by_id and by_id[d].capability != "validation"]
        avoid = chosen.get(str(max(deps, key=lambda s: s.position).id)) if sub.capability == "validation" and deps else None
        d = route_step(sub.capability, tools, ready_providers=have, demo=demo, need_tokens=need, needs_files=has_files and sub.capability != "web_research",
                       priority=priority, avoid_tool=avoid, fast_step=sub.capability == "validation")
        if d.tool_id is None:
            adj = replanner.adjust(sub.capability, d.reasons[0])
            if adj["action"] == "abort":
                raise HTTPException(422, d.reasons[0])
            sub.status, sub.tool_id, sub.routing = "skipped", None, {"skipped": True, "note": adj["note"]}
            notes.append(adj["note"])
            continue
        chosen[str(sub.id)] = d.tool_id
        sub.tool_id, sub.status = d.tool_id, "planned"
        tool = next(t for t in tools if t.id == d.tool_id)
        pkg = build_package(db, task, sub, subs, tool, persist=False)
        sub.routing = {"tool_id": d.tool_id, "tool_name": tool.name, "confidence": d.confidence, "reasons": d.reasons,
                       "alternatives": d.alternatives, "context_items": len(pkg.sent), "priority": priority}
        for b in d.blockers:
            blockers.setdefault(b, []).append(tool.name)
    task.status = "planned"
    db.commit()
    return {"blockers": [{"provider": p, "tools": sorted(set(n))} for p, n in blockers.items()], "notes": notes}
