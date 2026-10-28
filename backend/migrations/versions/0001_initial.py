"""Initial schema: catalog, rule sets, overrides, jobs, analytics results, audit.

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "attribute_type",
        sa.Column("attr_type", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_table(
        "rule_set",
        _id(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_index("ix_rule_set_entity_state", "rule_set", ["entity_type", "state"])
    op.create_table(
        "resolution_override",
        _id(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("record_ids", ARRAY(sa.Text), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_index("ix_resolution_override_record_ids", "resolution_override", ["record_ids"],
                    postgresql_using="gin")
    op.create_table(
        "review_pair",
        _id(),
        sa.Column("record_a", sa.String(255), nullable=False),
        sa.Column("record_b", sa.String(255), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("contributions", JSONB, nullable=False),
        sa.Column("rule_set_id", UUID(as_uuid=True), sa.ForeignKey("rule_set.id")),
        sa.Column("status", sa.String(16), nullable=False),
        _created_at(),
    )
    op.create_index("ix_review_pair_status_score", "review_pair", ["status", "score"])
    op.create_table(
        "analytics_rule",
        _id(),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
        sa.UniqueConstraint("rule_id", "version"),
    )
    op.create_table(
        "job_run",
        _id(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("counts", JSONB, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_job_run_kind_created", "job_run", ["kind", "created_at"])
    op.create_table(
        "cluster_result",
        _id(),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("job_run.id"), nullable=False),
        sa.Column("cluster_id", sa.String(128), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("reasons", JSONB, nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("change", sa.String(16), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
    )
    op.create_index("ix_cluster_result_run_score", "cluster_result", ["run_id", "score"])
    op.create_table(
        "suppression",
        _id(),
        sa.Column("fingerprint", sa.String(64), nullable=False, index=True),
        sa.Column("cluster_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("tolerance", sa.Float, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _created_at(),
    )
    op.create_table(
        "ingestion_source",
        _id(),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("mapping", JSONB, nullable=False),
        _created_at(),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(255)),
        sa.Column("before", JSONB),
        sa.Column("after", JSONB),
        sa.Column("request_id", sa.String(64)),
    )
    op.create_index("ix_audit_event_at", "audit_event", ["at"])
    op.create_index("ix_audit_event_actor", "audit_event", ["actor"])
    op.create_index("ix_audit_event_target", "audit_event", ["target_type", "target_id"])
    # Append-only: reject UPDATE and DELETE, even for the application's own role (X-5).
    # Retention purges run as a separate, privileged role that disables this trigger.
    op.execute("""
        CREATE FUNCTION audit_event_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_event is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_event_no_change
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION audit_event_immutable();
    """)
    op.create_table(
        "saved_view",
        _id(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False, index=True),
        sa.Column("shared", sa.Boolean, nullable=False),
        sa.Column("state", JSONB, nullable=False),
        _created_at(),
    )


def downgrade() -> None:
    for table in ("saved_view", "audit_event", "ingestion_source", "suppression",
                  "cluster_result", "job_run", "analytics_rule", "review_pair",
                  "resolution_override", "rule_set", "attribute_type"):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS audit_event_immutable()")
