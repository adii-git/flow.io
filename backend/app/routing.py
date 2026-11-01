"""Tool Router: pure scoring over registry rows. No provider names appear here; everything comes from metadata."""
from dataclasses import dataclass, field

QUALITY = {"high": 1.0, "mid": 0.7, "low": 0.4}  # proxy: pricier tiers are assumed more capable
COST = {"low": 1.0, "mid": 0.6, "high": 0.2}
SPEED = {"fast": 1.0, "mid": 0.6, "slow": 0.2}
# (quality, cost, speed) weights per capability
PROFILE = {
    "reasoning": (.6, .2, .2), "writing": (.6, .2, .2), "long_context_documents": (.5, .25, .25), "code_generation": (.65, .2, .15),
    "file_processing": (.2, .45, .35), "web_research": (.3, .3, .4), "image_generation": (.6, .25, .15),
    "validation": (.3, .3, .4), "code_execution": (.2, .4, .4),
}
PRIORITY_BOOST = {"balanced": (1, 1, 1), "quality": (2, 1, 1), "cheap": (1, 2, 1), "fast": (1, 1, 2)}
LABEL = {
    "reasoning": "reasoning", "writing": "writing", "long_context_documents": "long documents", "web_research": "web research",
    "code_generation": "writing code", "code_execution": "running code", "image_generation": "image creation",
    "file_processing": "file handling", "validation": "checking results",
}


@dataclass
class Decision:
    tool_id: str | None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)  # fallback order
    blockers: list[str] = field(default_factory=list)  # providers whose key is missing
    score: float = 0.0


def _usable(t) -> bool:
    return t.availability == "available"


def route_step(capability: str, tools: list, *, ready_providers: set[str], demo: bool = False, need_tokens: int = 0,
               needs_files: bool = False, needs_images: bool = False, priority: str = "balanced",
               avoid_tool: str | None = None, fast_step: bool = False) -> Decision:
    cands = [t for t in tools if _usable(t) and capability in t.capabilities]
    if not cands:
        return Decision(None, reasons=[f"No available tool can do {LABEL.get(capability, capability)} yet."])
    q, c, s = (w * b for w, b in zip(PROFILE.get(capability, (.4, .3, .3)), PRIORITY_BOOST.get(priority, (1, 1, 1))))
    total = q + c + s
    scored = []
    for t in cands:
        if t.context_window and need_tokens > 0.8 * t.context_window:
            continue  # cannot hold what this step must read
        sc = (q * QUALITY[t.cost_class] + c * COST[t.cost_class] + s * SPEED[t.speed_class]) / total
        if t.context_window:
            sc += 0.1 * (1 - min(need_tokens / t.context_window, 1))
        if needs_files and not t.supports_files: sc -= .3
        if needs_images and not t.supports_images: sc -= .3
        if len(t.capabilities) <= 2: sc += .1
        # Latency-sensitive steps (planning helpers, validation) prefer the fastest, cheapest tool
        # so the whole run feels quick — the heavy thinking still goes to the best model for its step.
        if fast_step:
            sc += .15 * SPEED[t.speed_class] + .05 * COST[t.cost_class]
        keyless = t.requires_key and not demo and t.provider not in ready_providers
        if keyless: sc -= .85
        else: sc += .25  # In live mode, strongly prefer a connected provider over an otherwise similar blocked one.
        if avoid_tool and t.id == avoid_tool: sc -= .2
        scored.append((sc, t, keyless))
    if not scored:
        return Decision(None, reasons=["The material is too large for every available tool. Trim it or split the task."])
    scored.sort(key=lambda x: (-x[0], x[1].id))
    top, tool, keyless = scored[0]
    second = scored[1][0] if len(scored) > 1 else None
    conf = 0.8 if second is None else min(0.95, 0.55 + max(top - second, 0) / max(abs(top), 1e-6))
    why = [f"Built for {LABEL.get(capability, capability)}"]
    if len(tool.capabilities) <= 2: why.append("A specialist that does little else")
    if tool.cost_class == "high" and q >= c and q >= s: why.append("The strongest option for this step")
    if tool.speed_class == "fast": why.append("Fast")
    if tool.cost_class == "low": why.append("Low cost")
    if tool.context_window and need_tokens: why.append(f"Fits the roughly {need_tokens:,} tokens of context this step needs")
    if avoid_tool and tool.id != avoid_tool: why.append("Different from the tool that wrote the result, so the check is independent")
    if keyless: why.append(f"Needs a {tool.provider} key before it can run")
    blockers = [tool.provider] if keyless else []
    return Decision(tool.id, round(conf, 2), why, [t.id for _, t, _ in scored[1:]], blockers, round(top, 3))
