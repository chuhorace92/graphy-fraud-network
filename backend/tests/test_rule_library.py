from types import SimpleNamespace

from graphy.schemas.rules import DEFAULT_ANALYTICS_RULES, AnalyticsRuleDocument, Condition
from graphy.services.analytics_rules import rules_in_force
from graphy.services.rules_engine import SUPPORTED_METRICS, unsupported


def _row(rule_id: str, version: int, state: str, severity: str = "low"):
    doc = AnalyticsRuleDocument(
        rule_id=rule_id, scope="cluster", severity=severity,
        conditions=[Condition(metric="shared_value_holders", op=">=", value=2)])
    return SimpleNamespace(rule_id=rule_id, version=version, state=state,
                           document=doc.model_dump(mode="json"))


def test_defaults_apply_only_while_nothing_is_stored() -> None:
    assert rules_in_force([]) == DEFAULT_ANALYTICS_RULES


def test_retiring_every_rule_switches_them_all_off() -> None:
    assert rules_in_force([_row("rule-a", 1, "retired"), _row("rule-b", 1, "draft")]) == []


def test_latest_published_version_wins_and_drafts_are_ignored() -> None:
    rows = [_row("rule-a", 1, "published", "low"), _row("rule-a", 2, "published", "high"),
            _row("rule-a", 3, "draft", "medium"), _row("rule-b", 1, "retired")]
    [rule] = rules_in_force(rows)
    assert rule.rule_id == "rule-a" and rule.severity == "high"


def test_unsupported_metrics_are_named() -> None:
    ok = AnalyticsRuleDocument(
        rule_id="ok", scope="cluster", severity="low",
        conditions=[Condition(metric="shared_value_holders", op=">=", value=2)])
    cluster = AnalyticsRuleDocument(
        rule_id="later", scope="cluster", severity="low",
        conditions=[Condition(metric="density", op=">=", value=0.5),
                    Condition(metric="shared_value_holders", op=">=", value=2)])
    assert unsupported(ok) == [] and unsupported(cluster) == ["density"]
    assert "density" not in SUPPORTED_METRICS


def test_every_default_rule_can_be_published() -> None:
    assert all(unsupported(r) == [] for r in DEFAULT_ANALYTICS_RULES)
