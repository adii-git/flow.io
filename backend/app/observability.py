"""Usage totals for users; per-run and per-provider metrics for admins."""
from collections import defaultdict
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ContextTransfer, Execution, Task, TaskEvent, Usage, User, now


def _pct(xs: list[int], p: float) -> int | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def user_usage(db: Session, user: User, days: int = 30) -> dict:
    since = now() - timedelta(days=days)
    rows = db.execute(select(Execution.tool_id, Usage.tokens_in, Usage.tokens_out)
                      .join(Usage, Usage.execution_id == Execution.id)
                      .where(Usage.user_id == user.id, Usage.created_at >= since)).all()
    by: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0})
    for tool, i, o in rows:
        b = by[tool or "unknown"]
        b["calls"] += 1; b["tokens_in"] += i; b["tokens_out"] += o
    tasks = len(db.scalars(select(Task.id).where(Task.user_id == user.id, Task.created_at >= since)).all())
    return {"days": days, "tasks": tasks, "calls": sum(b["calls"] for b in by.values()),
            "tokens_in": sum(b["tokens_in"] for b in by.values()), "tokens_out": sum(b["tokens_out"] for b in by.values()),
            "by_tool": [{"tool": k, **v} for k, v in sorted(by.items())],
            "note": "Token counts come from providers. Cost is not calculated yet."}


def admin_metrics(db: Session, limit: int = 50) -> dict:
    tasks = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit)).all()
    runs = []
    for t in tasks:
        ex = db.scalars(select(Execution).where(Execution.task_id == t.id)).all()
        ev = db.scalars(select(TaskEvent).where(TaskEvent.task_id == t.id).order_by(TaskEvent.id)).all()
        started = next((e.created_at for e in ev if e.type == "task.started"), None)
        ended = next((e.created_at for e in reversed(ev) if e.type in ("task.done", "task.failed")), None)
        ctx = sum(s["chars"] for tr in db.scalars(select(ContextTransfer).where(ContextTransfer.task_id == t.id)) for s in tr.sent)
        dur = int((ended - started).total_seconds() * 1000) if started and ended else None
        runs.append({"task_id": str(t.id), "status": t.status, "duration_ms": dur, "tools": sorted({e.tool_id for e in ex if e.tool_id}),
                     "tokens_in": sum(e.tokens_in for e in ex), "tokens_out": sum(e.tokens_out for e in ex),
                     "retries": sum(e.retries for e in ex), "failures": sum(1 for e in ex if e.status == "failed"), "context_chars": ctx})
    lat: dict[str, list[int]] = defaultdict(list)
    for tool, ms in db.execute(select(Execution.tool_id, Execution.latency_ms).where(Execution.status == "done", Execution.latency_ms.is_not(None))):
        lat[tool or "unknown"].append(ms)
    return {"runs": runs, "provider_latency_ms": [{"tool": k, "calls": len(v), "p50": _pct(v, .5), "p95": _pct(v, .95)} for k, v in sorted(lat.items())]}
