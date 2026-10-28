"""Fraud indicators for one network: what is unusual about it, in plain words.

Connections alone say little: a claim touches a driver, a policy and a shop in every case. The
analytics rules (rules_engine) look at how the pieces repeat: shared details, providers that keep
turning up together, the same people in changing roles, aliases, and claims bunched in time or
soon after a policy began. Each rule that fires adds its points to a 0-100 score, with a one-line
reason. Pure functions over plain dicts, so they are tested without a database.
"""

from typing import Any

from graphy.schemas.rules import DEFAULT_ANALYTICS_RULES, AnalyticsRuleDocument
from graphy.services.rules_engine import Finding, evaluate

HIGH, MEDIUM = 60, 35


def severity(score: int) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def network_insights(
    members: dict[str, dict[str, Any]],
    rels: list[dict[str, Any]],
    shares: list[dict[str, Any]],
    aliases: list[tuple[str, str]],
    rules: list[AnalyticsRuleDocument] | None = None,
) -> tuple[int, list[Finding]]:
    """members: id -> {type, label}. rels: {src, dst, rel_type, first_seen} between members.
    shares: {a, b, attr_type, value_id} for each shared value. aliases: entity pairs joined by
    an alias link. Returns (score, findings, strongest first)."""
    found = evaluate(DEFAULT_ANALYTICS_RULES if rules is None else rules, members, rels, shares,
                     aliases)
    return min(100, sum(f.points for f in found)), found
