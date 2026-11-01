from sqlalchemy.orm import Session
from .models import TaskEvent


def emit(db: Session, task_id, type_: str, message: str, **payload) -> None:
    """Adds an event to the caller's session; the caller commits."""
    db.add(TaskEvent(task_id=task_id, type=type_, payload={"message": message, **payload}))
