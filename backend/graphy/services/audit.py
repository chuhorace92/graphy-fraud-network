"""Append-only audit trail (X-5)."""

from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from graphy.auth import User
from graphy.db.models import AuditEvent

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _event(actor: str, action: str, target_type: str | None, target_id: str | None,
           before: dict[str, Any] | None, after: dict[str, Any] | None) -> AuditEvent:
    return AuditEvent(
        actor=actor, action=action, target_type=target_type, target_id=target_id,
        before=before, after=after, request_id=request_id_var.get(),
    )


async def record(
    session: AsyncSession,
    user: User,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the caller's transaction; it commits with the change it records."""
    session.add(_event(user.subject, action, target_type, target_id, before, after))


def record_sync(session: Session, actor: str, action: str, target_type: str | None = None,
                target_id: str | None = None, *, after: dict[str, Any] | None = None) -> None:
    session.add(_event(actor, action, target_type, target_id, None, after))
