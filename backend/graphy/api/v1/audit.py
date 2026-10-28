from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from graphy.api.deps import Auditor, Pg
from graphy.db.models import AuditEvent

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    actor: str
    action: str
    target_type: str | None
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None


@router.get("/audit/events", response_model=list[AuditEventOut])
async def events(
    pg: Pg, _: Auditor,
    actor: str | None = None,
    action: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    limit: int = Query(100, ge=1, le=1_000),
) -> list[AuditEvent]:
    """Filterable audit trail; compliance role only (X-5, scenario 6)."""
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if actor:
        q = q.where(AuditEvent.actor == actor)
    if action:
        q = q.where(AuditEvent.action == action)
    if target_id:
        q = q.where(AuditEvent.target_id == target_id)
    if since:
        q = q.where(AuditEvent.at >= since)
    return list(await pg.scalars(q))
