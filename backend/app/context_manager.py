"""Context Manager: builds the minimal Context Package for one step and records what was sent and held back."""
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ContextItem, ContextTransfer, Subtask, Task, Tool

POLICY: dict[str, set[str]] = {
    "web_research": {"objective", "requirement", "constraint"},
    "file_processing": {"objective", "requirement", "file"},
    "long_context_documents": {"objective", "requirement", "file", "research"},
    "reasoning": {"objective", "requirement", "constraint", "research", "file", "output"},
    "writing": {"objective", "requirement", "constraint", "research", "decision", "file", "output"},
    "code_generation": {"objective", "requirement", "constraint", "decision", "research", "output", "file"},
    "code_execution": {"objective", "requirement", "output"},
    "image_generation": {"objective", "requirement", "constraint", "decision"},
    "validation": {"objective", "requirement", "constraint", "output", "decision", "research"},
}
PRIORITY = ["objective", "requirement", "constraint", "decision", "research", "output", "file"]
FROM_STEPS = {"output", "research", "decision"}
LABEL = {"file_processing": "File processing", "web_research": "Web research", "long_context_documents": "Document reading",
         "reasoning": "Reasoning", "writing": "Writing", "code_generation": "Code writing", "code_execution": "Code running",
         "image_generation": "Image creation", "validation": "Validation"}


@dataclass
class Package:
    objective: str = ""
    requirements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    research: list[str] = field(default_factory=list)
    previous_outputs: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    current_state: str = ""
    next_task: str = ""
    image_count: int = 1  # how many pictures the ask named (image steps only)
    sent: list[dict] = field(default_factory=list)
    withheld: list[dict] = field(default_factory=list)

    def chars(self) -> int:
        return sum(s["chars"] for s in self.sent)

    def to_prompt(self) -> str:
        def block(title, items): return f"## {title}\n" + "\n".join(f"- {i}" for i in items) + "\n" if items else ""
        parts = [f"## Objective\n{self.objective}\n", block("Requirements", self.requirements), block("Constraints", self.constraints),
                 block("Decisions so far", self.decisions), block("Research", self.research)]
        for o in self.previous_outputs:
            parts.append(f"## Output of: {o['label']}\n{o['text']}\n")
        for f in self.files:
            parts.append(f"## File: {f['name']}\n{f['excerpt']}\n")
        parts.append(f"## Where we are\n{self.current_state}\n\n## Your task\n{self.next_task}\n")
        return "\n".join(p for p in parts if p)


def ancestors(sub: Subtask, by_id: dict) -> set[str]:
    seen, stack = set(), list(sub.depends_on or [])
    while stack:
        d = stack.pop()
        if d not in seen and d in by_id:
            seen.add(d)
            stack.extend(by_id[d].depends_on or [])
    return seen


def budget_chars(tool: Tool | None) -> int:
    w = tool.context_window if tool else 0
    return min(int(w * 4 * 0.5), 200_000) if w else 12_000


def build_package(db: Session, task: Task, sub: Subtask, subs: list[Subtask], tool: Tool | None = None, persist: bool = True) -> Package:
    by_id = {str(s.id): s for s in subs}
    anc = ancestors(sub, by_id)
    allowed = POLICY.get(sub.capability, {"objective", "requirement"})
    items = db.scalars(select(ContextItem).where(ContextItem.task_id == task.id).order_by(ContextItem.created_at)).all()
    items = sorted(items, key=lambda i: (PRIORITY.index(i.kind) if i.kind in PRIORITY else 99))
    p, left = Package(), budget_chars(tool)
    step_label = LABEL.get(sub.capability, sub.capability)
    for it in items:
        ref = {"item_id": str(it.id), "kind": it.kind, "label": it.label or it.kind}
        if it.kind == "scratch":
            p.withheld.append({**ref, "reason": "Temporary working notes are never passed on"}); continue
        if it.kind not in allowed:
            p.withheld.append({**ref, "reason": f"{step_label} doesn't need this"}); continue
        if it.kind in FROM_STEPS and it.subtask_id and str(it.subtask_id) not in anc:
            p.withheld.append({**ref, "reason": "Comes from a step this one doesn't depend on"}); continue
        text, trimmed = it.content, False
        if len(text) > left:
            if left < 500:
                p.withheld.append({**ref, "reason": "Over the size limit for this tool"}); continue
            text, trimmed = text[:left] + " [trimmed]", True
        left -= len(text)
        p.sent.append({**ref, "chars": len(text), "trimmed": trimmed, "preview": text[:140]})
        k = it.kind
        if k == "objective": p.objective = text
        elif k == "requirement": p.requirements.append(text)
        elif k == "constraint": p.constraints.append(text)
        elif k == "decision": p.decisions.append(text)
        elif k == "research": p.research.append(text)
        elif k == "output": p.previous_outputs.append({"label": it.label, "text": text})
        elif k == "file": p.files.append({"name": it.label, "excerpt": text})
    done = [LABEL.get(s.capability, s.capability) for s in subs if s.status == "done"]
    p.current_state = f"Step {sub.position + 1} of {len(subs)}. Finished: {', '.join(done) or 'nothing yet'}."
    p.next_task = f"{step_label}: {sub.description}"
    if sub.capability == "image_generation":
        p.image_count = max(1, min(int(((task.plan or {}).get("counts") or {}).get("images", 1)), 4))
    if persist:
        db.add(ContextTransfer(task_id=task.id, to_subtask_id=sub.id, sent=p.sent, withheld=p.withheld))
        db.flush()
    return p
