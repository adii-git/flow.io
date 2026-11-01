"""Every part of the ask gets done: writing steps, counts, the AI planner, and a check that adds missing parts."""
import json
import httpx
from app import ai_understanding
from app.adapters import AdapterResult, providers
from app.context_manager import Package
from app.executor import _revision_plan
from app.models import Subtask
from app.planner import build_steps
from app.understanding import counts, merge, step_text, understand
from tests.test_engine import live, run  # noqa: F401  (live is a fixture)

ASK = "write a 500 word essay on cars and also give two photos of car"


# ---------- understanding ----------
def test_mixed_ask_gets_every_part_and_its_numbers():
    u = understand(ASK)
    assert u.capabilities == ["writing", "image_generation"]
    assert u.counts == {"images": 2, "words": 500} and u.task_type == "document"
    assert "500 words" in step_text("writing", u.counts) and "2 different images" in step_text("image_generation", u.counts)


def test_writing_words_do_not_steal_code_or_brief_tasks():
    assert "writing" not in understand("Build a Python script that cleans a sales CSV").capabilities
    assert "writing" not in understand("Compare three competitors in the EU e-bike market and write a one-page brief").capabilities
    assert "writing" in understand("give me a photo of a car and write about it").capabilities


def test_counts():
    assert counts("make 3 logos and a 1200-word article") == {"images": 3, "words": 1200}
    assert counts("ten photos") == {} and counts("draw 9 pictures") == {"images": 4}  # capped
    assert counts("a pizza logo") == {"images": 1}


# ---------- planner ----------
def test_images_run_beside_writing_but_after_reasoning():
    s = build_steps(["writing", "image_generation"])
    assert s[0]["deps"] == [] and s[1]["deps"] == []          # essay and pictures at the same time
    assert sorted(s[2]["deps"]) == [0, 1]                       # the check waits for both
    s = build_steps(["reasoning", "image_generation"])
    assert s[1]["deps"] == [0]                                  # a brand decision still feeds the logo


# ---------- AI planner ----------
def test_merge_only_adds_and_drops_the_fallback():
    u = understand("hmm something about cars")                 # heuristic falls back to reasoning
    m = merge(u, ["writing", "image_generation", "bogus"], {"images": 2}, "ai+heuristic")
    assert m.capabilities == ["writing", "image_generation"] and m.counts == {"images": 2}
    u = understand(ASK)
    m = merge(u, ["writing"], {"images": 3}, "ai+heuristic")
    assert "image_generation" in m.capabilities and m.counts["images"] == 2   # never removes, user's number wins


def test_ai_planner_adds_a_part_the_words_missed(live):
    c, h, install = live
    install()
    reply = {"choices": [{"message": {"content": json.dumps({"parts": ["writing", "image_generation"], "images": 2, "words": 300})}}]}
    seen = []
    ai_understanding.TRANSPORT = httpx.MockTransport(lambda r: (seen.append(str(r.url)), httpx.Response(200, json=reply))[1])
    t = c.post("/api/tasks", json={"objective": "a short piece on old cars, with pictures"}, headers=h).json()
    d = c.get(f"/api/tasks/{t['id']}", headers=h).json()
    caps = [s["capability"] for s in d["subtasks"]]
    assert "writing" in caps and "image_generation" in caps and "groq" in seen[0]


def test_ai_planner_failure_keeps_the_heuristic_plan(live):
    c, h, install = live
    install()   # the conftest transport answers 503 for every provider
    t = c.post("/api/tasks", json={"objective": ASK}, headers=h).json()
    caps = [s["capability"] for s in c.get(f"/api/tasks/{t['id']}", headers=h).json()["subtasks"]]
    assert caps == ["writing", "image_generation", "validation"]


def test_parse_ignores_junk():
    assert ai_understanding.parse('sure! {"parts": ["writing", "x"], "images": 99, "words": -1}') == (["writing"], {"images": 4})


# ---------- the check fixes what is missing ----------
def _sub(cap, pos):
    return Subtask(capability=cap, position=pos, depends_on=[], status="done")


def test_revision_plan_adds_missing_and_redoes_named_parts():
    img, val = _sub("image_generation", 0), _sub("validation", 1)
    add, redo = _revision_plan(["The 500-word essay on cars is completely missing",
                                "There is still only one photo provided instead of the required two"], [img, val], [img])
    assert add == ["writing"] and redo == [img]
    w, img2 = _sub("writing", 0), _sub("image_generation", 1)
    add, redo = _revision_plan(["Too vague"], [w, img2, val], [w, img2])
    assert add == [] and redo == [img2]                         # nothing named: redo the last step


def test_check_adds_the_missing_essay_end_to_end(live):
    c, h, install = live

    def fn(tool, cap, n):
        if cap == "validation":
            return AdapterResult(json.dumps({"passed": n > 0, "issues": ["The essay is completely missing"]}))
        if cap == "image_generation":
            return AdapterResult("1 image", {"images": [{"mime": "image/png", "b64": "QUJD"}]})
    f = install(fn)
    tid, _, _ = run(c, h, "give me a photo of a red sports car")
    d = c.get(f"/api/tasks/{tid}", headers=h).json()
    assert d["status"] == "done" and "writing" in [s["capability"] for s in d["subtasks"]]
    assert [cap for _, cap in f.calls].count("writing") == 1
    assert c.get(f"/api/tasks/{tid}/result", headers=h).json()["validation"]["passed"] is True


def test_essay_and_two_photos_end_to_end(live):
    c, h, install = live

    def fn(tool, cap, n):
        if cap == "image_generation":
            return AdapterResult("img", {"images": [{"mime": "image/png", "b64": "QUJD"}]})
        if cap == "writing":
            return AdapterResult("Cars changed the world. " * 10)
    install(fn)
    tid, _, _ = run(c, h, ASK)
    r = c.get(f"/api/tasks/{tid}/result", headers=h).json()
    assert r["kind"] == "document" and "Cars changed the world" in r["markdown"] and r["images"]


# ---------- image tools ----------
def test_image_prompt_skips_the_essay_and_pollinations_makes_each_picture():
    pkg = Package(objective=ASK, requirements=["write a 500 word essay on cars", "also give two photos of car"], image_count=2)
    prompt = providers._image_prompt(pkg)
    assert "photos of car" in prompt and "essay" not in prompt
    urls = []
    providers.TRANSPORT = httpx.MockTransport(lambda r: (urls.append(str(r.url)), httpx.Response(200, content=b"PNG", headers={"content-type": "image/png"}))[1])
    try:
        from app.models import Tool
        t = Tool(id="p", name="P", provider="pollinations", capabilities=[], config={"model": "flux"}, adapter="pollinations_images")
        res = providers.PollinationsImages().run(pkg, t, None, "image_generation")
    finally:
        providers.TRANSPORT = None
    assert len(res.data["images"]) == 2 and len(urls) == 2 and "variation" in urls[1]


def test_pollinations_waits_out_the_free_limit_for_the_second_picture(monkeypatch):
    calls, waits = [], []
    monkeypatch.setattr(providers, "sleep", waits.append)

    def handler(r):
        calls.append(1)
        if len(calls) == 2:  # the second picture hits "1 image every 45 seconds"
            return httpx.Response(402, json={"error": {"message": "Free limit reached. Retry after 26s"}})
        return httpx.Response(200, content=b"PNG", headers={"content-type": "image/png"})
    providers.TRANSPORT = httpx.MockTransport(handler)
    try:
        from app.models import Tool
        t = Tool(id="p", name="P", provider="pollinations", capabilities=[], config={}, adapter="pollinations_images")
        res = providers.PollinationsImages().run(Package(objective="two photos of car", image_count=2), t, None, "image_generation")
    finally:
        providers.TRANSPORT = None
    assert len(res.data["images"]) == 2 and waits == [27] and len(calls) == 3
