"""Celery worker. Start with:  celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

Broker: CELERY_BROKER_URL, else REDIS_URL, else in-memory (tests only).
"""
import uuid
from celery import Celery
from .config import get_settings
from .executor import run_task


def broker_url() -> str:
    s = get_settings()
    return s.celery_broker_url or s.redis_url or "memory://"


celery_app = Celery("conduit", broker=broker_url())
celery_app.conf.update(
    task_acks_late=True,            # a crashed worker hands the job back instead of losing it
    worker_prefetch_multiplier=1,   # one long run per worker slot at a time
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,        # results live in our own DB, not in Celery
)


@celery_app.task(name="conduit.run_task")
def run_task_job(task_id: str) -> None:
    run_task(uuid.UUID(task_id))
