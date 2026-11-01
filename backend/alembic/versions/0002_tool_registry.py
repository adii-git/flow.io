"""Registry columns on tools; tool_connections keyed by provider instead of tool.

Idempotent on purpose: 0001 is built from the current models, so a fresh database already has these
columns. tool_connections held no rows before this phase (no endpoint wrote to it), so it is recreated.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002"
down_revision = "0001"


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    have = {c["name"] for c in insp.get_columns("tools")}
    adds = {
        "summary": sa.Column("summary", sa.String(200), nullable=False, server_default=""),
        "requires_key": sa.Column("requires_key", sa.Boolean, nullable=False, server_default=sa.true()),
        "adapter": sa.Column("adapter", sa.String(60), nullable=False, server_default=""),
        "config": sa.Column("config", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"),
    }
    for name, col in adds.items():
        if name not in have:
            op.add_column("tools", col)
    if "ix_tools_availability" not in {i["name"] for i in insp.get_indexes("tools")}:
        op.create_index("ix_tools_availability", "tools", ["availability"])
    if "provider" not in {c["name"] for c in insp.get_columns("tool_connections")}:
        op.drop_table("tool_connections")
        from app.models import ToolConnection
        ToolConnection.__table__.create(bind)


def downgrade():
    pass  # forward-only: downgrading would discard stored provider keys
