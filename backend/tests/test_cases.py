import pytest
from pydantic import ValidationError

from graphy.schemas.cases import Authority, CaseClose, Report
from graphy.schemas.graph import Network
from graphy.services.cases import CLOSED, STATUS_LABEL, _summary, case_key


def _network(members: list[str]) -> Network:
    return Network(network_id="root", size=len(members), links=2, types={"Person": 2, "Claim": 1},
                   aliases=1, focus_id=members[-1], focus_label="Acme", via=["bank_acct"],
                   score=70, severity="high", flags=["shared bank account"], hits=[],
                   members=members)


def test_case_key_is_the_lowest_member() -> None:
    assert case_key(_network(["p9", "p2", "p5"])) == "p2"


def test_network_without_a_case_row_is_new_and_unassigned() -> None:
    s = _summary(_network(["p1", "p2", "p3"]), None, {})
    assert (s.case_key, s.status, s.assignee, s.updated_at) == ("p1", "new", None, None)


def test_a_case_adds_up_what_its_claims_are_for() -> None:
    s = _summary(_network(["c1", "p2", "c3"]), None, {"c1": 1200.0, "c3": 300.5, "other": 99.0})
    assert (s.claim_count, s.claimed_amount, s.aliases) == (1, 1500.5, 1)


def test_there_are_three_ways_to_close_a_case() -> None:
    assert CLOSED == ("confirmed", "insufficient", "dismissed")
    assert STATUS_LABEL["insufficient"] == "Not enough information"


def test_the_report_to_an_authority_is_part_of_the_closing_report() -> None:
    close = CaseClose(outcome="confirmed", summary="Ring confirmed", authority=Authority(
        reported=True, name="State Fraud Bureau", reference="SFB-2026-114",
        reported_on="2026-10-20", notes="Referred with the claim files."))
    saved = Report.model_validate(close.model_dump(mode="json"))
    assert saved.authority.reported and saved.authority.name == "State Fraud Bureau"
    assert str(saved.authority.reported_on) == "2026-10-20"
    assert Report().authority.reported is False  # not reported unless someone says so


def test_not_enough_information_is_a_valid_outcome_but_nothing_else_is() -> None:
    assert CaseClose(outcome="insufficient", summary="Awaiting records").outcome == "insufficient"
    with pytest.raises(ValidationError):
        CaseClose(outcome="inconclusive", summary="x")  # type: ignore[arg-type]
