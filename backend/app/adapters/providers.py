"""Provider adapters.

The adapters deliberately use plain HTTPS so the orchestration layer stays provider-neutral.
Free/low-cost development providers are included alongside the original paid adapters:
Gemini, Groq, Hugging Face Inference Providers, and a local Stable Diffusion WebUI endpoint.
"""
import json
import re
import time
from collections.abc import Iterator

import httpx
from ..config import get_settings
from .base import Adapter, AdapterResult, FatalError, RetryableError

sleep = time.sleep  # tests replace this so rate-limit waits take no time

TRANSPORT: httpx.BaseTransport | None = None  # tests inject a MockTransport


def _client() -> httpx.Client:
    return httpx.Client(timeout=get_settings().provider_timeout, transport=TRANSPORT)


def _call(method: str, url: str, **kw) -> dict:
    try:
        with _client() as c:
            r = c.request(method, url, **kw)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise RetryableError(f"the connection failed ({type(e).__name__})")
    if r.status_code in (401, 403):
        raise FatalError("the provider rejected the saved API key")
    if r.status_code == 429 or r.status_code >= 500:
        raise RetryableError(f"the provider is busy or down (status {r.status_code})" + _detail(r))
    if r.status_code >= 400:
        raise FatalError(f"the provider refused the request (status {r.status_code})" + _detail(r))
    try:
        return r.json()
    except ValueError:
        raise RetryableError("the provider sent an unreadable reply")


def _detail(r: httpx.Response) -> str:
    """The provider's own reason (e.g. Gemini's 'quota exceeded ... limit: 0'), shortened."""
    try:
        msg = str(r.json().get("error", {}).get("message", "")).split("\n")[0][:180]
    except Exception:
        msg = ""
    return f": {msg}" if msg else ""


def _stream_openai_sse(url: str, headers: dict, payload: dict) -> Iterator[str]:
    """Stream text deltas from an OpenAI-compatible chat endpoint (Groq, Hugging Face).

    Yields each `choices[0].delta.content` chunk as it arrives. Any network or parse
    problem ends the generator quietly — the engine falls back to run() for the real
    result, so a failed stream only costs the live typing effect, never the answer.
    """
    payload = {**payload, "stream": True}
    try:
        with _client() as c:
            with c.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code >= 400:
                    return
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        choices = json.loads(data).get("choices") or []
                        delta = (choices[0].get("delta") or {}).get("content") if choices else None
                    except (ValueError, IndexError, KeyError):
                        continue
                    if delta:
                        yield delta
    except (httpx.TimeoutException, httpx.TransportError):
        return


SYSTEM = ("You are one step in a multi-step workflow. Do only the task named under 'Your task', using only the context given. "
          "Return the work product itself, no preamble. If you write code, use fenced blocks with a file name after the language, "
          "like ```python app.py. If a numeric comparison helps, add one ```json block shaped {\"title\":\"\",\"labels\":[],\"values\":[]}." )
VALIDATE = ("You check another step's work against the objective and requirements. Reply with JSON only, no prose: "
            "{\"passed\": true|false, \"issues\": [\"short, specific problems\"]}.")


def _prompt_messages(pkg, capability: str):
    return [
        {"role": "system", "content": VALIDATE if capability == "validation" else SYSTEM},
        {"role": "user", "content": pkg.to_prompt()},
    ]


class AnthropicMessages(Adapter):
    def run(self, pkg, tool, api_key, capability):
        d = _call("POST", "https://api.anthropic.com/v1/messages",
                  headers={"x-api-key": api_key or "", "anthropic-version": "2023-06-01", "content-type": "application/json"},
                  json={"model": tool.config["model"], "max_tokens": 4096,
                        "system": VALIDATE if capability == "validation" else SYSTEM,
                        "messages": [{"role": "user", "content": pkg.to_prompt()}]})
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        if not text:
            raise RetryableError("the model returned no text")
        u = d.get("usage", {})
        return AdapterResult(text, {}, u.get("input_tokens", 0), u.get("output_tokens", 0))


class GeminiGenerate(Adapter):
    """Google Gemini GenerateContent adapter, optionally with Google Search grounding."""
    streams = True

    def _payload(self, pkg, tool, capability):
        payload = {
            "system_instruction": {"parts": [{"text": VALIDATE if capability == "validation" else SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": pkg.to_prompt()}]}],
            "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.2},
        }
        if tool.config.get("google_search"):
            payload["tools"] = [{"google_search": {}}]
        return payload

    def run(self, pkg, tool, api_key, capability):
        payload = self._payload(pkg, tool, capability)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{tool.config['model']}:generateContent"
        d = _call("POST", url, headers={"x-goog-api-key": api_key or "", "content-type": "application/json"}, json=payload)
        candidates = d.get("candidates") or []
        parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
        text = "".join(p.get("text", "") for p in parts if p.get("text"))
        if not text:
            raise RetryableError("Gemini returned no text")
        usage = d.get("usageMetadata", {})
        data = {}
        gm = candidates[0].get("groundingMetadata", {}) if candidates else {}
        chunks = gm.get("groundingChunks") or []
        sources = []
        for ch in chunks:
            web = ch.get("web") or {}
            if web.get("uri"):
                sources.append({"title": web.get("title", web["uri"]), "url": web["uri"], "description": "Google Search grounding source"})
        if sources:
            data["sources"] = sources
        return AdapterResult(text, data, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))

    def stream(self, pkg, tool, api_key, capability):
        """Stream Gemini text deltas via streamGenerateContent?alt=sse. Quiet on any error."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{tool.config['model']}:streamGenerateContent?alt=sse"
        payload = self._payload(pkg, tool, capability)
        try:
            with _client() as c:
                with c.stream("POST", url, headers={"x-goog-api-key": api_key or "", "content-type": "application/json"}, json=payload) as r:
                    if r.status_code >= 400:
                        return
                    for line in r.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            cand = (json.loads(line[5:].strip()).get("candidates") or [])
                            parts = cand[0].get("content", {}).get("parts", []) if cand else []
                        except (ValueError, IndexError, KeyError):
                            continue
                        chunk = "".join(p.get("text", "") for p in parts if p.get("text"))
                        if chunk:
                            yield chunk
        except (httpx.TimeoutException, httpx.TransportError):
            return


class GroqChat(Adapter):
    """Groq's OpenAI-compatible chat completion endpoint."""
    streams = True

    def run(self, pkg, tool, api_key, capability):
        d = _call("POST", "https://api.groq.com/openai/v1/chat/completions",
                  headers={"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"},
                  json={"model": tool.config["model"], "messages": _prompt_messages(pkg, capability),
                        "max_tokens": 4096, "temperature": 0.2})
        choices = d.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
        if not text:
            raise RetryableError("Groq returned no text")
        u = d.get("usage") or {}
        return AdapterResult(text, {}, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))

    def stream(self, pkg, tool, api_key, capability):
        yield from _stream_openai_sse(
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"},
            {"model": tool.config["model"], "messages": _prompt_messages(pkg, capability), "max_tokens": 4096, "temperature": 0.2})


class HuggingFaceChat(Adapter):
    """Hugging Face Inference Providers OpenAI-compatible chat endpoint."""
    streams = True

    def run(self, pkg, tool, api_key, capability):
        d = _call("POST", "https://router.huggingface.co/v1/chat/completions",
                  headers={"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"},
                  json={"model": tool.config["model"], "messages": _prompt_messages(pkg, capability),
                        "max_tokens": 4096, "temperature": 0.2})
        choices = d.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
        if not text:
            raise RetryableError("Hugging Face returned no text")
        u = d.get("usage") or {}
        return AdapterResult(text, {}, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))

    def stream(self, pkg, tool, api_key, capability):
        yield from _stream_openai_sse(
            "https://router.huggingface.co/v1/chat/completions",
            {"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"},
            {"model": tool.config["model"], "messages": _prompt_messages(pkg, capability), "max_tokens": 4096, "temperature": 0.2})


class BraveSearch(Adapter):
    def run(self, pkg, tool, api_key, capability):
        d = _call("GET", "https://api.search.brave.com/res/v1/web/search", params={"q": pkg.objective[:200], "count": 8},
                  headers={"X-Subscription-Token": api_key or "", "Accept": "application/json"})
        rows = (d.get("web") or {}).get("results", [])
        if not rows:
            raise RetryableError("the search returned no results")
        src = [{"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")} for r in rows]
        return AdapterResult("\n".join(f"- {s['title']}: {s['description']} ({s['url']})" for s in src), {"sources": src})


def _image_prompt(pkg, variant: int = 0, limit: int = 900) -> str:
    """What to draw. A mixed ask ("write an essay and give two photos") should not send the
    essay instruction to the image model, so keep the parts that talk about pictures, plus the
    newest follow-ups (change requests), and fall back to the whole objective."""
    import re
    from ..understanding import IMG_NOUN
    follow = [r for r in pkg.requirements if r.startswith("Change requested by the user")]
    visual = [r for r in pkg.requirements if re.search(IMG_NOUN, r.lower()) and r not in follow]
    base = " ".join(visual) if visual else pkg.objective
    prompt = " ".join([base, *pkg.decisions[-1:], *follow])
    if len(prompt) > limit:
        prompt = base[: limit // 3] + " " + " ".join([*pkg.decisions[-1:], *follow])[-(limit * 2 // 3):]
    if variant:
        prompt += f" (variation {variant + 1}: a different scene, angle and composition)"
    return prompt


class LocalStableDiffusion(Adapter):
    """Local/open-source image generation through an Automatic1111/Forge-compatible API.

    Start a local WebUI with its API enabled and expose /sdapi/v1/txt2img. On Docker Desktop
    for Mac, use http://host.docker.internal:7860/sdapi/v1/txt2img.
    """
    def run(self, pkg, tool, api_key, capability):
        base = get_settings().local_image_api_url or tool.config.get("url", "http://host.docker.internal:7860/sdapi/v1/txt2img")
        prompt = "\n".join([pkg.objective, *pkg.requirements, *pkg.decisions])[:4000]
        d = _call("POST", base, headers={"Content-Type": "application/json"},
                  json={"prompt": prompt, "negative_prompt": "blurry, low quality, distorted, watermark",
                        "steps": 20, "width": 768, "height": 768})
        imgs = [{"mime": "image/png", "b64": x} for x in (d.get("images") or []) if x]
        if not imgs:
            raise RetryableError("the local image server returned no image")
        return AdapterResult(f"Generated {len(imgs)} local image(s) for the brief.", {"images": imgs})


class GeminiImages(Adapter):
    """Image generation with Google Gemini.

    Uses the model's :generateContent endpoint and asks for an IMAGE modality. Image-capable
    Gemini models return the picture as inline base64 data, which we pass through unchanged in the
    same {mime, b64} shape the result renderer and the local/OpenAI image adapters already use.
    Reuses the same Gemini API key saved under the 'gemini' provider — no extra key needed.
    """
    def run(self, pkg, tool, api_key, capability):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{tool.config['model']}:generateContent"
        want = getattr(pkg, "image_count", 1)
        imgs, t_in, t_out = [], 0, 0
        for i in range(want):
            payload = {
                "contents": [{"role": "user", "parts": [{"text": _image_prompt(pkg, i, 4000)}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            }
            try:
                d = _call("POST", url, headers={"x-goog-api-key": api_key or "", "content-type": "application/json"}, json=payload)
            except RetryableError:
                if imgs:
                    break  # keep the pictures we already have
                raise
            candidates = d.get("candidates") or []
            parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
            for p in parts:
                blob = p.get("inlineData") or p.get("inline_data") or {}
                b64 = blob.get("data")
                if b64:
                    imgs.append({"mime": blob.get("mimeType") or blob.get("mime_type") or "image/png", "b64": b64})
            usage = d.get("usageMetadata", {})
            t_in, t_out = t_in + usage.get("promptTokenCount", 0), t_out + usage.get("candidatesTokenCount", 0)
        if not imgs:
            raise RetryableError("Gemini returned no image")
        return AdapterResult(f"Generated {len(imgs)} of {want} image(s) for the brief.", {"images": imgs[:want]}, t_in, t_out)


class PollinationsImages(Adapter):
    """Free, keyless image generation (pollinations.ai). Used as the backup when Gemini's image
    quota is empty. Note: the prompt is sent to a public third-party service."""
    def run(self, pkg, tool, api_key, capability):
        import base64
        from urllib.parse import quote
        import random
        size = int(tool.config.get("size", 1024))
        want = getattr(pkg, "image_count", 1)
        imgs, i, tries = [], 0, 0
        with _client() as c:
            while i < want:
                url = f"https://image.pollinations.ai/prompt/{quote(_image_prompt(pkg, i), safe='')}"
                try:
                    r = c.get(url, params={"width": size, "height": size, "nologo": "true", "seed": random.randint(1, 10**6),
                                           "model": tool.config.get("model", "flux")})
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    if imgs:
                        break  # keep the pictures we already have
                    raise RetryableError(f"the connection failed ({type(e).__name__})")
                mime = r.headers.get("content-type", "").split(";")[0]
                if r.status_code == 402 and tries < 3:
                    # free tier: "1 image every 45 seconds per IP. Retry after 26s". Wait it out, then go on.
                    m = re.search(r"after (\d+)\s*s", r.text)
                    wait = int(m.group(1)) + 1 if m else 46
                    if wait <= 60:
                        sleep(wait)
                        tries += 1
                        continue
                if r.status_code in (402, 429) or r.status_code >= 500:
                    if imgs:
                        break  # keep the pictures we already have
                    raise RetryableError(f"the free image service is busy or rate-limited (status {r.status_code})")
                if r.status_code >= 400:
                    raise FatalError(f"the image service refused the request (status {r.status_code})")
                if mime.startswith("image/") and r.content:
                    imgs.append({"mime": mime, "b64": base64.b64encode(r.content).decode()})
                i += 1
        if not imgs:
            raise RetryableError("the image service returned no image")
        return AdapterResult(f"Generated {len(imgs)} of {want} image(s) for the brief.", {"images": imgs})


class OpenAIImages(Adapter):
    def run(self, pkg, tool, api_key, capability):
        prompt = "\n".join([pkg.objective, *pkg.requirements, *pkg.decisions])[:4000]
        d = _call("POST", "https://api.openai.com/v1/images/generations",
                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                  json={"model": tool.config["model"], "prompt": prompt, "size": "1024x1024"})
        imgs = []
        for i in d.get("data", []):
            if i.get("b64_json"):
                imgs.append({"mime": "image/png", "b64": i["b64_json"]})
            elif str(i.get("url", "")).startswith("https://"):
                imgs.append({"url": i["url"]})
        if not imgs:
            raise RetryableError("no image came back")
        return AdapterResult(f"Generated {len(imgs)} image(s) for the brief.", {"images": imgs})
