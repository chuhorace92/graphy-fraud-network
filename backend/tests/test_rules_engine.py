from graphy.schemas.rules import DEFAULT_ANALYTICS_RULES, AnalyticsRuleDocument, Condition
from graphy.services.rules_engine import describe, evaluate

# The four pattern rules these tests were written for; the other defaults have their own tests.
PATTERNS = DEFAULT_ANALYTICS_RULES[:4]


def _m(**kinds: str) -> dict:
    return {k: {"type": t, "label": k.upper()} for k, t in kinds.items()}


def _rel(src: str, dst: str, rel_type: str) -> dict:
    return {"src": src, "dst": dst, "rel_type": rel_type, "first_seen": "2026-01-01"}


def _fired(members, rels, shares=()) -> set[str]:
    return {f.rule_id for f in evaluate(PATTERNS, members, rels, list(shares))}


def test_the_default_rules_cover_every_indicator() -> None:
    assert [r.rule_id for r in DEFAULT_ANALYTICS_RULES] == [
        "shared-attribute-two-parties", "medical-and-legal-on-three-claims",
        "legal-and-bodyshop-on-three-claims", "same-group-shifting-roles-auto-claims",
        "repeat-participants", "probable-aliases", "claims-bunched-in-time",
        "claims-soon-after-policy-start"]


# 1. two or more parties use the same attribute

def test_two_parties_sharing_an_attribute() -> None:
    members = _m(a="Person", b="Person", c="Claim")
    share = {"a": "a", "b": "b", "attr_type": "phone", "value_id": "phone:1"}
    [f] = evaluate(PATTERNS, members, [], [share])
    assert f.rule_id == "shared-attribute-two-parties" and f.severity == "low"
    assert "2 parties use the same phone number (A, B)" == f.detail


def test_shared_value_needs_two_parties_not_things() -> None:
    members = _m(a="Person", home="Property")
    share = {"a": "a", "b": "home", "attr_type": "address", "value_id": "address:1"}
    assert _fired(members, [], [share]) == set()


def test_each_shared_attribute_is_reported() -> None:
    members = _m(a="Person", b="Person")
    shares = [{"a": "a", "b": "b", "attr_type": t, "value_id": f"{t}:1"}
              for t in ("phone", "bank_acct")]
    assert len(evaluate(PATTERNS, members, [], shares)) == 2


# 2 and 3. provider pairs on three or more claims

def _claims(n: int, providers: dict[str, str]):
    members = _m(**providers)
    rels = []
    for i in range(n):
        members[f"c{i}"] = {"type": "Claim", "label": f"C{i}"}
        rels += [_rel(p, f"c{i}", "treated_for") for p in providers]
    return members, rels


def test_medical_and_legal_on_three_claims() -> None:
    members, rels = _claims(3, {"doc": "MedicalProvider", "law": "LegalRep"})
    [f] = evaluate(PATTERNS, members, rels, [])
    assert f.rule_id == "medical-and-legal-on-three-claims" and f.severity == "high"
    assert f.detail == "DOC (medical provider) and LAW (attorney) are together on 3 claims"


def test_medical_and_legal_on_two_claims_is_quiet() -> None:
    assert _fired(*_claims(2, {"doc": "MedicalProvider", "law": "LegalRep"})) == set()


def test_legal_and_bodyshop_on_three_claims() -> None:
    members, rels = _claims(4, {"law": "LegalRep", "shop": "BodyShop"})
    assert _fired(members, rels) == {"legal-and-bodyshop-on-three-claims"}


def test_pair_must_share_the_same_claims() -> None:
    members = _m(doc="MedicalProvider", law="LegalRep")
    rels = []
    for i in range(3):  # each on three claims, but never the same claim
        members[f"a{i}"] = {"type": "Claim", "label": f"A{i}"}
        members[f"b{i}"] = {"type": "Claim", "label": f"B{i}"}
        rels += [_rel("doc", f"a{i}", "treated_for"), _rel("law", f"b{i}", "represents")]
    assert _fired(members, rels) == set()


# 4. the same group on several auto claims with shifting roles

def _auto(claims: int, roles_by_claim: list[dict[str, str]], vehicle: bool = True):
    members = _m(**{p: "Person" for roles in roles_by_claim for p in roles}, car="Vehicle")
    rels = []
    for i, roles in enumerate(roles_by_claim[:claims]):
        members[f"c{i}"] = {"type": "Claim", "label": f"C{i}"}
        if vehicle:
            rels.append(_rel(f"c{i}", "car", "involves"))
        rels += [_rel(p, f"c{i}", role) for p, role in roles.items()]
    return members, rels


_SHIFT = [{"a": "driver", "b": "passenger", "c": "passenger"},
          {"a": "passenger", "b": "driver", "c": "claimant"},
          {"a": "claimant", "b": "passenger", "c": "driver"}]


def test_same_group_shifting_roles_on_auto_claims() -> None:
    [f] = evaluate(PATTERNS, *_auto(3, _SHIFT), [])
    assert f.rule_id == "same-group-shifting-roles-auto-claims" and f.severity == "high"
    assert "3 people (A, B, C) share 3 auto claims, shifting between" in f.detail


def test_group_without_role_shifts_is_quiet() -> None:
    same = [{"a": "driver", "b": "passenger", "c": "passenger"}] * 3
    assert _fired(*_auto(3, same)) == set()


def test_group_on_non_auto_claims_is_quiet() -> None:
    assert _fired(*_auto(3, _SHIFT, vehicle=False)) == set()


def test_group_that_never_repeats_is_quiet() -> None:
    split = [{"a": "driver", "b": "passenger"}, {"a": "passenger", "c": "driver"}]
    assert _fired(*_auto(2, split)) == set()


# 5. the former built-in indicators, now rules

def _rule(rule_id: str):
    return next(r for r in DEFAULT_ANALYTICS_RULES if r.rule_id == rule_id)


def test_the_same_person_on_three_claims() -> None:
    members, rels = _auto(3, [{"a": "driver"}, {"a": "driver"}, {"a": "passenger"}])
    [f] = evaluate([_rule("repeat-participants")], members, rels, [])
    assert f.entities == ["a"] and f.points == 5 and "1 person appears on at least 3 claims" in f.detail
    [m] = f.matches
    assert (m.kind, m.entities, m.claims) == ("person", ["a"], ["c0", "c1", "c2"])
    assert evaluate([_rule("repeat-participants")], *_auto(2, [{"a": "driver"}] * 2), []) == []


def test_an_alias_link_is_a_finding_that_names_the_pair() -> None:
    members = _m(a="Person", b="Person")
    [f] = evaluate([_rule("probable-aliases")], members, [], [], [("b", "a")])
    assert f.entities == ["a", "b"] and f.matches[0].kind == "alias"
    assert evaluate([_rule("probable-aliases")], members, [], [], []) == []


def _dated(days: list[str]):
    members, rels = {}, []
    for i, d in enumerate(days):
        members[f"c{i}"] = {"type": "Claim", "label": f"C{i}"}
        members[f"p{i}"] = {"type": "Policy", "label": f"P{i}"}
        rels += [{"src": f"c{i}", "dst": f"p{i}", "rel_type": "under_policy", "first_seen": d}]
    return members, rels


def test_claims_bunched_in_time_name_the_claims_in_the_window() -> None:
    members, rels = _dated(["2026-01-01", "2026-01-10", "2026-01-20", "2026-02-01", "2026-09-01"])
    [f] = evaluate([_rule("claims-bunched-in-time")], members, rels, [])
    assert f.detail == "4 claims filed within 31 days"
    assert f.matches[0].claims == ["c0", "c1", "c2", "c3"]
    tight = AnalyticsRuleDocument(rule_id="tight", scope="cluster", severity="low", conditions=[
        Condition(metric="claims_in_window", op=">=", value=4, window_days=20)])
    assert evaluate([tight], members, rels, []) == []  # the window is the rule's to set


def test_claims_soon_after_a_policy_started() -> None:
    members, rels = _dated(["2026-01-10", "2026-01-20"])
    for i in range(2):
        members[f"x{i}"] = {"type": "Person", "label": f"X{i}"}
        rels.append({"src": f"x{i}", "dst": f"p{i}", "rel_type": "policyholder",
                     "first_seen": "2026-01-01"})
    [f] = evaluate([_rule("claims-soon-after-policy-start")], members, rels, [])
    assert f.detail == "2 claims filed within 60 days of the policy starting"
    assert [m.note for m in f.matches] == ["filed 9 days after the policy started",
                                           "filed 19 days after the policy started"]


def test_pattern_findings_carry_the_data_they_matched() -> None:
    members = _m(doc="MedicalProvider", law="LegalRep")
    rels = []
    for i in range(3):
        members[f"c{i}"] = {"type": "Claim", "label": f"C{i}"}
        rels += [_rel("doc", f"c{i}", "treated_for"), _rel("law", f"c{i}", "represents")]
    [f] = evaluate(PATTERNS, members, rels, [])
    assert f.matches[0].kind == "claims" and f.matches[0].claims == ["c0", "c1", "c2"]
    assert f.condition == "Fires when a medical provider and an attorney are together on at least 3 claims"


def test_a_rules_points_default_to_its_severity_unless_it_sets_them() -> None:
    assert evaluate([_rule("probable-aliases")], _m(a="Person", b="Person"), [], [],
                    [("a", "b")])[0].points == 15
    assert describe(_rule("claims-bunched-in-time")) == "Fires when at least 4 claims are filed within 120 days"


def test_a_scaling_rule_adds_points_for_each_thing_it_names_up_to_its_cap() -> None:
    people = {f"p{i}": "Person" for i in range(6)}
    members = _m(**people)
    rels = []
    for c in range(3):
        members[f"c{c}"] = {"type": "Claim", "label": f"C{c}"}
        rels += [_rel(p, f"c{c}", "insured") for p in people]
    [f] = evaluate([_rule("repeat-participants")], members, rels, [])
    assert f.points == 20  # six people at 5 each, capped at 20
    [one] = evaluate([_rule("repeat-participants")], *_auto(3, [{"a": "driver"}] * 3), [])
    assert one.points == 5
