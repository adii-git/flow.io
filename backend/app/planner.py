"""Planner: turns understood capabilities into a step graph. Gathering steps run in parallel; the rest chain."""
GATHER = {"file_processing", "web_research", "long_context_documents"}
# Side steps need only the gathered material, not the text chain, so they run beside it:
# an essay and its pictures are made at the same time instead of one after the other.
SIDE = {"image_generation"}


def build_steps(caps: list[str]) -> list[dict]:
    """Returns [{capability, deps: [positions]}]; validation is always last and depends on every leaf."""
    steps = [{"capability": c, "deps": []} for c in [*caps, "validation"]]
    gather = [i for i, s in enumerate(steps[:-1]) if s["capability"] in GATHER]
    side = [i for i, s in enumerate(steps[:-1]) if s["capability"] in SIDE]
    chain = [i for i, s in enumerate(steps[:-1]) if s["capability"] not in GATHER | SIDE]
    for n, i in enumerate(chain):
        steps[i]["deps"] = gather[:] if n == 0 else [chain[n - 1]]
    for i in side:
        # a reasoning decision (brand direction, style) still feeds the picture; plain writing does not
        think = [j for j in chain if steps[j]["capability"] == "reasoning"]
        steps[i]["deps"] = gather[:] + think[-1:]
    needed = {d for s in steps[:-1] for d in s["deps"]}
    steps[-1]["deps"] = [i for i in range(len(steps) - 1) if i not in needed]
    return steps
