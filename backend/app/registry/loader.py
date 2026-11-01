import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Tool
from ..config import get_settings

SEED = Path(__file__).with_name("tools.json")
Capability = Literal["reasoning", "long_context_documents", "web_research", "code_generation",
                     "code_execution", "image_generation", "file_processing", "validation", "writing"]


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.\-]{1,62}$")
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(pattern=r"^[a-z0-9\-]{2,60}$")
    summary: str = Field(max_length=200)
    capabilities: list[Capability] = Field(min_length=1)
    context_window: int = Field(ge=0)
    supports_images: bool = False
    supports_files: bool = False
    supports_tools: bool = False
    cost_class: Literal["low", "mid", "high"]
    speed_class: Literal["fast", "mid", "slow"]
    availability: Literal["available", "planned"] = "available"
    requires_key: bool = True
    adapter: str
    config: dict = {}

    @model_validator(mode="after")
    def _no_secrets(self):
        if any(w in k.lower() for k in self.config for w in ("key", "secret", "token", "password")):
            raise ValueError("config must not hold secrets; provider keys live in tool_connections")
        return self


def load_specs(path: Path = SEED) -> list[ToolSpec]:
    specs = [ToolSpec(**t) for t in json.loads(path.read_text())["tools"]]
    ids = [s.id for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate tool ids in registry seed")
    return specs


def sync_registry(db: Session, specs: list[ToolSpec] | None = None) -> dict[str, int]:
    """Idempotent upsert. Tools dropped from the seed are retired, not deleted (subtasks may reference them)."""
    specs = specs if specs is not None else load_specs()
    existing = {t.id: t for t in db.scalars(select(Tool))}
    out = {"added": 0, "updated": 0, "retired": 0}
    for s in specs:
        row = existing.get(s.id)
        if row is None:
            db.add(Tool(**s.model_dump()))
            out["added"] += 1
            continue
        for k, v in s.model_dump().items():
            setattr(row, k, v)
        out["updated"] += 1
    for tid, row in existing.items():
        if tid not in {s.id for s in specs} and row.availability != "retired":
            row.availability = "retired"
            out["retired"] += 1
    # Local image generation is intentionally opt-in: it becomes routable only when a
    # local Stable Diffusion WebUI/Forge API endpoint has been configured.
    local = existing.get("local-image")
    if local is None:
        local = db.scalar(select(Tool).where(Tool.id == "local-image"))
    if local is not None:
        local.availability = "available" if get_settings().local_image_api_url else "planned"
    db.commit()
    return out
