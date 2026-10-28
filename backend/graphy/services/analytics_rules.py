"""Which analytics rules are in force: the latest published version of each rule_id."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from graphy.db.models import AnalyticsRule
from graphy.schemas.rules import DEFAULT_ANALYTICS_RULES, AnalyticsRuleDocument


def _latest(rows: list[AnalyticsRule]) -> list[AnalyticsRuleDocument]:
    newest: dict[str, AnalyticsRule] = {}
    for r in rows:
        if r.state == "published" and (r.rule_id not in newest
                                       or r.version > newest[r.rule_id].version):
            newest[r.rule_id] = r
    return [AnalyticsRuleDocument.model_validate(r.document) for r in newest.values()]


def rules_in_force(rows: list[AnalyticsRule]) -> list[AnalyticsRuleDocument]:
    """The published rules; the built-in defaults only while nothing has ever been stored. Once
    rules exist, retiring them all really does switch every rule off."""
    return _latest(rows) if rows else DEFAULT_ANALYTICS_RULES


async def published_rules(pg: AsyncSession) -> list[AnalyticsRuleDocument]:
    return rules_in_force(list(await pg.scalars(select(AnalyticsRule))))


def seed_default_rules(pg: Session, created_by: str = "system") -> int:
    """Store the default rules as published, skipping any rule_id that already has a row, so
    edits made through the API are never overwritten. Returns how many were added."""
    have = set(pg.scalars(select(AnalyticsRule.rule_id)))
    added = [r for r in DEFAULT_ANALYTICS_RULES if r.rule_id not in have]
    for r in added:
        pg.add(AnalyticsRule(rule_id=r.rule_id, version=1, state="published",
                             document=r.model_dump(mode="json"), created_by=created_by))
    pg.commit()
    return len(added)
