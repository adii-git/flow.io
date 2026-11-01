import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-000")
os.environ.setdefault("FERNET_KEY", "VGVzdEtleUZvckNvbmR1aXRUZXN0S2V5Rm9yQ29uZHU=")
os.environ["COOKIE_SECURE"] = "false"
os.environ.update(EXECUTION_BACKEND="sync", RETRY_BACKOFF="0", EXEC_PARALLELISM="1")
import tempfile
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from app import db as dbmod
from app.config import get_settings
from app.models import Base
from app.ratelimit import limiter

get_settings.cache_clear()
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
get_settings.cache_clear()


@pytest.fixture()
def client():
    engine = dbmod.init_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from sqlalchemy import event
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    limiter.reset()
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _reset_adapters():
    from app import adapters, ai_understanding
    import httpx
    adapters.OVERRIDE = None
    # The AI planner must never reach a real provider in tests; by default it "fails" and the
    # heuristic plan is used. Tests of the AI planner swap in their own transport.
    ai_understanding.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(503, json={}))
    yield
    adapters.OVERRIDE = None
    ai_understanding.TRANSPORT = None
