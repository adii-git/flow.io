"""Image generation fallback: Gemini's free tier often has no image quota (429), so a free,
keyless tool must be next in line."""
import httpx
import pytest

from app.adapters import FatalError, RetryableError, providers
from app.models import Tool
from tests.test_support import KEY, pkg, tool  # noqa: F401  (pkg is a fixture)


def test_pollinations_returns_image_bytes_as_b64(pkg):
    seen = {}

    def handler(r):
        seen["url"] = str(r.url)
        return httpx.Response(200, content=b"\xff\xd8JPEGDATA", headers={"content-type": "image/jpeg"})
    providers.TRANSPORT = httpx.MockTransport(handler)
    try:
        out = providers.PollinationsImages().run(pkg, Tool(id="p", config={"model": "flux", "size": 512}), None, "image_generation")
    finally:
        providers.TRANSPORT = None
    assert out.data["images"] == [{"mime": "image/jpeg", "b64": "/9hKUEVHREFUQQ=="}]
    assert "image.pollinations.ai/prompt/Do%20X" in seen["url"] and "width=512" in seen["url"]


@pytest.mark.parametrize("resp,exc", [
    (httpx.Response(429), RetryableError),
    (httpx.Response(400), FatalError),
    (httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}), RetryableError),
])
def test_pollinations_errors(pkg, resp, exc):
    providers.TRANSPORT = httpx.MockTransport(lambda r: resp)
    try:
        with pytest.raises(exc):
            providers.PollinationsImages().run(pkg, Tool(id="p", config={}), None, "image_generation")
    finally:
        providers.TRANSPORT = None


def test_429_shows_the_providers_reason(pkg):
    body = {"error": {"message": "You exceeded your current quota. limit: 0, model: gemini-2.5-flash-image"}}
    providers.TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(429, json=body))
    try:
        with pytest.raises(RetryableError, match="limit: 0"):
            providers.GeminiImages().run(pkg, tool("gemini_images", "gemini-2.5-flash-image"), KEY, "image_generation")
    finally:
        providers.TRANSPORT = None


def test_free_image_tool_is_the_fallback_for_gemini_image():
    from app.registry.loader import load_specs
    from app.routing import route_step
    tools = [Tool(**{k: v for k, v in s.model_dump().items() if k in Tool.__table__.columns}) for s in load_specs()]
    d = route_step("image_generation", tools, ready_providers={"gemini", "groq"})
    assert d.tool_id == "gemini-image"
    assert "pollinations-image" in d.alternatives
    # with no Gemini key at all, the free tool is chosen first
    assert route_step("image_generation", tools, ready_providers=set()).tool_id == "pollinations-image"
