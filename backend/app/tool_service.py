from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .models import Tool, ToolConnection, User
from .repositories import audit
from .security import encrypt_secret


def status_for(tool: Tool, connected: set[str]) -> str:
    if tool.availability == "planned":
        return "planned"
    if get_settings().execution_mode == "demo":
        return "ready"
    return "ready" if (not tool.requires_key or tool.provider in connected) else "needs_key"


def _connected(db: Session, user: User) -> set[str]:
    return set(db.scalars(select(ToolConnection.provider).where(ToolConnection.user_id == user.id)))


def list_tools(db: Session, user: User, capability: str | None = None) -> list[dict]:
    conn = _connected(db, user)
    rows = db.scalars(select(Tool).where(Tool.availability != "retired").order_by(Tool.provider, Tool.name)).all()
    return [{**{c: getattr(t, c) for c in ("id", "name", "provider", "summary", "capabilities", "context_window",
             "supports_images", "supports_files", "supports_tools", "cost_class", "speed_class", "requires_key")},
             "status": status_for(t, conn)} for t in rows if not capability or capability in t.capabilities]


def get_tool(db: Session, user: User, tool_id: str) -> dict:
    for t in list_tools(db, user):
        if t["id"] == tool_id:
            return t
    raise HTTPException(404, "That tool isn't in the registry.")


def connect(db: Session, user: User, provider: str, api_key: str, ip: str) -> ToolConnection:
    t = db.scalar(select(Tool).where(Tool.provider == provider, Tool.requires_key.is_(True), Tool.availability != "retired"))
    if not t:
        raise HTTPException(404, "No tool in the registry uses a key from that provider.")
    row = db.scalar(select(ToolConnection).where(ToolConnection.user_id == user.id, ToolConnection.provider == provider))
    if row is None:
        row = ToolConnection(user_id=user.id, provider=provider, encrypted_key="")
        db.add(row)
    row.encrypted_key, row.key_hint = encrypt_secret(api_key), api_key[-4:]
    audit(db, "tool.connect", user.id, ip, provider=provider)  # the key itself is never logged
    db.commit()
    return row


def disconnect(db: Session, user: User, provider: str, ip: str) -> None:
    row = db.scalar(select(ToolConnection).where(ToolConnection.user_id == user.id, ToolConnection.provider == provider))
    if not row:
        raise HTTPException(404, "No key is saved for that provider.")
    db.delete(row)
    audit(db, "tool.disconnect", user.id, ip, provider=provider)
    db.commit()


def connections(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(ToolConnection).where(ToolConnection.user_id == user.id).order_by(ToolConnection.provider)).all()
    return [{"provider": r.provider, "key_hint": r.key_hint, "connected_at": r.created_at} for r in rows]
