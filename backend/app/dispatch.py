import logging
import threading
from .config import get_settings
from .executor import run_task

log = logging.getLogger("conduit.dispatch")


def _thread(task_id) -> None:
    threading.Thread(target=run_task, args=(task_id,), daemon=True).start()


def dispatch(task_id) -> str:
    """Starts a run. Returns the backend actually used: celery | sync | thread."""
    b = get_settings().execution_backend
    if b == "celery":
        try:
            from .worker import run_task_job
            run_task_job.delay(str(task_id))
            return "celery"
        except Exception:  # broker down: run here rather than leave the task stuck as 'running'
            log.exception("celery broker unreachable, running task %s in a thread", task_id)
            _thread(task_id)
            return "thread"
    if b == "sync":
        run_task(task_id)
        return "sync"
    _thread(task_id)
    return "thread"
