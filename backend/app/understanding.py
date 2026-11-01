"""Task Understanding, Phase 3 version: transparent keyword heuristics, stored with source="heuristic".
Replaced by an LLM-backed agent later; the output shape stays the same."""
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

ORDER = ["file_processing", "web_research", "long_context_documents", "reasoning", "writing",
         "code_generation", "code_execution", "image_generation"]
# "write"/"explain" alone is weak: "write a brief" is already a reasoning/document job and
# "write a script" is code. It only adds a writing step when no other text step was found.
WEAK_WRITING = ["write", "writ", "explain", "tell me", "describ"]
TEXT_CAPS = {"reasoning", "long_context_documents", "code_generation", "writing"}
NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "couple": 2, "pair": 2}
MAX_IMAGES = 4

KEYWORDS: dict[str, list[str]] = {
    "file_processing": ["csv", "excel", "spreadsheet", "upload", "file", "extract", "convert", "ocr", "xlsx"],
    "web_research": ["research", "compet", "market", "source", "find", "news", "trend", "survey", "study", "look up", "benchmark", "landscape"],
    "long_context_documents": ["pdf", "contract", "report", "document", "summar", "memo", "paper", "transcript", "brief", "whitepaper"],
    "writing": ["essay", "article", "blog", "story", "stories", "poem", "caption", "email", "letter", "paragraph", "word",
                "speech", "tweet", "newsletter", "biography", "lyrics", "copywrit", "headline", "bio "],
    "reasoning": ["plan", "strateg", "decid", "compar", "pricing", "launch", "evaluat", "choose", "priorit", "recommend", "trade-off", "pros and cons"],
    "code_generation": ["api", "code", "app", "build", "script", "bug", "function", "backend", "frontend", "website", "python", "javascript", "program", "implement"],
    "code_execution": ["clean", "parse", "chart", "plot", "calculate", "analy", "transform", "csv", "run "],
    "image_generation": ["image", "logo", "poster", "photo", "illustrat", "picture", "visual", "mockup", "icon"],
}

LABELS = {
    "file_processing": "File processing", "web_research": "Web research", "long_context_documents": "Document reading",
    "reasoning": "Reasoning", "writing": "Writing", "code_generation": "Code writing", "code_execution": "Code running",
    "image_generation": "Image creation", "validation": "Validation",
}
STEP_TEXT = {
    "file_processing": "Read and prepare the files this task depends on.",
    "web_research": "Gather current facts and sources.",
    "long_context_documents": "Read long material and pull out what matters.",
    "reasoning": "Weigh the options and reach a decision.",
    "writing": "Write the full text asked for, in the requested length and form.",
    "code_generation": "Write the code the result needs.",
    "code_execution": "Run code to process data or test the result.",
    "image_generation": "Create the visual assets.",
    "validation": "Check the result against your requirements.",
}


@dataclass
class Understanding:
    source: str
    title: str
    task_type: str
    requirements: list[str]
    capabilities: list[str]
    counts: dict = field(default_factory=dict)  # {"images": 2, "words": 500} when the ask names them

    def to_dict(self) -> dict:
        return asdict(self)


def _matches(text: str, words: list[str], key: str) -> bool:
    return (key in text) if " " in key or key.endswith(" ") else any(w.startswith(key) for w in words)


IMG_NOUN = r"(?:photos?|images?|pictures?|pics?|illustrations?|posters?|logos?|icons?|visuals?|mockups?|wallpapers?)"


def counts(text: str) -> dict:
    """Numbers the ask names: how many images, how many words. Missing means 'not said'."""
    t = " ".join(text.lower().split())
    out: dict = {}
    m = re.search(r"\b(\d{1,2}|" + "|".join(NUM_WORDS) + r")\s+(?:[a-z\-]+\s+){0,2}?" + IMG_NOUN + r"\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM_WORDS[m.group(1)]
        if n > 0:
            out["images"] = min(n, MAX_IMAGES)
    w = re.search(r"(\d{2,5})\s*[- ]?\s*words?\b", t)
    if w:
        out["words"] = min(int(w.group(1)), 5000)
    return out


def step_text(cap: str, c: dict) -> str:
    """The step's instruction, with the user's numbers folded in so the model sees them as the task."""
    base = STEP_TEXT[cap]
    if cap == "writing" and c.get("words"):
        return f"{base} Write about {c['words']} words (stay within 10% of that)."
    if cap == "image_generation" and c.get("images", 1) > 1:
        return f"Create {c['images']} different images for the brief."
    return base


def _task_type(caps: list[str]) -> str:
    if len(caps) >= 4:
        return "project"
    # text + pictures: show the text as the main answer; images render under it for any kind
    if "writing" in caps:
        return "document"
    for cap, kind in [("image_generation", "image"), ("code_generation", "code"), ("code_execution", "analysis"),
                      ("file_processing", "analysis"), ("web_research", "research"), ("long_context_documents", "document")]:
        if cap in caps:
            return kind
    return "strategy"


def detect(text: str) -> list[str]:
    """Capabilities a piece of text clearly asks for, with no fallback. Used for follow-ups:
    'make the background blue' matches nothing, so it adds no new step."""
    t = " ".join(text.lower().split()) + " "
    words = re.findall(r"[a-z0-9\-]+", t)
    return _with_weak_writing(t, words, [c for c in ORDER if any(_matches(t, words, k) for k in KEYWORDS[c])])


def _with_weak_writing(text: str, words: list[str], caps: list[str]) -> list[str]:
    if "writing" not in caps and not (TEXT_CAPS & set(caps)) and any(_matches(text, words, k) for k in WEAK_WRITING):
        caps = [c for c in ORDER if c in {*caps, "writing"}]
    return caps


def merge(u: "Understanding", extra_caps: list[str], extra_counts: dict, source: str) -> "Understanding":
    """Adds what a second reader (the AI planner) found. Never removes a part the heuristic found,
    so a weak AI answer can only add steps, not drop one."""
    caps = [c for c in ORDER if c in {*u.capabilities, *(x for x in extra_caps if x in ORDER)}]
    if len(caps) > 1 and "reasoning" in caps and u.capabilities == ["reasoning"] and "reasoning" not in extra_caps:
        caps.remove("reasoning")  # 'reasoning' was only the heuristic's no-match fallback
    c = {**extra_counts, **u.counts}  # numbers the user typed beat the AI's guess
    return Understanding(source, u.title, _task_type(caps), list(u.requirements), caps, c)


@lru_cache(maxsize=512)
def _analyze(objective: str) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """Pure, deterministic analysis of an objective. Cached because the same prompt
    (common on re-runs and near-duplicate asks) always yields the same plan, so we skip
    re-scanning the keyword tables. Returns immutable tuples; the caller copies them into
    a fresh Understanding so a cached entry is never mutated."""
    text = " ".join(objective.lower().split()) + " "
    words = re.findall(r"[a-z0-9\-]+", text)
    caps = _with_weak_writing(text, words, [c for c in ORDER if any(_matches(text, words, k) for k in KEYWORDS[c])]) or ["reasoning"]
    clauses = [c.strip(" .,:;") for c in re.split(r"[.;\n]|,? and then |, and | and ", objective) if len(c.strip()) > 3]
    title = objective.strip().split("\n")[0][:70].rstrip(" .,:;")
    reqs = tuple(clauses[:6]) or (objective.strip()[:200],)
    return title, _task_type(caps), reqs, tuple(caps)


def understand(objective: str) -> Understanding:
    title, task_type, reqs, caps = _analyze(objective)
    return Understanding("heuristic", title, task_type, list(reqs), list(caps), counts(objective))
