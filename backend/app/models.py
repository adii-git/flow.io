"""Data model. Generic column types so tests run on SQLite; Postgres gets JSONB and pgvector."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
                        TypeDecorator, UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Embedding(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(JSON())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Row:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def fk(target: str, **kw):
    return mapped_column(Uuid, ForeignKey(target, ondelete="CASCADE"), **kw)


class User(Row, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RefreshToken(Row, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = fk("users.id", index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Row, Base):
    __tablename__ = "projects"
    user_id: Mapped[uuid.UUID] = fk("users.id", index=True)
    name: Mapped[str] = mapped_column(String(120))


class Task(Row, Base):
    __tablename__ = "tasks"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    project_id: Mapped[uuid.UUID | None] = fk("projects.id", nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    plan: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # {what, doing, details} when a run fails
    __table_args__ = (Index("ix_tasks_user_status_created", "user_id", "status", "created_at"),)


class Tool(Base):
    """Registry entry. Data, not code: the router scores these rows."""
    __tablename__ = "tools"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(60))
    capabilities: Mapped[list] = mapped_column(JSONType, default=list)
    context_window: Mapped[int] = mapped_column(Integer, default=0)
    supports_images: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_files: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_class: Mapped[str] = mapped_column(String(12), default="mid")
    speed_class: Mapped[str] = mapped_column(String(12), default="mid")
    availability: Mapped[str] = mapped_column(String(16), default="available", index=True)  # available | planned | retired
    summary: Mapped[str] = mapped_column(String(200), default="")
    requires_key: Mapped[bool] = mapped_column(Boolean, default=True)
    adapter: Mapped[str] = mapped_column(String(60), default="")  # executor adapter id (Phase 7); not used for routing
    config: Mapped[dict] = mapped_column(JSONType, default=dict)  # adapter settings, never secrets


class Subtask(Row, Base):
    __tablename__ = "subtasks"
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    position: Mapped[int] = mapped_column(Integer)
    capability: Mapped[str] = mapped_column(String(40))
    tool_id: Mapped[str | None] = mapped_column(ForeignKey("tools.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    depends_on: Mapped[list] = mapped_column(JSONType, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    routing: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # router decision, user-safe reasons only
    output: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class ToolConnection(Row, Base):
    """One provider key per user (a single Anthropic key serves every Anthropic tool)."""
    __tablename__ = "tool_connections"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    provider: Mapped[str] = mapped_column(String(60))
    encrypted_key: Mapped[str] = mapped_column(Text)  # Fernet token, never plaintext
    key_hint: Mapped[str] = mapped_column(String(8), default="")  # last 4 characters, display only
    __table_args__ = (UniqueConstraint("user_id", "provider"),)


class Execution(Row, Base):
    __tablename__ = "executions"
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    subtask_id: Mapped[uuid.UUID | None] = fk("subtasks.id", nullable=True)
    tool_id: Mapped[str | None] = mapped_column(ForeignKey("tools.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContextItem(Row, Base):
    __tablename__ = "context_items"
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    kind: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    subtask_id: Mapped[uuid.UUID | None] = fk("subtasks.id", nullable=True)  # step that produced it
    label: Mapped[str] = mapped_column(String(120), default="")
    embedding: Mapped[list | None] = mapped_column(Embedding, nullable=True)


class ContextTransfer(Row, Base):
    __tablename__ = "context_transfers"
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    from_subtask_id: Mapped[uuid.UUID | None] = fk("subtasks.id", nullable=True)
    to_subtask_id: Mapped[uuid.UUID | None] = fk("subtasks.id", nullable=True)
    sent: Mapped[list] = mapped_column(JSONType, default=list)
    withheld: Mapped[list] = mapped_column(JSONType, default=list)  # each item carries a reason


class File(Row, Base):
    __tablename__ = "files"
    user_id: Mapped[uuid.UUID] = fk("users.id", index=True)
    task_id: Mapped[uuid.UUID | None] = fk("tasks.id", nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")


class Result(Row, Base):
    __tablename__ = "results"
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    kind: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)


class Usage(Row, Base):
    __tablename__ = "usage"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    execution_id: Mapped[uuid.UUID | None] = fk("executions.id", nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("ix_usage_user_created", "user_id", "created_at"),)


class Setting(Row, Base):
    __tablename__ = "settings"
    user_id: Mapped[uuid.UUID] = fk("users.id", unique=True)
    theme: Mapped[str] = mapped_column(String(12), default="system")
    prefs: Mapped[dict] = mapped_column(JSONType, default=dict)


class AuditLog(Row, Base):
    __tablename__ = "audit_log"
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)


class TaskEvent(Base):
    """Append-only run log; the SSE stream reads it, so any process can write progress."""
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = fk("tasks.id", index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
