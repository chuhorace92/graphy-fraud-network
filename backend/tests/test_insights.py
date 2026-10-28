from graphy.services.insights import network_insights, severity


def _net(n_claims: int, *, same_provider: bool, days_apart: int = 10):
    members = {"clinic": {"type": "MedicalProvider", "label": "Acme Clinic"}}
    rels = []
    for i in range(n_claims):
        c, p, who = f"c{i}", f"p{i}", f"x{i}"
        members[c] = {"type": "Claim", "label": c}
        members[p] = {"type": "Policy", "label": p}
        members[who] = {"type": "Person", "label": f"Person {i}"}
        day = f"2026-01-{1 + i:02d}" if days_apart < 30 else f"{2020 + i}-06-01"
        rels += [
            {"src": c, "dst": p, "rel_type": "under_policy", "first_seen": day},
            {"src": who, "dst": p, "rel_type": "policyholder", "first_seen": "2020-01-01"},
            {"src": who, "dst": c, "rel_type": "insured", "first_seen": day},
        ]
        if same_provider or i == 0:
            rels.append({"src": "clinic", "dst": c, "rel_type": "treated_for", "first_seen": day})
    return members, rels


def test_ordinary_network_is_quiet() -> None:
    score, found = network_insights(*_net(5, same_provider=False, days_apart=60), [], [])
    assert score == 0 and found == []


def test_new_policy_and_tight_window() -> None:
    members, rels = _net(5, same_provider=False)
    for r in rels:  # policies started two weeks before each loss
        if r["rel_type"] == "policyholder":
            r["first_seen"] = "2025-12-20"
    _, found = network_insights(members, rels, [], [])
    flags = {f.rule_id: f for f in found}
    assert "5 claims filed within 60 days of the policy starting" == (
        flags["claims-soon-after-policy-start"].detail)
    assert "claims-bunched-in-time" in flags
    assert set(flags["claims-bunched-in-time"].entities) == {f"c{i}" for i in range(5)}


def test_alias_hit_names_both_entities() -> None:
    members, rels = _net(1, same_provider=False)
    _, found = network_insights(members, rels, [], [("x0", "other")])
    [hit] = [f for f in found if f.rule_id == "probable-aliases"]
    assert hit.entities == ["other", "x0"] and hit.severity == "medium"


def test_severity_bands() -> None:
    assert [severity(s) for s in (0, 34, 35, 59, 60, 100)] == [
        "low", "low", "medium", "medium", "high", "high"]
