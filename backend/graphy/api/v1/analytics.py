import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from graphy.api.deps import Detector, Graph, Investigator, Pg, Reader, not_yet
from graphy.db.models import AnalyticsRule, ClusterResult, Suppression
from graphy.schemas.graph import RulePreview
from graphy.schemas.rules import AnalyticsRuleDocument
from graphy.services import audit, graph_queries
from graphy.services.rules_engine import unsupported

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: str
    version: int
    state: str
    document: dict[str, Any]
    created_by: str
    created_at: datetime


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    cluster_id: str
    score: float
    reasons: dict[str, Any]
    metrics: dict[str, Any]
    change: str


class SuppressBody(BaseModel):
    reason: str = Field(min_length=3, max_length=2_000)
    tolerance: float = Field(default=0.1, ge=0, le=1)


@router.get("/rules", response_model=list[AnalyticsRuleOut])
async def list_rules(pg: Pg, _: Reader) -> list[AnalyticsRule]:
    rows = await pg.scalars(
        select(AnalyticsRule).order_by(AnalyticsRule.rule_id, AnalyticsRule.version.desc())
    )
    return list(rows)


@router.post("/rules", response_model=AnalyticsRuleOut, status_code=201)
async def create_rule(body: AnalyticsRuleDocument, pg: Pg, user: Detector) -> AnalyticsRule:
    latest = await pg.scalar(
        select(func.max(AnalyticsRule.version)).where(AnalyticsRule.rule_id == body.rule_id)
    )
    rule = AnalyticsRule(rule_id=body.rule_id, version=(latest or 0) + 1,
                         document=body.model_dump(mode="json"), created_by=user.subject)
    pg.add(rule)
    await pg.flush()
    await audit.record(pg, user, "analytics_rule.create", "analytics_rule", str(rule.id),
                       after={"rule_id": rule.rule_id, "version": rule.version})
    await pg.commit()
    return rule


def _snapshot(r: AnalyticsRule) -> dict[str, Any]:
    return {"rule_id": r.rule_id, "version": r.version, "state": r.state}


async def _get_rule(pg: Pg, rule_pk: uuid.UUID) -> AnalyticsRule:
    r = await pg.get(AnalyticsRule, rule_pk, with_for_update=True)
    if r is None:
        raise HTTPException(404, "Rule not found")
    return r


def _require_evaluable(doc: AnalyticsRuleDocument) -> None:
    if bad := unsupported(doc):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"These metrics are not evaluated per network yet: {', '.join(bad)}")


@router.post("/rules/preview", response_model=RulePreview)
async def preview_rule(body: AnalyticsRuleDocument, graph: Graph, _: Detector) -> RulePreview:
    """Where would this rule fire on today's data? Nothing is saved."""
    _require_evaluable(body)
    return await graph_queries.rule_preview(graph, body)


@router.post("/rules/{rule_pk}/publish", response_model=AnalyticsRuleOut)
async def publish_rule(rule_pk: uuid.UUID, pg: Pg, user: Detector) -> AnalyticsRule:
    """Make this version the live one for its rule; it also restores a retired version. The
    previous live version is retired, so it can be restored the same way."""
    r = await _get_rule(pg, rule_pk)
    if r.state == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already published")
    _require_evaluable(AnalyticsRuleDocument.model_validate(r.document))
    before = _snapshot(r)
    await pg.execute(
        update(AnalyticsRule)
        .where(AnalyticsRule.rule_id == r.rule_id, AnalyticsRule.state == "published",
               AnalyticsRule.id != r.id)
        .values(state="retired"))
    r.state = "published"
    await audit.record(pg, user, "analytics_rule.publish", "analytics_rule", str(r.id),
                       before=before, after=_snapshot(r))
    await pg.commit()
    return r


@router.post("/rules/{rule_pk}/retire", response_model=AnalyticsRuleOut)
async def retire_rule(rule_pk: uuid.UUID, pg: Pg, user: Detector) -> AnalyticsRule:
    """Switch a live rule off. Its history stays and it can be published again."""
    r = await _get_rule(pg, rule_pk)
    if r.state != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a live rule can be retired")
    before = _snapshot(r)
    r.state = "retired"
    await audit.record(pg, user, "analytics_rule.retire", "analytics_rule", str(r.id),
                       before=before, after=_snapshot(r))
    await pg.commit()
    return r


@router.delete("/rules/{rule_pk}", status_code=204)
async def delete_draft(rule_pk: uuid.UUID, pg: Pg, user: Detector) -> Response:
    """Discard a draft. Versions that have been live are history and are kept."""
    r = await _get_rule(pg, rule_pk)
    if r.state != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft can be deleted")
    await audit.record(pg, user, "analytics_rule.delete", "analytics_rule", str(r.id),
                       before=_snapshot(r))
    await pg.delete(r)
    await pg.commit()
    return Response(status_code=204)


@router.post("/runs", status_code=202)
async def start_run(_: Detector) -> None:
    not_yet("Analytics runs (community detection and outlier scoring)")


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, _: Reader) -> None:
    not_yet("Analytics run history")


@router.get("/clusters", response_model=list[ClusterOut])
async def clusters(
    pg: Pg, _: Reader,
    run_id: uuid.UUID | None = None,
    min_score: float = Query(0, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
) -> list[ClusterResult]:
    q = select(ClusterResult).where(ClusterResult.score >= min_score)
    if run_id:
        q = q.where(ClusterResult.run_id == run_id)
    return list(await pg.scalars(q.order_by(ClusterResult.score.desc()).limit(limit)))


@router.post("/clusters/{cluster_result_id}/suppress", status_code=201)
async def suppress(cluster_result_id: uuid.UUID, body: SuppressBody, pg: Pg,
                   user: Investigator) -> dict[str, str]:
    """Mark a cluster benign; it re-alerts only if it changes materially (GA-8)."""
    cluster = await pg.get(ClusterResult, cluster_result_id)
    if cluster is None:
        raise HTTPException(404, "Cluster not found")
    s = Suppression(fingerprint=cluster.fingerprint, cluster_id=cluster.cluster_id,
                    reason=body.reason, tolerance=body.tolerance, created_by=user.subject)
    pg.add(s)
    await pg.flush()
    await audit.record(pg, user, "cluster.suppress", "cluster", cluster.cluster_id,
                       after=body.model_dump())
    await pg.commit()
    return {"suppression_id": str(s.id)}
