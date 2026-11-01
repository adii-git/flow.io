"""Phase 3: robustness. Real Celery task path, broker failure, parallel steps, timeouts, rate limits."""
import threading

import httpx
import pytest

from app import dispatch as dispatch_mod, worker
from app.adapters import AdapterResult, RetryableError, providers
from app.config import get_settings
from tests.test_engine import RESEARCH, live, run  # noqa: F401  (live is a fixture)
from tests.test_support import KEY, pkg, tool  # noqa: F401  (pkg is a fixture)


# ---------- Celery queue ----------
def test_task_runs_through_the_celery_worker(live, monkeypatch):
    c, h, install = live
    install()
    monkeypatch.setattr(get_settings(), "execution_backend", "celery")
    monkeypatch.setattr(worker.celery_app.conf, "task_always_eager", True)  # run the real Celery task in-process
    seen = []
    real = worker.run_task_job.run
    monkeypatch.setattr(worker.run_task_job, "run", lambda tid: (seen.append(tid), real(tid))[1])
    tid, _, r = run(c, h, RESEARCH)
    assert r.status_code == 202
    assert seen == [tid]  # the job went through Celery, not a thread
    assert c.get(f"/api/tasks/{tid}", headers=h).json()["status"] == "done"


def test_broker_down_falls_back_to_a_thread(monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_backend", "celery")

    def down(*a, **k):
        raise ConnectionError("broker unreachable")
    monkeypatch.setattr(worker.run_task_job, "delay", down)
    started = []
    monkeypatch.setattr(dispatch_mod, "_thread", lambda tid: started.append(tid))
    assert dispatch_mod.dispatch("t-1") == "thread" and started == ["t-1"]


def test_broker_url_order(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "celery_broker_url", "")
    monkeypatch.setattr(s, "redis_url", "")
    assert worker.broker_url() == "memory://"
    monkeypatch.setattr(s, "redis_url", "redis://r:6379/0")
    assert worker.broker_url() == "redis://r:6379/0"
    monkeypatch.setattr(s, "celery_broker_url", "sqla+sqlite:///x.db")
    assert worker.broker_url() == "sqla+sqlite:///x.db"


# ---------- parallel steps ----------
@pytest.fixture()
def file_db_live(tmp_path, monkeypatch):
    """Like `live`, but on a file SQLite DB: the in-memory test DB is one shared connection,
    which cannot serve two threads at once. A file DB gives each thread its own connection."""
    from fastapi.testclient import TestClient
    from app import adapters, db as dbmod
    from app.main import create_app
    from app.models import Base
    from app.ratelimit import limiter
    from tests.test_engine import Fake
    from tests.test_tasks import signup
    engine = dbmod.init_engine(f"sqlite:///{tmp_path}/p.db", connect_args={"check_same_thread": False, "timeout": 15})
    Base.metadata.create_all(engine)
    limiter.reset()
    monkeypatch.setattr(get_settings(), "execution_mode", "live")
    with TestClient(create_app()) as c:
        h = signup(c, "p@example.com")
        for p in ("anthropic", "brave", "openai", "gemini", "groq", "huggingface"):
            c.post("/api/tools/connect", json={"provider": p, "api_key": f"key-for-{p}-123456"}, headers=h)

        def install(fn=None):
            f = Fake(fn)
            adapters.OVERRIDE = {k: f for k in ("anthropic_messages", "brave_search", "openai_images", "gemini_generate", "groq_chat", "huggingface_chat")}
            return f
        yield c, h, install
    Base.metadata.drop_all(engine)


def test_gather_steps_really_run_at_the_same_time(file_db_live, monkeypatch):
    """Research + document reading have no dependency on each other. Both must be inside the
    adapter at once: a 2-party barrier only opens if they run in parallel."""
    c, h, install = file_db_live
    monkeypatch.setattr(get_settings(), "exec_parallelism", 3)
    gate = threading.Barrier(2, timeout=5)

    def fn(tool, cap, n):
        if cap in ("web_research", "long_context_documents") and n == 0:
            gate.wait()  # raises BrokenBarrierError if the other step is not running alongside
        return None
    install(fn)
    tid, _, _ = run(c, h, RESEARCH)
    assert c.get(f"/api/tasks/{tid}", headers=h).json()["status"] == "done"
    assert not gate.broken


# ---------- provider timeouts ----------
def test_read_timeout_is_retryable(pkg):
    def slow(r): raise httpx.ReadTimeout("too slow")
    providers.TRANSPORT = httpx.MockTransport(slow)
    try:
        with pytest.raises(RetryableError):
            providers.GroqChat().run(pkg, tool("groq_chat", "m"), KEY, "reasoning")
        with pytest.raises(RetryableError):
            providers.GeminiGenerate().run(pkg, tool("gemini_generate", "m"), KEY, "reasoning")
    finally:
        providers.TRANSPORT = None


def test_provider_timeout_is_configurable(monkeypatch):
    monkeypatch.setattr(get_settings(), "provider_timeout", 7.5)
    with providers._client() as cl:
        assert cl.timeout.read == 7.5


def test_rate_limited_provider_retries_then_succeeds(live):
    c, h, install = live

    def fn(tool, cap, n):
        if cap == "reasoning" and n == 0:
            raise RetryableError("the provider is busy or down (status 429)")
        return None
    f = install(fn)
    tid, _, _ = run(c, h, RESEARCH)
    assert c.get(f"/api/tasks/{tid}", headers=h).json()["status"] == "done"
    reasoning = [x for x in f.calls if x[1] == "reasoning"]
    assert len(reasoning) == 2 and reasoning[0] == reasoning[1]  # same tool, retried once


# ---------- our own API rate limits ----------
def test_login_is_rate_limited(client):
    body = {"email": "x@example.com", "password": "wrong-password-123"}
    codes = [client.post("/api/auth/login", json=body).status_code for _ in range(11)]
    assert 429 not in codes[:10] and codes[10] == 429


def test_task_creation_is_rate_limited(client):
    from tests.test_tasks import signup
    h = signup(client, "r@example.com")
    codes = [client.post("/api/tasks", json={"objective": "Write a short plan"}, headers=h).status_code for _ in range(31)]
    assert codes[:30].count(201) == 30 and codes[30] == 429
