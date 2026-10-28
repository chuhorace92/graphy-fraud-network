from types import SimpleNamespace

import pytest

from graphy.resolution.deterministic import compute
from graphy.resolution.scoring import (
    Value,
    candidate_pairs,
    name_key,
    name_parts_similarity,
    score_all,
    score_pair,
    similarity,
)
from graphy.schemas.rules import (
    DEFAULT_SCORING_BY_TYPE,
    AttributeScoring,
    Constraints,
    DeterministicRule,
    RuleSetDocument,
    Scoring,
    default_rule_set,
    effective_scoring,
)

DEFAULT_SCORING = Scoring(
    attributes={
        "tax_id": AttributeScoring(strength="strong", on_conflict="block", merge_alone=True),
        "name": AttributeScoring(strength="medium", compare="fuzzy", min_similarity=0.88),
        "bank_acct": AttributeScoring(strength="strong"),
        "email": AttributeScoring(strength="strong", ignore_shared_over=25),
        "phone": AttributeScoring(strength="medium", ignore_shared_over=20),
        "address": AttributeScoring(strength="low", compare="fuzzy", min_similarity=0.9,
                                    ignore_shared_over=30),
    })


def v(attr: str, text: str, secret: bool = False) -> Value:
    return Value(f"{attr}:{text}", None if secret else text, text)


def rec(**attrs: str) -> dict[str, list[Value]]:
    return {a: [v(a, t, secret=a in ("tax_id", "bank_acct"))] for a, t in attrs.items()}


def score(a: dict, b: dict, cfg: Scoring = DEFAULT_SCORING, holders: dict | None = None):
    return score_pair("a", "b", a, b, cfg, holders or {})


def test_legal_suffixes_and_punctuation_do_not_make_names_different() -> None:
    assert name_key("acme clinic l l c", True) == name_key("acme clinic", True) == "acme clinic"
    assert name_key("acme clinic llc", False) == "acme clinic llc"
    assert name_key("inc", True) == "inc"  # never strip a name down to nothing


def test_a_name_that_merely_contains_another_is_not_similar() -> None:
    assert similarity("acme clinic", "clinic acme") == 1.0
    assert similarity("acme clinic", "acme clinic services") < 0.85


def test_the_same_tin_merges_on_its_own() -> None:
    p = score(rec(tax_id="1", name="alpha one"), rec(tax_id="1", name="zulu nine"))
    assert (p.decision, p.merge_alone, p.code) == ("merge", True, "merge_alone")


def test_different_tins_block_a_merge_however_much_else_matches() -> None:
    same = dict(name="acme clinic", bank_acct="9", email="a@x.example", phone="+1555")
    p = score(rec(tax_id="1", **same), rec(tax_id="2", **same))
    assert (p.decision, p.code) == ("none", "blocked")


def test_a_ring_sharing_details_but_not_a_name_is_never_merged() -> None:
    shared = dict(bank_acct="9", email="a@x.example", phone="+1555")
    p = score(rec(name="evergreen roofing", **shared), rec(name="northwind builders", **shared))
    assert p.score == 100
    assert (p.decision, p.code) == ("none", "no_identity")


def test_a_same_name_and_phone_and_address_goes_to_review() -> None:
    a = rec(name="acme clinic llc", phone="+1555", address="1 main st")
    b = rec(name="acme clinic l l c", phone="+1555", address="1 main st")
    p = score(a, b)
    assert p.score == 60 and p.decision == "review"


def test_same_name_bank_and_email_is_enough_to_merge() -> None:
    a = rec(name="acme clinic", bank_acct="9", email="a@x.example")
    p = score(a, dict(a))
    assert (p.score, p.decision) == (100, "merge")


def test_a_fuzzy_match_earns_partial_credit() -> None:
    p = score(rec(name="acme clinics"), rec(name="acme clinic"))
    (c,) = p.contributions
    assert c.outcome == "similar" and 0.88 <= c.similarity < 1
    assert p.score == round(25 * c.similarity)


def test_a_name_below_the_minimum_similarity_is_no_match() -> None:
    p = score(rec(name="acme clinic"), rec(name="bolt plumbing"))
    assert p.contributions[0].outcome == "conflict" and p.score == 0


def test_a_value_shared_by_too_many_records_is_ignored() -> None:
    a, b = rec(name="acme clinic", phone="+1555"), rec(name="acme clinic", phone="+1555")
    assert score(a, b, holders={"phone:+1555": 21}).score == 25  # name only
    assert score(a, b, holders={"phone:+1555": 20}).score == 50


def test_penalizing_a_difference_lowers_the_score() -> None:
    cfg = Scoring(attributes={
        "name": AttributeScoring(strength="medium", compare="fuzzy"),
        "phone": AttributeScoring(strength="medium", on_conflict="penalize", conflict_penalty=20),
    })
    same = score(rec(name="acme clinic", phone="1"), rec(name="acme clinic", phone="1"), cfg)
    diff = score(rec(name="acme clinic", phone="1"), rec(name="acme clinic", phone="2"), cfg)
    assert (same.score, diff.score) == (50, 5)


def test_a_missing_value_is_neither_a_match_nor_a_conflict() -> None:
    p = score(rec(tax_id="1", name="acme clinic"), rec(name="acme clinic"))
    assert [c.attr for c in p.contributions] == ["name"]


def test_candidates_include_fuzzy_names_and_skip_oversized_blocks() -> None:
    records = {"r1": rec(name="acme clinic"), "r2": rec(name="acme clinics"),
               "r3": rec(name="bolt plumbing")}
    assert candidate_pairs(records, DEFAULT_SCORING, 100).pairs == {("r1", "r2")}
    crowded = {f"r{i}": rec(name="acme clinic") for i in range(5)}
    cands = candidate_pairs(crowded, DEFAULT_SCORING, 4)
    assert not cands.pairs and cands.skipped_blocks > 0


def test_a_rule_set_from_before_scoring_merges_on_its_keys_only() -> None:
    doc = RuleSetDocument(deterministic_rules=[DeterministicRule(rule_id="same-tax-id",
                                                                 attrs=["tax_id"])])
    cfg = effective_scoring(doc)
    shared = dict(name="acme clinic", bank_acct="9", email="a@x.example")
    records = {"a": rec(tax_id="1", **shared), "b": rec(tax_id="2", **shared),
               "c": rec(tax_id="1", name="other")}
    scored, _ = score_all(records, cfg, 100)
    assert {(p.a, p.b) for p in scored if p.decision == "merge"} == {("a", "c")}


def override(kind: str, *ids: str):
    return SimpleNamespace(kind=kind, record_ids=list(ids))


def test_compute_merges_duplicates_and_queues_borderline_pairs() -> None:
    records = {
        "d1": rec(tax_id="1", name="acme clinic llc"),
        "d2": rec(tax_id="1", name="acme clinic"),
        "b1": rec(name="bolt plumbing", phone="+1", address="9 elm st"),
        "b2": rec(name="bolt plumbing inc", phone="+1", address="9 elm st"),
        "z": rec(name="zulu"),
    }
    out = compute(records, RuleSetDocument(scoring=DEFAULT_SCORING), [])
    assert out.uf.find("d1") == out.uf.find("d2") != out.uf.find("b1")
    assert [(p.a, p.b) for p in out.review] == [("b1", "b2")]
    assert out.fired["d1"] == {"same-tax-id"} and out.stats.pairs_merged == 1


def test_known_different_and_manual_decisions_win() -> None:
    records = {"d1": rec(tax_id="1"), "d2": rec(tax_id="1"), "x": rec(name="x"), "y": rec(name="y")}
    doc = RuleSetDocument(scoring=DEFAULT_SCORING)
    apart = compute(records, doc, [override("known_different", "d1", "d2")])
    assert apart.uf.find("d1") != apart.uf.find("d2") and apart.stats.blocked_known_different == 1
    joined = compute(records, doc, [override("merge", "x", "y")])
    assert joined.uf.find("x") == joined.uf.find("y") and joined.manual == {"x", "y"}


def test_the_group_size_cap_stops_a_chain() -> None:
    records = {f"r{i}": rec(tax_id="1") for i in range(6)}
    doc = RuleSetDocument(scoring=DEFAULT_SCORING, constraints=Constraints(max_cluster_size=3))
    out = compute(records, doc, [])
    assert max(len(m) for m in out.uf.members.values()) == 3 and out.stats.blocked_size_cap > 0


def test_the_default_merges_on_the_tin_only_as_before() -> None:
    assert DEFAULT_SCORING.attributes["tax_id"].merge_alone
    assert not any(a.merge_alone for k, a in DEFAULT_SCORING.attributes.items() if k != "tax_id")


def test_the_explanation_lists_what_decided_the_score_not_every_difference() -> None:
    a = rec(tax_id="1", name="acme clinic", phone="+1")
    b = rec(tax_id="1", name="acme clinic", phone="+2")
    p = score(a, b)
    assert p.lines() == ["SSN / tax ID: exact match (merges on its own)",
                         "Name: exact match (+25 points)"]
    assert len(p.contributions) == 3  # the review screen still shows the phone difference
    blocked = score(rec(tax_id="1", name="x"), rec(tax_id="2", name="x"))
    assert "SSN / tax ID: differs" in blocked.lines()


def test_the_document_the_screen_sends_is_a_valid_rule_set() -> None:
    from graphy.schemas.rules import RuleSetCreate

    payload = {"scoring": DEFAULT_SCORING.model_dump(mode="json"),
               "constraints": {"max_cluster_size": 50, "max_block_size": 1000}}
    made = RuleSetCreate.model_validate(
        {"name": "person-rules", "entity_type": "Person", "document": payload})
    assert made.document.scoring == DEFAULT_SCORING


def test_settings_that_make_no_sense_are_refused() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Scoring(review=80, auto_merge=60)  # review above merge
    with pytest.raises(ValidationError):
        Scoring(attributes={"provider_type": AttributeScoring()})  # not a scored attribute
    with pytest.raises(ValidationError):
        AttributeScoring(min_similarity=0.2)
    with pytest.raises(ValidationError):
        AttributeScoring(strength="huge")  # type: ignore[arg-type]


# ---- people: names by their parts, dates of birth, and aliases from the review band

PERSON = DEFAULT_SCORING_BY_TYPE["Person"]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("chris smith", "christopher smith"),
        ("john smith", "john adam smith"),
        ("john a smith", "john smith"),
        ("j smith", "john smith"),
        ("bob jones", "robert jones"),
        ("john smith", "john smith"),
    ],
)
def test_names_that_could_be_one_person(a: str, b: str) -> None:
    lever = AttributeScoring(compare="name_parts")
    assert name_parts_similarity(a, b, lever) > 0 and name_parts_similarity(b, a, lever) > 0


@pytest.mark.parametrize(
    ("a", "b"),
    [("chris smith", "chris jones"), ("john smith", "mary smith"), ("smith", "john smith")],
)
def test_names_that_are_not(a: str, b: str) -> None:
    assert name_parts_similarity(a, b, AttributeScoring(compare="name_parts")) == 0.0


def test_the_name_levers_change_what_counts() -> None:
    strict = AttributeScoring(compare="name_parts", nicknames=False, min_similarity=1.0)
    assert name_parts_similarity("chris smith", "christopher smith", strict) == 0.0
    loose = AttributeScoring(compare="name_parts", surname_exact=False)
    assert name_parts_similarity("john smith", "john smyth", loose) == 1.0
    assert name_parts_similarity("john smith", "john smyth", AttributeScoring(compare="name_parts")) == 0.0
    close_first = AttributeScoring(compare="name_parts", min_similarity=0.8)
    assert 0.8 <= name_parts_similarity("jonathan smith", "johnathan smith", close_first) < 1.0


def test_a_name_variant_on_the_same_date_of_birth_is_a_probable_alias() -> None:
    a = rec(name="chris smith", dob="1980-01-01", tax_id="1", email="a@x.example")
    b = rec(name="christopher smith", dob="1980-01-01", tax_id="2", email="b@x.example")
    p = score(a, b, PERSON)
    assert (p.score, p.decision) == (75, "review")  # a name (25) and a date of birth (50)


def test_a_score_alone_never_merges_people_unless_the_rule_set_says_so() -> None:
    same = dict(name="chris smith", dob="1980-01-01", phone="+1", bank_acct="9")
    p = score(rec(**same), rec(**same), PERSON)
    assert p.score == 100 and p.decision == "review"
    assert "does not merge" in p.reason
    merging = PERSON.model_copy(update={"merge_by_score": True})
    assert score(rec(**same), rec(**same), merging).decision == "merge"


def test_the_same_date_of_birth_without_a_matching_name_is_nothing() -> None:
    a = rec(name="chris smith", dob="1980-01-01", phone="+1")
    b = rec(name="mary jones", dob="1980-01-01", phone="+1")
    assert score(a, b, PERSON).code == "no_identity"


def test_a_tax_id_or_an_email_still_merges_people_on_its_own() -> None:
    assert score(rec(tax_id="1", name="a b"), rec(tax_id="1", name="c d"), PERSON).decision == "merge"
    assert score(rec(email="x@y.example", name="a b"), rec(email="x@y.example", name="c d"),
                 PERSON).decision == "merge"


def test_a_date_of_birth_can_be_compared_by_year() -> None:
    cfg = Scoring(attributes={"dob": AttributeScoring(strength="strong", compare="year")},
                  require_identity_match=False)
    p = score(rec(dob="1980-01-01"), rec(dob="1980-07-30"), cfg)
    assert p.score == 40 and p.contributions[0].outcome == "similar"  # 0.8 of 50
    assert score(rec(dob="1980-01-01"), rec(dob="1981-01-01"), cfg).score == 0


def test_what_says_who_a_vehicle_is_differs_from_a_person() -> None:
    vehicle = DEFAULT_SCORING_BY_TYPE["Vehicle"]
    assert vehicle.identity == ["vin", "plate_number"]
    assert score(rec(vin="V1"), rec(vin="V1"), vehicle).decision == "merge"
    assert score(rec(plate_number="AB12"), rec(plate_number="AB12"), vehicle).code == "low"


def test_every_type_has_defaults_and_types_with_nothing_to_compare_never_merge() -> None:
    keys = {t: sorted(a for a, v in s.attributes.items() if v.merge_alone)
            for t, s in DEFAULT_SCORING_BY_TYPE.items()}
    assert keys["Person"] == ["email", "tax_id"] and keys["Vehicle"] == ["vin"]
    assert default_rule_set("Claim").scoring == Scoring()


def _ids(*people: tuple[str, dict]):
    return {pid: r for pid, r in people}


def test_probable_aliases_come_out_of_the_same_scoring_that_merges() -> None:
    records = _ids(
        ("p1", rec(name="chris smith", dob="1980-01-01", tax_id="1")),
        ("p2", rec(name="christopher smith", dob="1980-01-01", tax_id="2")),
        ("p3", rec(name="mary jones", dob="1975-05-05", tax_id="3")),
    )
    doc = default_rule_set("Person")
    out = compute(records, doc, [])
    [(a, b, score_, why)] = out.aliases
    assert a != b and score_ == 75 and "Name" in why and "Date of birth" in why
    assert out.uf.find("p1") != out.uf.find("p2")  # nothing is merged
    assert [(p.a, p.b) for p in out.review] == [("p1", "p2")]


def test_a_confirmed_alias_merges_and_a_rejected_one_stops_being_asked_about() -> None:
    records = _ids(
        ("p1", rec(name="chris smith", dob="1980-01-01")),
        ("p2", rec(name="christopher smith", dob="1980-01-01")),
    )
    doc = default_rule_set("Person")
    joined = compute(records, doc, [override("merge", "p1", "p2")])
    assert joined.aliases == [] and joined.uf.find("p1") == joined.uf.find("p2")
    apart = compute(records, doc, [override("known_different", "p1", "p2")])
    assert apart.aliases == [] and apart.review == []


def test_scoring_settings_that_make_no_sense_are_refused_for_identity_too() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Scoring(identity=["favourite_colour"])
