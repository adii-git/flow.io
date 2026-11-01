import json
import pytest
from sqlalchemy import select
from app import adapters, db as dbmod
from app.adapters import AdapterResult, FatalError, RetryableError
from app.adapters.base import Adapter
from app.config import get_settings
from app.models import Execution, Tool
from app.planner import build_steps
from app.registry.loader import load_specs
from app.routing import route_step
from tests.test_tasks import signup

RESEARCH = "Compare three competitors in the EU e-bike market and write a one-page brief"
CODE = "Build a Python script that cleans a sales CSV and charts monthly revenue"


class Fake(Adapter):
    def __init__(self, fn=None):
        self.calls, self.fn = [], fn

    def run(self, pkg, tool, key, capability):
        n = sum(1 for t, c in self.calls if (t, c) == (tool.id, capability))
        self.calls.append((tool.id, capability))
        if self.fn:
            r = self.fn(tool, capability, n)
            if r is not None:
                return r
        return {"validation": AdapterResult('{"passed": true, "issues": []}'),
                "web_research": AdapterResult("found", {"sources": [{"title": "T", "url": "https://x.test/a", "description": "d"}]}),
                "code_generation": AdapterResult("Here:\n```python app.py\nprint('hi')\n```"),
                "reasoning": AdapterResult("Analysis.\n```json\n{\"title\":\"Sales\",\"labels\":[\"a\",\"b\"],\"values\":[1,2]}\n```"),
                }.get(capability, AdapterResult(f"{capability} output"))


@pytest.fixture()
def live(client, monkeypatch):
    """Live mode with all provider keys saved and every adapter replaced by a scriptable fake."""
    s = get_settings()
    monkeypatch.setattr(s, "execution_mode", "live")
    h = signup(client, "a@example.com")
    for p in ("anthropic", "brave", "openai", "gemini", "groq", "huggingface"):
        assert client.post("/api/tools/connect", json={"provider": p, "api_key": f"key-for-{p}-123456"}, headers=h).status_code == 200

    def install(fn=None):
        f = Fake(fn)
        adapters.OVERRIDE = {k: f for k in ("anthropic_messages", "brave_search", "openai_images", "gemini_generate", "groq_chat", "huggingface_chat",
                                            "gemini_images", "pollinations_images")}
        return f
    return client, h, install


def run(client, h, objective, priority="balanced"):
    t = client.post("/api/tasks", json={"objective": objective}, headers=h).json()
    p = client.post(f"/api/tasks/{t['id']}/plan", json={"priority": priority}, headers=h)
    assert p.status_code == 200, p.text
    r = client.post(f"/api/tasks/{t['id']}/execute", headers=h)
    return t["id"], p.json(), r


def events(client, h, tid):
    with client.stream("GET", f"/api/tasks/{tid}/stream", headers=h) as r:
        return r.read().decode()


# ---------- pure units ----------
def test_planner_parallel_gather_then_chain():
    s = build_steps(["file_processing", "web_research", "reasoning", "code_generation"])
    assert s[0]["deps"] == [] and s[1]["deps"] == []                 # gathering runs in parallel
    assert s[2]["deps"] == [0, 1] and s[3]["deps"] == [2]              # then a chain
    assert s[4]["capability"] == "validation" and s[4]["deps"] == [3]


def _tools():
    return [Tool(**s.model_dump()) for s in load_specs()]


def test_router_specialists_and_independent_validation():
    t = _tools()
    assert route_step("web_research", t, ready_providers={"brave"}).tool_id == "brave-search"
    assert route_step("web_research", t, ready_providers={"gemini"}).tool_id == "gemini-2-5-flash-lite-search"
    assert route_step("image_generation", t, ready_providers={"openai"}).tool_id == "openai-image"
    d = route_step("validation", t, ready_providers={"anthropic"})
    same = route_step("validation", t, ready_providers={"anthropic"}, avoid_tool=d.tool_id)
    assert same.tool_id != d.tool_id and any("independent" in r for r in same.reasons)


def test_router_prefers_ready_tools_and_flags_blockers():
    t = _tools()
    d = route_step("web_research", t, ready_providers=set())
    assert d.tool_id == "gemini-2-5-flash-lite-search" and d.blockers == ["gemini"]
    assert route_step("web_research", t, ready_providers=set(), demo=True).blockers == []


def test_router_unroutable_and_priority():
    t = _tools()
    assert route_step("code_execution", t, ready_providers=set()).tool_id is None       # sandbox is planned
    assert route_step("reasoning", t, ready_providers={"anthropic"}, priority="quality").tool_id == "claude-opus-5-5"
    assert route_step("reasoning", t, ready_providers={"anthropic"}, priority="cheap").tool_id == "claude-haiku-4-5"
    assert route_step("reasoning", t, ready_providers={"anthropic"}, need_tokens=10**6).tool_id is None


# ---------- plan / execute ----------
def test_demo_mode_runs_end_to_end_and_labels_output(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_mode", "demo")
    h = signup(client, "a@example.com")
    tid, plan, r = run(client, h, RESEARCH)
    assert plan["blockers"] == [] and r.status_code == 202
    task = client.get(f"/api/tasks/{tid}", headers=h).json()
    assert task["status"] == "done" and any(x in task["tools_used"] for x in ("brave-search", "gemini-2-5-flash-lite-search"))
    res = client.get(f"/api/tasks/{tid}/result", headers=h).json()
    assert res["kind"] == "research" and res["simulated"] is True and res["sources"] and res["validation"]["passed"] is True
    ev = events(client, h, tid)
    assert "event: task.started" in ev and "event: task.done" in ev and "event: step.done" in ev
    assert client.get("/api/config").json()["execution_mode"] == "demo"


def test_live_without_keys_is_blocked_with_clear_message(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_mode", "live")
    h = signup(client, "a@example.com")
    t = client.post("/api/tasks", json={"objective": RESEARCH}, headers=h).json()
    p = client.post(f"/api/tasks/{t['id']}/plan", headers=h).json()
    assert {b["provider"] for b in p["blockers"]} == {"anthropic", "gemini"}
    r = client.post(f"/api/tasks/{t['id']}/execute", headers=h)
    assert r.status_code == 409 and "Add a key" in r.json()["detail"]
    assert client.post(f"/api/tasks/{t['id']}/execute", headers=signup(client, "b@example.com")).status_code == 404


def test_plan_records_reasons_confidence_context(live):
    c, h, install = live
    install()
    t = c.post("/api/tasks", json={"objective": RESEARCH}, headers=h).json()
    sub = c.post(f"/api/tasks/{t['id']}/plan", headers=h).json()["task"]["subtasks"]
    for s in sub:
        r = s["routing"]
        assert r["tool_id"] and r["reasons"] and 0 < r["confidence"] <= 0.95 and r["context_items"] >= 1


def test_full_run_context_isolation_and_result(live):
    c, h, install = live
    f = install()
    tid, _, r = run(c, h, RESEARCH)
    assert r.status_code == 202
    assert c.get(f"/api/tasks/{tid}", headers=h).json()["status"] == "done"
    ctx = c.get(f"/api/context/{tid}", headers=h).json()
    val = next(x for x in ctx if x["step"] == "validation")
    assert any(s["kind"] == "objective" for s in val["sent"])
    web = next(x for x in ctx if x["step"] == "web_research")
    assert not any(s["kind"] in ("output", "decision") for s in web["sent"])         # search gets no prior outputs
    assert [c_ for _, c_ in f.calls].count("validation") == 1
    assert c.post(f"/api/tasks/{tid}/execute", headers=h).status_code == 202            # re-run allowed
    assert c.get(f"/api/tasks/{tid}/result", headers=h).json()["sources"][0]["url"] == "https://x.test/a"


def test_retry_then_fallback_then_success(live):
    c, h, install = live
    t = c.post("/api/tasks", json={"objective": RESEARCH}, headers=h).json()
    plan = c.post(f"/api/tasks/{t['id']}/plan", headers=h).json()["task"]["subtasks"]
    reasoning = next(s for s in plan if s["capability"] == "reasoning")["routing"]
    bad = reasoning["tool_id"]

    def fn(tool, cap, n):
        if cap == "reasoning" and tool.id == bad:
            raise RetryableError("timeout")
    f = install(fn)
    assert c.post(f"/api/tasks/{t['id']}/execute", headers=h).status_code == 202
    assert c.get(f"/api/tasks/{t['id']}", headers=h).json()["status"] == "done"
    ev = events(c, h, t["id"])
    assert ev.count("event: step.retry") == 2 and "event: step.fallback" in ev
    assert f.calls.count((bad, "reasoning")) == 3                                         # 1 try + 2 retries
    with dbmod.session_scope() as db:
        assert len(db.scalars(select(Execution).where(Execution.status == "failed")).all()) == 3


def test_all_tools_fail_gives_plain_failure(live):
    c, h, install = live

    def fn(tool, cap, n):
        if cap == "reasoning":
            raise FatalError("the provider rejected the saved API key")
    install(fn)
    tid, _, _ = run(c, h, RESEARCH)
    t = c.get(f"/api/tasks/{tid}", headers=h).json()
    assert t["status"] == "failed" and "Reasoning failed" in t["error"]["what"] and "rejected" in t["error"]["details"]
    assert c.get(f"/api/tasks/{tid}/result", headers=h).status_code == 404
    assert "event: task.failed" in events(c, h, tid)


def test_validation_failure_triggers_one_revision(live):
    c, h, install = live

    def fn(tool, cap, n):
        if cap == "validation":
            return AdapterResult(json.dumps({"passed": n > 0, "issues": ["missing pricing"]}))
    f = install(fn)
    tid, _, _ = run(c, h, RESEARCH)
    ev = events(c, h, tid)
    assert "event: validation.revision" in ev and "missing pricing" in ev
    assert [cap for _, cap in f.calls].count("reasoning") == 2
    assert c.get(f"/api/tasks/{tid}/result", headers=h).json()["validation"]["passed"] is True


def test_unreadable_checker_reply_is_not_claimed_as_checked(live):
    c, h, install = live
    install(lambda tool, cap, n: AdapterResult("looks fine to me") if cap == "validation" else None)
    tid, _, _ = run(c, h, RESEARCH)
    v = c.get(f"/api/tasks/{tid}/result", headers=h).json()["validation"]
    assert v["passed"] is None and "not independently checked" in v["note"]


def test_code_task_skips_unavailable_execution_and_extracts_files(live):
    c, h, install = live
    install()
    t = c.post("/api/tasks", json={"objective": CODE}, headers=h).json()
    p = c.post(f"/api/tasks/{t['id']}/plan", headers=h).json()
    assert any("isn't available yet" in n for n in p["notes"])
    assert [s["status"] for s in p["task"]["subtasks"] if s["capability"] == "code_execution"] == ["skipped"]
    assert c.post(f"/api/tasks/{t['id']}/execute", headers=h).status_code == 202
    res = c.get(f"/api/tasks/{t['id']}/result", headers=h).json()
    assert res["kind"] == "code" and res["files"][0]["path"] == "app.py" and "print('hi')" in res["files"][0]["content"]


def test_analysis_chart_is_extracted(live):
    c, h, install = live
    install()
    tid, _, _ = run(c, h, "Analyze this csv and compare the numbers, then decide what to do")
    res = c.get(f"/api/tasks/{tid}/result", headers=h).json()
    assert res["kind"] in ("analysis", "project") and res["chart"]["labels"] == ["a", "b"]
    assert "```json" not in res["markdown"]


def test_cannot_start_a_task_twice(live):
    c, h, install = live
    install()
    t = c.post("/api/tasks", json={"objective": RESEARCH}, headers=h).json()
    c.post(f"/api/tasks/{t['id']}/plan", headers=h)
    from app.models import Task
    with dbmod.session_scope() as db:
        db.get(Task, __import__("uuid").UUID(t["id"])).status = "running"; db.commit()
    assert c.post(f"/api/tasks/{t['id']}/execute", headers=h).status_code == 409
    assert c.post(f"/api/tasks/{t['id']}/plan", headers=h).status_code == 409


def test_unplanned_task_cannot_run(client):
    h = signup(client, "a@example.com")
    t = client.post("/api/tasks", json={"objective": RESEARCH}, headers=h).json()
    assert client.post(f"/api/tasks/{t['id']}/execute", headers=h).status_code == 409


# ---------- usage + admin ----------
def test_usage_and_admin_metrics(live, monkeypatch):
    c, h, install = live
    install(lambda tool, cap, n: AdapterResult("x", tokens_in=10, tokens_out=5) if cap == "reasoning" else None)
    run(c, h, RESEARCH)
    u = c.get("/api/usage", headers=h).json()
    assert u["tasks"] == 1 and u["tokens_in"] == 10 and u["tokens_out"] == 5 and u["calls"] >= 4
    assert c.get("/api/admin/metrics", headers=h).status_code == 403
    monkeypatch.setattr(get_settings(), "admin_emails", "boss@example.com")
    admin = signup(c, "boss@example.com")
    m = c.get("/api/admin/metrics", headers=admin).json()
    assert m["runs"][0]["tokens_in"] == 10 and m["runs"][0]["status"] == "done" and m["runs"][0]["context_chars"] > 0
    assert any(x["p50"] is not None for x in m["provider_latency_ms"])
