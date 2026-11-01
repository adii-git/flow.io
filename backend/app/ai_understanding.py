"""AI planner: a fast model reads the ask and lists every part it needs.

The keyword heuristic misses parts it has no word for ("essay" once had none), so a task could
silently lose half of what the user asked. Here one quick JSON call (Groq first, it is the fastest;
Gemini Flash-Lite second) names the parts and their numbers. The result is MERGED into the
heuristic (understanding.merge), so the AI can only add steps, never remove one, and any failure,
timeout or odd reply simply leaves the heuristic plan as it was.
"""
import json
import logging
import re
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .models import ToolConnection
from .security import decrypt_secret
from .understanding import ORDER, Understanding, merge

log = logging.getLogger("conduit.ai_understanding")
TIMEOUT = 8.0  # planning must stay quick; past this we use the heuristic plan
TRANSPORT: httpx.BaseTransport | None = None  # tests swap in a MockTransport

PROMPT = (
    "Split the user's request into the work parts it needs. Allowed parts: "
    "web_research (look up current facts), long_context_documents (read/summarise long material), "
    "reasoning (compare, decide, plan, recommend), writing (essays, articles, stories, captions, emails, any prose), "
    "code_generation (write code or an app), code_execution (run code, analyse data, charts), "
    "file_processing (work with uploaded files), image_generation (make pictures, photos, logos, posters). "
    "Include every part the request asks for and nothing it does not. "
    'Reply with JSON only: {"parts": ["writing", "image_generation"], "images": 2, "words": 500}. '
    "Use images/words only when the request names a number, else 0."
)


def _key(db: Session, user_id, provider: str) -> str | None:
    row = db.scalar(select(ToolConnection).where(ToolConnection.user_id == user_id, ToolConnection.provider == provider))
    return decrypt_secret(row.encrypted_key) if row else None


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, transport=TRANSPORT)


def _ask_groq(key: str, objective: str) -> str:
    with _client() as c:
        r = c.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                   json={"model": "openai/gpt-oss-20b", "temperature": 0, "max_tokens": 300,
                         "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": objective[:4000]}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _ask_gemini(key: str, objective: str) -> str:
    with _client() as c:
        r = c.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
                   headers={"x-goog-api-key": key},
                   json={"system_instruction": {"parts": [{"text": PROMPT}]},
                         "contents": [{"role": "user", "parts": [{"text": objective[:4000]}]}],
                         "generationConfig": {"temperature": 0, "maxOutputTokens": 300, "responseMimeType": "application/json"}})
        r.raise_for_status()
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])


def parse(text: str) -> tuple[list[str], dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    j = json.loads(m.group(0)) if m else {}
    parts = [p for p in j.get("parts", []) if isinstance(p, str) and p in ORDER]
    counts = {}
    for k, hi in (("images", 4), ("words", 5000)):
        v = j.get(k)
        if isinstance(v, (int, float)) and v > 0:
            counts[k] = min(int(v), hi)
    return parts, counts


def refine(db: Session, user_id, objective: str, u: Understanding) -> Understanding:
    """Returns u plus whatever the AI found. Never raises."""
    if get_settings().execution_mode == "demo":
        return u
    for provider, ask in (("groq", _ask_groq), ("gemini", _ask_gemini)):
        try:
            key = _key(db, user_id, provider)
            if not key:
                continue
            parts, counts = parse(ask(key, objective))
            if parts:
                return merge(u, parts, counts, "ai+heuristic")
        except Exception:  # any provider/network/JSON problem: try the next one, then keep the heuristic
            log.info("AI planner via %s failed; keeping the heuristic plan", provider, exc_info=True)
    return u
