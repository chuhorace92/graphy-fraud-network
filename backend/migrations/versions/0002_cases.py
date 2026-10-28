"""Case management: working state, tasks, notes and documents for networks flagged by fraud
indicators, and the closing report.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                     nullable=False)


def _case_fk() -> sa.Column:
    return sa.Column("case_id", UUID(as_uuid=True),
                     sa.ForeignKey("fraud_case.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "fraud_case",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assignee", sa.String(255)),
        sa.Column("report", JSONB),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.String(255)),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_table(
        "case_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _case_fk(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_index("ix_case_event_case_id", "case_event", ["case_id"])
    op.create_table(
        "case_task",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _case_fk(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("assignee", sa.String(255)),
        sa.Column("due_date", sa.Date),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_index("ix_case_task_case_id", "case_task", ["case_id"])
    op.create_table(
        "case_document",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _case_fk(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("task_id", UUID(as_uuid=True),
                  sa.ForeignKey("case_task.id", ondelete="SET NULL")),
        sa.Column("uploaded_by", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_index("ix_case_document_case_id", "case_document", ["case_id"])
    op.create_index("ix_case_document_task_id", "case_document", ["task_id"])
    op.create_table(
        "case_note",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _case_fk(),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("task_id", UUID(as_uuid=True),
                  sa.ForeignKey("case_task.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
        sa.Column("updated_by", sa.String(255)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_case_note_case_id", "case_note", ["case_id"])
    op.create_index("ix_case_note_task_id", "case_note", ["task_id"])


def downgrade() -> None:
    for table in ("case_note", "case_document", "case_task", "case_event", "fraud_case"):
        op.drop_table(table)
