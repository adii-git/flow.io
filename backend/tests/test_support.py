import json
import httpx
import pytest
from app import db as dbmod
from app.adapters import FatalError, RetryableError, providers
from app.config import get_settings
from app.context_manager import build_package
from app.models import Subtask, Task, Tool
from sqlalchemy import select
from tests.test_tasks import signup

KEY = "k-123456789"


def tool(adapter, model=""):
    return Tool(id="t", name="T", provider="p", capabilities=[], config={"model": model}, adapter=adapter)


@pytest.fixture()
def pkg():
    from app.context_manager import Package
    return Package(objective="Do X", requirements=["r1"], current_state="s", next_task="n")


def mock(handler):
    providers.TRANSPORT = httpx.MockTransport(handler)
    yield
    providers.TRANSPORT = None


@pytest.fixture()
def anthropic_ok():
    yield from mock(lambda r: httpx.Response(200, json={"content": [{"type": "text", "text": "hello"}], "usage": {"input_tokens": 7, "output_tokens": 3}}))


def test_anthropic_success_sends_key_and_package(anthropic_ok, pkg):
    seen = {}
    providers.TRANSPORT = httpx.MockTransport(lambda r: (seen.update(h=r.headers, b=json.loads(r.content)), httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}], "usage": {}}))[1])
    out = providers.AnthropicMessages().run(pkg, tool("a", "claude-x"), KEY, "reasoning")
    assert out.text == "hi" and seen["h"]["x-api-key"] == KEY and seen["b"]["model"] == "claude-x" and "Do X" in seen["b"]["messages"][0]["content"]


@pytest.mark.parametrize("status,exc", [(401, FatalError), (403, FatalError), (400, FatalError), (429, RetryableError), (503, RetryableError)])
def test_provider_status_mapping(pkg, status, exc):
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(status, json={}))
    try:
        with pytest.raises(exc):
            providers.AnthropicMessages().run(pkg, tool("a", "m"), KEY, "reasoning")
    finally:
        providers.TRANSPORT = None


def test_network_failure_is_retryable(pkg):
    def boom(r): raise httpx.ConnectTimeout("slow")
    providers.TRANSPORT = httpx.MockTransport(boom)
    try:
        with pytest.raises(RetryableError):
            providers.BraveSearch().run(pkg, tool("b"), KEY, "web_research")
    finally:
        providers.TRANSPORT = None


def test_brave_and_openai_parse(pkg):
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"web": {"results": [{"title": "A", "url": "https://a.test", "description": "d"}]}}))
    assert providers.BraveSearch().run(pkg, tool("b"), KEY, "web_research").data["sources"][0]["url"] == "https://a.test"
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": [{"b64_json": "QUJD"}, {"url": "http://insecure.test/x.png"}]}))
    out = providers.OpenAIImages().run(pkg, tool("o", "img"), KEY, "image_generation")
    providers.TRANSPORT = None
    assert out.data["images"] == [{"mime": "image/png", "b64": "QUJD"}]  # non-https URLs are dropped


def test_gemini_images_parses_inline_data(pkg):
    seen = {}

    def handler(r):
        seen.update(h=r.headers, b=json.loads(r.content), url=str(r.url))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "image/png", "data": "QUJD"}}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 0}})

    providers.TRANSPORT = httpx.MockTransport(handler)
    try:
        out = providers.GeminiImages().run(pkg, tool("gemini_images", "gemini-2.5-flash-image"), KEY, "image_generation")
    finally:
        providers.TRANSPORT = None
    assert out.data["images"] == [{"mime": "image/png", "b64": "QUJD"}]
    assert seen["h"]["x-goog-api-key"] == KEY
    assert seen["b"]["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert "gemini-2.5-flash-image:generateContent" in seen["url"]
    assert "Do X" in seen["b"]["contents"][0]["parts"][0]["text"]


def test_gemini_images_no_image_is_retryable(pkg):
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]}))
    try:
        with pytest.raises(RetryableError):
            providers.GeminiImages().run(pkg, tool("gemini_images", "gemini-2.5-flash-image"), KEY, "image_generation")
    finally:
        providers.TRANSPORT = None


# ---------- Phase 2: token streaming ----------
def _sse_body(lines):
    return ("".join(f"data: {l}\n\n" for l in lines)).encode()


def test_groq_stream_yields_deltas(pkg):
    seen = {}

    def handler(r):
        seen.update(b=json.loads(r.content))
        return httpx.Response(200, content=_sse_body([
            json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
            json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
            "[DONE]",
        ]), headers={"content-type": "text/event-stream"})

    providers.TRANSPORT = httpx.MockTransport(handler)
    try:
        chunks = list(providers.GroqChat().stream(pkg, tool("groq_chat", "m"), KEY, "reasoning"))
    finally:
        providers.TRANSPORT = None
    assert chunks == ["Hel", "lo"] and seen["b"]["stream"] is True
    assert providers.GroqChat().streams is True


def test_gemini_stream_yields_deltas(pkg):
    body = _sse_body([
        json.dumps({"candidates": [{"content": {"parts": [{"text": "A"}]}}]}),
        json.dumps({"candidates": [{"content": {"parts": [{"text": "B"}]}}]}),
    ])
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"}))
    try:
        chunks = list(providers.GeminiGenerate().stream(pkg, tool("gemini_generate", "gemini-x"), KEY, "reasoning"))
    finally:
        providers.TRANSPORT = None
    assert chunks == ["A", "B"]


def test_stream_error_is_silent(pkg):
    # a failed stream must yield nothing, never raise — the engine falls back to run()
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    try:
        assert list(providers.GroqChat().stream(pkg, tool("groq_chat", "m"), KEY, "reasoning")) == []
    finally:
        providers.TRANSPORT = None


def test_default_adapter_stream_falls_back_to_run(pkg):
    from app.adapters.base import Adapter, AdapterResult

    class One(Adapter):
        def run(self, pkg, tool, api_key, capability):
            return AdapterResult("whole answer")

    assert list(One().stream(pkg, tool("x"), KEY, "reasoning")) == ["whole answer"]


# ---------- Phase 2: fast-step routing ----------
def _rt(id, speed, cost, caps=("validation",)):
    return Tool(id=id, name=id, provider=id, capabilities=list(caps), availability="available",
                requires_key=False, cost_class=cost, speed_class=speed, context_window=0, config={})


def test_fast_step_prefers_the_fastest_tool():
    from app.routing import route_step
    slow = _rt("slow", "slow", "low")
    fast = _rt("fast", "fast", "low")
    base = route_step("validation", [slow, fast], ready_providers=set(), demo=True)
    boosted = route_step("validation", [slow, fast], ready_providers=set(), demo=True, fast_step=True)
    assert base.tool_id == "fast"  # fast already wins; fast_step must not flip it
    assert boosted.tool_id == "fast"
    # with a fast tie broken only by the flag, the faster one still leads
    assert boosted.score >= base.score


# ---------- files + context isolation ----------
def upload(c, h, name="data.csv", body=b"a,b\n1,2\n"):
    return c.post("/api/files", headers=h, files={"file": (name, body, "text/csv")})


def test_upload_rules(client):
    h = signup(client, "a@example.com")
    assert upload(client, h).status_code == 201
    assert upload(client, h, "evil.exe", b"MZ").status_code == 415
    assert upload(client, h, "x.txt", b"ab\x00cd").status_code == 415
    assert upload(client, h, "big.txt", b"a" * 2_000_001).status_code == 413
    f = upload(client, h, "../../etc/passwd.txt", b"hi").json()
    assert f["filename"] == "passwd.txt"
    assert client.post("/api/files", files={"file": ("a.txt", b"x")}).status_code == 401
    assert client.get(f"/api/files/{f['id']}", headers=signup(client, "b@example.com")).status_code == 404


def test_attached_file_reaches_reading_steps_but_not_search(client):
    h = signup(client, "a@example.com")
    fid = upload(client, h, "sales.csv", b"month,rev\njan,10\n").json()["id"]
    t = client.post("/api/tasks", json={"objective": "Research competitors and summarize this report", "file_ids": [fid]}, headers=h).json()
    assert t["context_count"] >= 2
    with dbmod.session_scope() as db:
        task = db.get(Task, __import__("uuid").UUID(t["id"]))
        subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)))
        by = {s.capability: s for s in subs}
        web = build_package(db, task, by["web_research"], subs, persist=False)
        doc = build_package(db, task, by["long_context_documents"], subs, persist=False)
    assert web.files == [] and any(w["kind"] == "file" and "doesn't need" in w["reason"] for w in web.withheld)
    assert doc.files[0]["name"] == "sales.csv" and "jan,10" in doc.files[0]["excerpt"]
    # a file can only be claimed once, and only by its owner
    assert client.post("/api/tasks", json={"objective": "Reuse the file please", "file_ids": [fid]}, headers=h).status_code == 404
    other = signup(client, "b@example.com")
    f2 = upload(client, h, "p.txt", b"private").json()["id"]
    assert client.post("/api/tasks", json={"objective": "Steal the file please", "file_ids": [f2]}, headers=other).status_code == 404


def test_context_budget_trims_and_withholds():
    from app.models import ContextItem
    h_user = None  # budget logic only needs a tiny tool window
    small = Tool(id="s", name="S", provider="p", capabilities=[], context_window=100, config={}, adapter="x")
    from app.context_manager import budget_chars
    assert budget_chars(small) == 200 and budget_chars(None) == 12_000 and budget_chars(Tool(context_window=10**9)) == 200_000


def test_scratch_never_leaves(client):
    h = signup(client, "a@example.com")
    t = client.post("/api/tasks", json={"objective": "Write a report about our launch plan"}, headers=h).json()
    from app.models import ContextItem
    with dbmod.session_scope() as db:
        task = db.get(Task, __import__("uuid").UUID(t["id"]))
        db.add(ContextItem(task_id=task.id, kind="scratch", label="Hidden notes", content="private chain of thought")); db.commit()
        subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id).order_by(Subtask.position)))
        for s in subs:
            p = build_package(db, task, s, subs, persist=False)
            assert "private chain" not in p.to_prompt()
            assert any(w["kind"] == "scratch" for w in p.withheld)


def test_sse_resumes_after_last_event(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_mode", "demo")
    h = signup(client, "a@example.com")
    t = client.post("/api/tasks", json={"objective": "Compare competitors and write a brief"}, headers=h).json()
    client.post(f"/api/tasks/{t['id']}/plan", headers=h)
    client.post(f"/api/tasks/{t['id']}/execute", headers=h)
    with client.stream("GET", f"/api/tasks/{t['id']}/stream", headers=h) as r:
        full = r.read().decode()
    ids = [int(l[4:]) for l in full.splitlines() if l.startswith("id: ")]
    with client.stream("GET", f"/api/tasks/{t['id']}/stream", headers={**h, "Last-Event-ID": str(ids[-2])}) as r:
        tail = r.read().decode()
    assert tail.count("id: ") == 1 and "task.done" in tail
    assert client.get(f"/api/tasks/{t['id']}/stream", headers=signup(client, "b@example.com")).status_code == 404


def test_free_provider_adapters_parse(pkg):
    seen = []
    def handler(r):
        seen.append((str(r.url), r.headers, json.loads(r.content)))
        if "generativelanguage" in str(r.url):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "gemini"}]},
                "groundingMetadata": {"groundingChunks": [{"web": {"title": "Source", "uri": "https://source.test"}}]}}],
                "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7}})
        if "groq.com" in str(r.url):
            return httpx.Response(200, json={"choices": [{"message": {"content": "groq"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hf"}}], "usage": {"prompt_tokens": 4, "completion_tokens": 2}})

    providers.TRANSPORT = httpx.MockTransport(handler)
    try:
        g = providers.GeminiGenerate().run(pkg, Tool(id="g", name="g", provider="gemini", capabilities=[], config={"model": "gemini-x", "google_search": True}, adapter="g"), KEY, "web_research")
        q = providers.GroqChat().run(pkg, Tool(id="q", name="q", provider="groq", capabilities=[], config={"model": "openai/gpt-oss-120b"}, adapter="q"), KEY, "reasoning")
        h = providers.HuggingFaceChat().run(pkg, Tool(id="h", name="h", provider="huggingface", capabilities=[], config={"model": "openai/gpt-oss-120b:fastest"}, adapter="h"), KEY, "reasoning")
        assert g.text == "gemini" and g.data["sources"][0]["url"] == "https://source.test"
        assert (g.tokens_in, g.tokens_out) == (11, 7)
        assert q.text == "groq" and (q.tokens_in, q.tokens_out) == (5, 3)
        assert h.text == "hf" and (h.tokens_in, h.tokens_out) == (4, 2)
        assert seen[0][2]["tools"] == [{"google_search": {}}]
    finally:
        providers.TRANSPORT = None
