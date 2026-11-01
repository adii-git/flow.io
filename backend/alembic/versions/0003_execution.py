"""Execution phase: run log, step routing/output, context provenance, file excerpts. Idempotent like 0002."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
J = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    def add(table, col):
        if col.name not in {c["name"] for c in insp.get_columns(table)}:
            op.add_column(table, col)

    add("tasks", sa.Column("error", J, nullable=True))
    add("subtasks", sa.Column("routing", J, nullable=True))
    add("subtasks", sa.Column("output", J, nullable=True))
    add("context_items", sa.Column("subtask_id", sa.Uuid, sa.ForeignKey("subtasks.id", ondelete="CASCADE"), nullable=True))
    add("context_items", sa.Column("label", sa.String(120), nullable=False, server_default=""))
    add("files", sa.Column("excerpt", sa.Text, nullable=False, server_default=""))
    from app.models import TaskEvent
    TaskEvent.__table__.create(bind, checkfirst=True)


def downgrade():
    pass
