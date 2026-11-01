from app.understanding import understand


def caps(s): return understand(s).capabilities


def test_research_brief():
    u = understand("Compare three competitors in the EU e-bike market and write a one-page brief")
    assert u.capabilities == ["web_research", "long_context_documents", "reasoning"] and u.task_type == "research"
    assert len(u.requirements) == 2 and u.source == "heuristic"


def test_code_and_data():
    c = caps("Build a Python script that cleans a sales CSV and charts monthly revenue")
    assert "code_generation" in c and "code_execution" in c and "file_processing" in c


def test_image_and_fallback():
    assert understand("Design a logo for a streetwear brand").task_type == "image"
    assert caps("hmm") == ["reasoning"]


def test_many_capabilities_is_project():
    assert understand("Research competitors, build an app, design a logo and write a report").task_type == "project"


def test_result_is_cached_but_isolated():
    # same objective hits the cache, yet each call returns a fresh, independently mutable object
    from app.understanding import _analyze
    _analyze.cache_clear()
    a = understand("Design a logo for a streetwear brand")
    before = _analyze.cache_info()
    b = understand("Design a logo for a streetwear brand")
    after = _analyze.cache_info()
    assert after.hits == before.hits + 1  # the second call was served from cache
    assert a.capabilities == b.capabilities and a is not b
    a.capabilities.append("mutated")
    assert "mutated" not in b.capabilities  # a cached entry is never shared by reference
