"""Follow-ups: continue a finished task in the same session."""
from sqlalchemy import select

from app import db as dbmod
from app.models import ContextItem
from tests.test_engine import live, run  # noqa: F401  (live is a fixture)

IMG = "Design a logo for a streetwear brand called storkk"


def _done(c, h, tid):
    return c.get(f"/api/tasks/{tid}", headers=h).json()


def test_follow_up_reruns_with_the_change_and_previous_answer(live):
    c, h, install = live
    f = install()
    tid, _, _ = run(c, h, "Compare pricing options for our launch and recommend one")
    assert _done(c, h, tid)["status"] == "done"
    seen = []
    orig = f.run

    def spy(pkg, tool, key, cap):
        seen.append((cap, pkg.to_prompt()))
        return orig(pkg, tool, key, cap)
    f.run = spy
    r = c.post(f"/api/tasks/{tid}/followup", json={"message": "Make it shorter, three bullet points"}, headers=h)
    assert r.status_code == 202, r.text
    assert _done(c, h, tid)["status"] == "done"
    reasoning = next(p for cap, p in seen if cap == "reasoning")
    assert "Make it shorter, three bullet points" in reasoning      # the change reaches the model
    assert "Output of: Previous answer" in reasoning                # with the old answer to revise
    hist = c.get(f"/api/tasks/{tid}/followups", headers=h).json()
    assert [m["message"] for m in hist] == ["Make it shorter, three bullet points"]


def test_follow_up_can_add_a_new_step(live):
    c, h, install = live
    install()
    tid, _, _ = run(c, h, IMG)
    before = [s["capability"] for s in _done(c, h, tid)["subtasks"]]
    assert "code_generation" not in before
    assert c.post(f"/api/tasks/{tid}/followup", json={"message": "Now build a simple website that shows this logo"}, headers=h).status_code == 202
    t = _done(c, h, tid)
    caps = [s["capability"] for s in t["subtasks"]]
    assert t["status"] == "done" and "code_generation" in caps and caps[-1] == "validation"
    assert [s["position"] for s in sorted(t["subtasks"], key=lambda s: s["position"])] == list(range(len(caps)))


def test_plain_change_adds_no_step_and_previous_answer_is_not_duplicated(live):
    c, h, install = live
    install()
    tid, _, _ = run(c, h, IMG)
    n = len(_done(c, h, tid)["subtasks"])
    for msg in ("make the background blue", "add more contrast"):
        assert c.post(f"/api/tasks/{tid}/followup", json={"message": msg}, headers=h).status_code == 202
    assert len(_done(c, h, tid)["subtasks"]) == n
    with dbmod.session_scope() as db:
        prev = db.scalars(select(ContextItem).where(ContextItem.label == "Previous answer")).all()
    assert len(prev) == 1


def test_follow_up_rules(live, client):
    c, h, install = live
    install()
    t = c.post("/api/tasks", json={"objective": IMG}, headers=h).json()
    assert c.post(f"/api/tasks/{t['id']}/followup", json={"message": "hi there"}, headers=h).status_code == 409  # not run yet
    tid, _, _ = run(c, h, IMG)
    assert c.post(f"/api/tasks/{tid}/followup", json={"message": "   "}, headers=h).status_code == 422
    from tests.test_tasks import signup
    other = signup(c, "z@example.com")
    assert c.post(f"/api/tasks/{tid}/followup", json={"message": "steal"}, headers=other).status_code == 404
    assert c.get(f"/api/tasks/{tid}/followups", headers=other).status_code == 404
