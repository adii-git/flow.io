"""Execution engine: dependency-ordered state graph with parallel, retry, fallback, conditional (revision) and skip edges."""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from . import adapters as adp, replanner
from .adapters import FatalError, RetryableError
from .config import get_settings
from .context_manager import LABEL, build_package
from .db import session_scope
from .events import emit
from .models import (ContextItem, Execution, Result, Subtask, Task, Tool, ToolConnection, Usage, now)
from .repositories import audit
from .results import build_result
from .security import decrypt_secret

log = logging.getLogger("conduit.executor")
sleep = time.sleep
KIND_FOR = {"web_research": "research", "long_context_documents": "research", "reasoning": "decision"}
MAX_REVISIONS = 1


def _api_key(db: Session, user_id, tool: Tool, demo: bool) -> str | None:
    if demo or not tool.requires_key:
        return None
    row = db.scalar(select(ToolConnection).where(ToolConnection.user_id == user_id, ToolConnection.provider == tool.provider))
    if not row:
        raise FatalError(f"no {tool.provider} key is saved")
    return decrypt_secret(row.encrypted_key)


def _chain(db: Session, user_id, sub: Subtask, demo: bool) -> list[Tool]:
    r = sub.routing or {}
    have = set(db.scalars(select(ToolConnection.provider).where(ToolConnection.user_id == user_id)))
    out = []
    for i, tid in enumerate([r.get("tool_id"), *r.get("alternatives", [])]):
        t = db.get(Tool, tid) if tid else None
        if t and t.availability == "available" and (i == 0 or demo or not t.requires_key or t.provider in have):
            out.append(t)
    return out


# Capabilities whose text the user should watch type out. Validation returns a JSON
# verdict, and image/search steps have no prose, so those stream nothing.
STREAM_CAPS = {"reasoning", "writing", "long_context_documents", "code_generation", "web_research", "file_processing", "code_execution"}
STREAM_FLUSH_CHARS = 60  # batch deltas into one event per ~60 chars to avoid flooding the event log


def _stream_tokens(db: Session, task_id, sub_id, adapter, pkg, tool, key, capability) -> None:
    """Emit step.token events as the model types, for the live typing effect.

    Best-effort only: the authoritative result still comes from adapter.run() right after.
    Any failure here is swallowed — a broken stream must never fail the step, only skip
    the preview. Non-streaming adapters (images, search) are skipped entirely.
    """
    if not getattr(adapter, "streams", False) or capability not in STREAM_CAPS:
        return
    try:
        buf, total, seq = "", 0, 0
        for delta in adapter.stream(pkg, tool, key, capability):
            if not delta:
                continue
            buf += delta
            total += len(delta)
            if total > 20_000:  # a safety cap so a runaway stream can't bloat the log
                break
            if len(buf) >= STREAM_FLUSH_CHARS:
                emit(db, task_id, "step.token", buf, subtask_id=str(sub_id), seq=seq)
                db.commit()
                buf, seq = "", seq + 1
        if buf:
            emit(db, task_id, "step.token", buf, subtask_id=str(sub_id), seq=seq)
            db.commit()
    except Exception:  # never let the preview break the real run
        log.debug("token stream failed for %s; falling back to run()", sub_id, exc_info=True)


def run_step(task_id, sub_id) -> dict:
    """Runs one step with retries and fallbacks. Returns {ok, error}. Uses its own short sessions."""
    s = get_settings()
    demo = s.execution_mode == "demo"
    with session_scope() as db:
        task, sub = db.get(Task, task_id), db.get(Subtask, sub_id)
        subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task_id).order_by(Subtask.position)))
        label, chain = LABEL.get(sub.capability, sub.capability), _chain(db, task.user_id, sub, demo)
        sub.status = "running"
        emit(db, task_id, "step.started", f"{label} is starting" + (f" with {chain[0].name}." if chain else "."), subtask_id=str(sub_id))
        db.commit()
        last_err = "no tool was available"
        for ti, tool in enumerate(chain):
            try:
                key = _api_key(db, task.user_id, tool, demo)
                pkg = build_package(db, task, sub, subs, tool)
                db.commit()
            except FatalError as e:
                last_err = str(e)
                pkg = key = None
            for attempt in range(s.max_retries + 1 if pkg else 0):
                ex = Execution(task_id=task_id, subtask_id=sub_id, tool_id=tool.id, status="running", started_at=now(), retries=attempt)
                db.add(ex)
                db.commit()
                t0 = time.monotonic()
                try:
                    adapter = adp.get_adapter(tool.adapter)
                    _stream_tokens(db, task_id, sub_id, adapter, pkg, tool, key, sub.capability)
                    res = adapter.run(pkg, tool, key, sub.capability)
                except (RetryableError, FatalError) as e:
                    last_err = str(e)
                    ex.status, ex.error, ex.finished_at = "failed", last_err, now()
                    ex.latency_ms = int((time.monotonic() - t0) * 1000)
                    if isinstance(e, RetryableError) and attempt < s.max_retries:
                        emit(db, task_id, "step.retry", f"{tool.name} had a temporary problem ({last_err}). Trying again ({attempt + 1} of {s.max_retries}).", subtask_id=str(sub_id))
                        db.commit()
                        sleep(s.retry_backoff * 2 ** attempt)
                        continue
                    db.commit()
                    break
                ex.status, ex.finished_at, ex.latency_ms = "done", now(), int((time.monotonic() - t0) * 1000)
                ex.tokens_in, ex.tokens_out = res.tokens_in, res.tokens_out
                db.add(Usage(user_id=task.user_id, execution_id=ex.id, tokens_in=res.tokens_in, tokens_out=res.tokens_out))
                sub.output = {"text": res.text, "data": res.data, "simulated": res.simulated, "label": label, "tool": tool.id}
                sub.status = "done"
                if sub.capability != "validation":
                    db.add(ContextItem(task_id=task_id, subtask_id=sub_id, label=f"{label} output", content=res.text or label,
                                       kind=KIND_FOR.get(sub.capability, "output")))
                emit(db, task_id, "step.done", f"{label} finished with {tool.name}.", subtask_id=str(sub_id), tool=tool.id)
                db.commit()
                return {"ok": True}
            if ti + 1 < len(chain):
                emit(db, task_id, "step.fallback", f"{tool.name} couldn't finish this step ({last_err}). Switching to {chain[ti + 1].name}.", subtask_id=str(sub_id))
                db.commit()
        sub.status = "failed"
        emit(db, task_id, "step.failed", f"{label} couldn't be completed: {last_err}.", subtask_id=str(sub_id))
        db.commit()
        return {"ok": False, "error": last_err}


def parse_validation(text: str) -> tuple[bool | None, list[str]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        j = json.loads(m.group(0)) if m else None
        if isinstance(j, dict) and isinstance(j.get("passed"), bool):
            return j["passed"], [str(i) for i in j.get("issues", [])][:8]
    except ValueError:
        pass
    return None, []


def _record_verdict(task_id, val_id, passed, issues) -> None:
    with session_scope() as db:
        v = db.get(Subtask, val_id)
        v.output = {**(v.output or {}), "validation": {"passed": passed, "issues": issues,
                                                          **({} if passed is not None else {"note": "The checker's reply could not be read, so the result was not independently checked."})}}
        db.commit()


MISSING_RE = re.compile(r"\b(missing|not (?:provided|included|present|given|there)|absent|omitted|no \w+ (?:was|were|is)|"
                        r"wasn'?t|isn'?t|without|only one|only \d|instead of|lacks?|fewer)\b", re.I)


def _revision_plan(issues: list[str], subs: list[Subtask], deps: list[Subtask]) -> tuple[list[str], list[Subtask]]:
    """From the check's issues, which capabilities to ADD (a whole part is missing) and which done
    steps to REDO (the issue names their part). Falls back to redoing the last step."""
    from .understanding import detect
    have = {s.capability for s in subs}
    add, redo_caps = [], set()
    for issue in issues:
        for cap in detect(issue):
            if cap not in have and MISSING_RE.search(issue):
                add.append(cap) if cap not in add else None
            elif cap in have:
                redo_caps.add(cap)
    redo = [d for d in deps if d.capability in redo_caps]
    if not add and not redo and deps:
        redo = [max(deps, key=lambda s: s.position)]
    return add, redo


def _validate(task_id, val_id, revisions: int = 0) -> None:
    with session_scope() as db:
        text = (db.get(Subtask, val_id).output or {}).get("text", "")
    passed, issues = parse_validation(text)
    _record_verdict(task_id, val_id, passed, issues)
    if passed is False and revisions < MAX_REVISIONS:
        from .followup_service import insert_steps
        from .planning_service import route_new
        with session_scope() as db:
            task, val = db.get(Task, task_id), db.get(Subtask, val_id)
            subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task_id).order_by(Subtask.position)))
            by_id = {str(s.id): s for s in subs}
            deps = [by_id[d] for d in val.depends_on if d in by_id and by_id[d].capability != "validation" and by_id[d].status == "done"]
            add, redo = _revision_plan(issues, subs, deps)
            added = route_new(db, task, insert_steps(db, task, subs, add)) if add else []
            if not redo and not added:
                db.commit()
                return
            db.add(ContextItem(task_id=task_id, kind="constraint", label="Validator feedback", content="Fix these problems: " + "; ".join(issues)))
            for t in redo:
                db.execute(delete(ContextItem).where(ContextItem.subtask_id == t.id))
                t.status = "planned"
            names = [LABEL.get(s.capability, s.capability) for s in [*added, *redo]]
            what = (f"Adding the missing part ({', '.join(LABEL.get(c, c) for c in add)}) and " if added else "") + f"asking {', '.join(names)} to fix them."
            emit(db, task_id, "validation.revision", f"The check found problems: {'; '.join(issues) or 'unspecified'}. {what[0].upper() + what[1:]}",
                 subtask_id=str((added or redo)[0].id))
            val.status = "planned"
            run_ids = [s.id for s in [*added, *redo]]
            db.commit()
        s = get_settings()
        if len(run_ids) > 1 and s.exec_parallelism > 1:
            with ThreadPoolExecutor(min(s.exec_parallelism, len(run_ids))) as pool:
                oks = list(pool.map(lambda i: run_step(task_id, i)["ok"], run_ids))
        else:
            oks = [run_step(task_id, i)["ok"] for i in run_ids]
        if any(oks) and run_step(task_id, val_id)["ok"]:
            with session_scope() as db:
                text = (db.get(Subtask, val_id).output or {}).get("text", "")
            p2, i2 = parse_validation(text)
            _record_verdict(task_id, val_id, p2, i2)
        with session_scope() as db:  # never leave the check or a fixed step half-finished
            for i, ok in zip(run_ids, oks):
                x = db.get(Subtask, i)
                if not ok and x.status != "done":
                    x.status = "done" if x.output else "skipped"  # a redo that failed keeps its first answer
            v = db.get(Subtask, val_id)
            if v.status != "done":
                v.status = "done"  # the first verdict stands; stops the run loop re-checking forever
            db.commit()


def _fail(task_id, what: str, doing: str, details: str) -> None:
    with session_scope() as db:
        t = db.get(Task, task_id)
        t.status, t.error = "failed", {"what": what, "doing": doing, "details": details}
        emit(db, task_id, "task.failed", what + " " + doing)
        audit(db, "task.failed", t.user_id, task_id=str(task_id))
        db.commit()


def run_task(task_id) -> None:
    s = get_settings()
    try:
        with session_scope() as db:
            t = db.get(Task, task_id)
            t.status, t.error = "running", None
            emit(db, task_id, "task.started", "Starting the run.")
            audit(db, "task.run", t.user_id, task_id=str(task_id))
            db.commit()
        while True:
            with session_scope() as db:
                subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task_id).order_by(Subtask.position)))
                finished = {str(x.id) for x in subs if x.status in ("done", "skipped")}
                pending = [x for x in subs if x.status == "planned"]
                ready = [(x.id, x.capability) for x in pending if set(x.depends_on or []) <= finished]
            if not pending:
                break
            if not ready:
                return _fail(task_id, "The plan has a step that can never start.", "Nothing was lost. Plan the task again.", "dependency deadlock")
            if len(ready) > 1 and s.exec_parallelism > 1:
                with ThreadPoolExecutor(min(s.exec_parallelism, len(ready))) as pool:
                    outs = list(pool.map(lambda r: run_step(task_id, r[0]), ready))
            else:
                outs = [run_step(task_id, r[0]) for r in ready]
            for (sid, cap), out in zip(ready, outs):
                if out["ok"]:
                    if cap == "validation":
                        _validate(task_id, sid)
                    continue
                adj = replanner.adjust(cap, out["error"])
                if adj["action"] == "abort":
                    return _fail(task_id, f"{LABEL.get(cap, cap)} failed, and the task can't finish without it.",
                                 "Your other work is saved. Check the tool's key in Tools, then run the task again.", out["error"])
                with session_scope() as db:
                    x = db.get(Subtask, sid)
                    x.status, x.routing = "skipped", {**(x.routing or {}), "skipped": True, "note": adj["note"]}
                    emit(db, task_id, "step.skipped", adj["note"], subtask_id=str(sid))
                    db.commit()
        with session_scope() as db:
            t = db.get(Task, task_id)
            subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task_id)))
            db.execute(delete(Result).where(Result.task_id == task_id))
            r = build_result(t, subs)
            db.add(Result(task_id=task_id, kind=r["kind"], payload=r))
            t.status = "done"
            emit(db, task_id, "task.done", "Done. Your result is ready.")
            audit(db, "task.done", t.user_id, task_id=str(task_id))
            db.commit()
    except Exception as e:  # a bug, not a provider failure: say so plainly and keep the trace in logs
        log.exception("run_task crashed")
        _fail(task_id, "Conduit hit an unexpected problem while running this task.", "The run was stopped and nothing else will happen. Try again, and report it if it repeats.", repr(e))
