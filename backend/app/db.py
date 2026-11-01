from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from .config import get_settings

_engine = None
_Session = None


def init_engine(url: str | None = None, **kw):
    global _engine, _Session
    _engine = create_engine(url or get_settings().database_url, pool_pre_ping=True, **kw)
    _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    if _Session is None:
        init_engine()
    with _Session() as s:
        yield s


from contextlib import contextmanager  # noqa: E402


@contextmanager
def session_scope():
    if _Session is None:
        init_engine()
    with _Session() as s:
        yield s
