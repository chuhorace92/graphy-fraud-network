import pytest
from pydantic import ValidationError

from graphy.schemas.rules import AnalyticsRuleDocument, RuleSetCreate, Thresholds
from graphy.services.graph_queries import lucene_terms


def test_trd_example_rule_validates() -> None:
    rule = AnalyticsRuleDocument.model_validate({
        "rule_id": "shared-address-ring",
        "scope": "cluster",
        "conditions": [
            {"metric": "distinct_members", "op": ">=", "value": 5},
            {"metric": "shared_attribute_count", "attr_type": "address", "op": ">=", "value": 1},
            {"metric": "age_span_days", "op": "<=", "value": 90},
        ],
        "severity": "high",
    })
    assert len(rule.conditions) == 3


def test_rules_reject_unknown_fields() -> None:
    # Nothing outside the schema gets through, e.g. a smuggled Cypher fragment.
    with pytest.raises(ValidationError):
        AnalyticsRuleDocument.model_validate({
            "rule_id": "x1", "scope": "cluster", "severity": "low",
            "conditions": [{"metric": "density", "op": ">=", "value": 1}],
            "cypher": "MATCH (n) DETACH DELETE n",
        })


def test_unknown_metric_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsRuleDocument.model_validate({
            "rule_id": "x1", "scope": "cluster", "severity": "low",
            "conditions": [{"metric": "n) DETACH DELETE n //", "op": ">=", "value": 1}],
        })


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Thresholds(auto_merge=0.8, review=0.9)


def test_rule_set_name_pattern() -> None:
    with pytest.raises(ValidationError):
        RuleSetCreate.model_validate({"name": "Bad Name!", "entity_type": "Person",
                                      "document": {}})


def test_lucene_escaping() -> None:
    assert lucene_terms('Smith AND "x"') == r'smith~ and \"x\"'
    assert lucene_terms("o'brien+co") == r"o'brien\+co~"
    assert lucene_terms("a:b") == r"a\:b"
