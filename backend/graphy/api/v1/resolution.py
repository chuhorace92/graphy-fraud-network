import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from graphy.api.deps import Pg, Reader, Steward
from graphy.catalog import EntityType
from graphy.config import get_settings
from graphy.db.models import ResolutionOverride, ReviewPair, RuleSet
from graphy.db.neo4j import sync_driver
from graphy.db.postgres import sync_session
from graphy.resolution.deterministic import simulate as run_simulation
from graphy.schemas.resolution import ActiveRules, SimulateRequest, Simulation
from graphy.schemas.rules import (
    RuleSetCreate,
    RuleSetDocument,
    default_rule_set,
    filled_scoring,
)
from graphy.services import audit
from graphy.services.jobs import JobAccepted, enqueue, resolve

router = APIRouter(prefix="/resolution", tags=["resolution"])


class RuleSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: str
    version: int
    state: str
    document: dict[str, Any]
    created_by: str
    created_at: datetime
    published_at: datetime | None


class ReviewPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    record_a: str
    record_b: str
    score: float
    contributions: dict[str, Any]
    status: str
    created_at: datetime


class Decision(BaseModel):
    """confirm/merge -> records are the same; reject/split -> known different (ER-7)."""

    kind: Literal["confirm", "reject", "merge", "split"]
    record_ids: list[str] = Field(min_length=2, max_length=500)
    reason: str | None = Field(default=None, max_length=2_000)
    review_pair_id: uuid.UUID | None = None


def _snapshot(rs: RuleSet) -> dict[str, Any]:
    return {"name": rs.name, "version": rs.version, "state": rs.state}


async def _get(pg: Pg, rule_set_id: uuid.UUID) -> RuleSet:
    rs = await pg.get(RuleSet, rule_set_id, with_for_update=True)
    if rs is None:
        raise HTTPException(404, "Rule set not found")
    return rs


@router.get("/rule-sets", response_model=list[RuleSetOut])
async def list_rule_sets(pg: Pg, _: Reader) -> list[RuleSet]:
    return list(await pg.scalars(select(RuleSet).order_by(RuleSet.name, RuleSet.version.desc())))


@router.post("/rule-sets", response_model=RuleSetOut, status_code=201)
async def create_rule_set(body: RuleSetCreate, pg: Pg, user: Steward) -> RuleSet:
    """Create a new draft version. Earlier versions are never edited in place (ER-5)."""
    latest = await pg.scalar(select(func.max(RuleSet.version)).where(RuleSet.name == body.name))
    rs = RuleSet(name=body.name, entity_type=body.entity_type, version=(latest or 0) + 1,
                 state="draft", document=body.document.model_dump(mode="json"),
                 created_by=user.subject)
    pg.add(rs)
    await pg.flush()
    await audit.record(pg, user, "rule_set.create", "rule_set", str(rs.id), after=_snapshot(rs))
    await pg.commit()
    return rs


@router.get("/rule-sets/{rule_set_id}", response_model=RuleSetOut)
async def get_rule_set(rule_set_id: uuid.UUID, pg: Pg, _: Reader) -> RuleSet:
    rs = await pg.get(RuleSet, rule_set_id)
    if rs is None:
        raise HTTPException(404, "Rule set not found")
    return rs


def _simulate(entity_type: str, doc: RuleSetDocument) -> Simulation:
    with sync_session() as pg:
        return run_simulation(entity_type=entity_type, doc=doc, driver=sync_driver(), pg=pg,
                              settings=get_settings())


@router.get("/active", response_model=ActiveRules)
async def active_rules(pg: Pg, _: Reader, entity_type: EntityType = "Person") -> ActiveRules:
    """The rules resolution uses now for a type: its published rule set, or the built-in default."""
    row = await pg.scalar(select(RuleSet).where(
        RuleSet.entity_type == entity_type, RuleSet.state == "published")
        .order_by(RuleSet.published_at.desc()).limit(1))
    doc = default_rule_set(entity_type) if row is None else RuleSetDocument.model_validate(
        row.document)
    return ActiveRules(
        entity_type=entity_type, name="built-in default" if row is None else row.name,
        version=None if row is None else f"v{row.version}",
        document=doc.model_copy(update={"scoring": filled_scoring(doc, entity_type)}))


@router.post("/simulate", response_model=Simulation)
async def simulate_document(body: SimulateRequest, _: Steward) -> Simulation:
    """What these rules would do to today's data for a type. Nothing is changed (ER-4)."""
    return await run_in_threadpool(_simulate, body.entity_type, body.document)


@router.post("/rule-sets/{rule_set_id}/simulate", response_model=Simulation)
async def simulate(rule_set_id: uuid.UUID, pg: Pg, _: Steward) -> Simulation:
    rs = await pg.get(RuleSet, rule_set_id)
    if rs is None:
        raise HTTPException(404, "Rule set not found")
    return await run_in_threadpool(_simulate, rs.entity_type,
                                   RuleSetDocument.model_validate(rs.document))


async def _make_current(pg: Pg, user: Steward, background: BackgroundTasks, rs: RuleSet,
                        action: str) -> JobAccepted:
    before = _snapshot(rs)
    await pg.execute(
        update(RuleSet)
        .where(RuleSet.entity_type == rs.entity_type, RuleSet.state == "published",
               RuleSet.id != rs.id)
        .values(state="retired")
    )
    rs.state, rs.published_at = "published", datetime.now(UTC)
    await audit.record(pg, user, action, "rule_set", str(rs.id), before=before,
                       after=_snapshot(rs))
    await pg.commit()
    return await enqueue(pg, user, background, "resolution",
                         {"trigger": action, "rule_set_id": str(rs.id)}, resolve)


@router.post("/rule-sets/{rule_set_id}/publish", response_model=JobAccepted, status_code=202)
async def publish(rule_set_id: uuid.UUID, pg: Pg, user: Steward,
                  background: BackgroundTasks) -> JobAccepted:
    """Publish and re-run resolution. Phase 3 will require a simulation first (ER-4)."""
    rs = await _get(pg, rule_set_id)
    if rs.state not in ("draft", "simulated"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot publish a {rs.state} rule set")
    return await _make_current(pg, user, background, rs, "rule_set.publish")


@router.post("/rule-sets/{rule_set_id}/rollback", response_model=JobAccepted, status_code=202)
async def rollback(rule_set_id: uuid.UUID, pg: Pg, user: Steward,
                   background: BackgroundTasks) -> JobAccepted:
    """Make a previously published (now retired) version current again (ER-5)."""
    rs = await _get(pg, rule_set_id)
    if rs.state != "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a retired version can be restored")
    return await _make_current(pg, user, background, rs, "rule_set.rollback")


@router.post("/runs", response_model=JobAccepted, status_code=202)
async def run_resolution(pg: Pg, user: Steward, background: BackgroundTasks) -> JobAccepted:
    return await enqueue(pg, user, background, "resolution", {"trigger": "manual"}, resolve)


@router.get("/review-queue", response_model=list[ReviewPairOut])
async def review_queue(pg: Pg, _: Reader, limit: int = 100) -> list[ReviewPair]:
    rows = await pg.scalars(
        select(ReviewPair).where(ReviewPair.status == "pending")
        .order_by(ReviewPair.score.desc()).limit(min(limit, 500))
    )
    return list(rows)


@router.post("/decisions", status_code=201)
async def decide(body: Decision, pg: Pg, user: Steward) -> dict[str, str]:
    """Record an override. It is keyed by source record ids, so it survives every re-run."""
    kind = "merge" if body.kind in ("confirm", "merge") else "known_different"
    override = ResolutionOverride(kind=kind, record_ids=body.record_ids, reason=body.reason,
                                  created_by=user.subject)
    pg.add(override)
    if body.review_pair_id:
        pair = await pg.get(ReviewPair, body.review_pair_id)
        if pair is None:
            raise HTTPException(404, "Review pair not found")
        pair.status = "decided"
    await pg.flush()
    await audit.record(pg, user, f"resolution.{body.kind}", "resolution_override",
                       str(override.id), after=body.model_dump(mode="json"))
    await pg.commit()
    return {"override_id": str(override.id), "applies_on": "next resolution run"}
