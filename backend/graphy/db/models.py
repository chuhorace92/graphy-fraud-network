"""PostgreSQL tables: configuration, overrides, jobs and audit (TRD section 2).

Keep this in step with migrations/versions. The graph itself lives in Neo4j.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: ARRAY(Text)}


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class AttributeType(Base):
    """Versioned attribute catalog entry (BRD 9.1, TRD 3.1)."""

    __tablename__ = "attribute_type"

    attr_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(16), default="draft")
    definition: Mapped[dict[str, Any]]
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class RuleSet(Base):
    """Entity-resolution rule set, versioned; draft -> simulated -> published -> retired."""

    __tablename__ = "rule_set"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="draft")
    document: Mapped[dict[str, Any]]
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResolutionOverride(Base):
    """Manual merge / split / known-different, keyed by source record ids so re-runs keep it."""

    __tablename__ = "resolution_override"

    id: Mapped[uuid.UUID] = _uuid()
    kind: Mapped[str] = mapped_column(String(16))  # merge | known_different
    record_ids: Mapped[list[str]]
    reason: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class ReviewPair(Base):
    """Borderline candidate pair awaiting a human decision (ER-7)."""

    __tablename__ = "review_pair"

    id: Mapped[uuid.UUID] = _uuid()
    record_a: Mapped[str] = mapped_column(String(255))
    record_b: Mapped[str] = mapped_column(String(255))
    score: Mapped[float] = mapped_column(Float)
    contributions: Mapped[dict[str, Any]]
    rule_set_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rule_set.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = _created_at()


class AnalyticsRule(Base):
    __tablename__ = "analytics_rule"
    __table_args__ = (UniqueConstraint("rule_id", "version"),)

    id: Mapped[uuid.UUID] = _uuid()
    rule_id: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="draft")
    document: Mapped[dict[str, Any]]
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class JobRun(Base):
    """Every ingestion, resolution and analytics job (TRD section 8)."""

    __tablename__ = "job_run"

    id: Mapped[uuid.UUID] = _uuid()
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    counts: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClusterResult(Base):
    """Scored outlier candidate from an analytics run (GA-4, GA-5)."""

    __tablename__ = "cluster_result"

    id: Mapped[uuid.UUID] = _uuid()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_run.id"))
    cluster_id: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[dict[str, Any]]
    metrics: Mapped[dict[str, Any]]
    change: Mapped[str] = mapped_column(String(16), default="new")  # new | grown | unchanged
    fingerprint: Mapped[str] = mapped_column(String(64))


class Suppression(Base):
    """Cluster marked benign; re-alerts only if membership changes beyond tolerance (GA-8)."""

    __tablename__ = "suppression"

    id: Mapped[uuid.UUID] = _uuid()
    fingerprint: Mapped[str] = mapped_column(String(64))
    cluster_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    tolerance: Mapped[float] = mapped_column(Float, default=0.1)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class IngestionSource(Base):
    __tablename__ = "ingestion_source"

    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    source_system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    mapping: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    """Append-only; a database trigger rejects UPDATE and DELETE (X-5)."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = _created_at()
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(255))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))


class SavedView(Base):
    __tablename__ = "saved_view"

    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(String(255))
    owner: Mapped[str] = mapped_column(String(255))
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _created_at()


class FraudCase(Base):
    """Working state of one network of people, claims and providers. Created the first time
    someone acts on it; until then every network is an implicit "new" case. Keyed on the
    network's lowest entity id, which stays put unless an entity with a lower id joins it."""

    __tablename__ = "fraud_case"

    id: Mapped[uuid.UUID] = _uuid()
    case_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="new")
    assignee: Mapped[str | None] = mapped_column(String(255))
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # closing report, draft or final
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), onupdate=func.now())


class CaseEvent(Base):
    """A case's history: notes, status changes and assignments, oldest first."""

    __tablename__ = "case_event"

    id: Mapped[uuid.UUID] = _uuid()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fraud_case.id", ondelete="CASCADE"),
                                               index=True)
    kind: Mapped[str] = mapped_column(String(16))  # note, status, assignee, task, ...
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


def _case_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("fraud_case.id", ondelete="CASCADE"), index=True)


class CaseTask(Base):
    __tablename__ = "case_task"

    id: Mapped[uuid.UUID] = _uuid()
    case_id: Mapped[uuid.UUID] = _case_fk()
    title: Mapped[str] = mapped_column(String(255))
    assignee: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # or received, not_received
    done: Mapped[bool] = mapped_column(Boolean, default=False)  # closed
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class CaseDocument(Base):
    """An uploaded file, kept in the database (small files only; there is no object store)."""

    __tablename__ = "case_document"

    id: Mapped[uuid.UUID] = _uuid()
    case_id: Mapped[uuid.UUID] = _case_fk()
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("case_task.id", ondelete="SET NULL"), index=True)  # tagged to a task
    uploaded_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class CaseNote(Base):
    """A diary entry on a case. `body` is HTML, sanitized before it is stored; editable until
    the case is closed."""

    __tablename__ = "case_note"

    id: Mapped[uuid.UUID] = _uuid()
    case_id: Mapped[uuid.UUID] = _case_fk()
    title: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("case_task.id", ondelete="SET NULL"), index=True)  # tagged to a task
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
