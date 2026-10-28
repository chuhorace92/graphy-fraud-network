from graphy.catalog import DEFAULT_CATALOG
from graphy.ingestion.normalize import NormalizationError, normalize
from graphy.scripts.seed_demo import generate


def test_seed_rows_are_all_valid() -> None:
    rows = generate(people=60, rings=2)
    bad = []
    for row in rows:
        try:
            normalize(DEFAULT_CATALOG[row["attr_type"]], row["value"], "k")
        except NormalizationError as exc:
            bad.append((row, exc))
    assert not bad, bad[:3]


def test_seed_plants_a_phone_hub() -> None:
    rows = generate(people=60, rings=1)
    phones: dict[str, set[str]] = {}
    for r in rows:
        if r["attr_type"] == "phone":
            phones.setdefault(r["value"], set()).add(r["source_key"])
    assert max(len(v) for v in phones.values()) > DEFAULT_CATALOG["phone"].hub_threshold


def test_seed_relationships_are_valid_and_typed() -> None:
    from graphy.catalog import ENTITY_TYPES, REL_TYPES
    from graphy.scripts.seed_demo import generate_all

    rows, rels = generate_all(people=60, rings=2)
    etype = {r["source_key"]: r["entity_type"] for r in rows}
    assert set(etype.values()) == set(ENTITY_TYPES)
    for r in rels:
        src, dst = REL_TYPES[r["rel_type"]]
        assert etype[r["from_key"]] in src and etype[r["to_key"]] in dst, r


def test_seed_plants_name_variant_aliases() -> None:
    from graphy.resolution.scoring import name_parts_similarity
    from graphy.schemas.rules import AttributeScoring
    from graphy.scripts.seed_demo import generate

    lever = AttributeScoring(compare="name_parts")

    rows = generate(people=60, rings=1)
    names = {r["source_key"]: r["value"].casefold() for r in rows if r["attr_type"] == "name"}
    aliases = [k for k in names if k.startswith("ALIAS-")]
    assert aliases
    assert all(any(name_parts_similarity(names[a], n, lever) > 0 for k, n in names.items()
                   if not k.startswith("ALIAS-")) for a in aliases)


def test_every_claim_has_metadata() -> None:
    from collections import defaultdict
    from datetime import date

    from graphy.scripts.seed_demo import generate

    meta: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in generate(people=60, rings=2):
        if r["entity_type"] == "Claim":
            meta[r["source_key"]][r["attr_type"]].append(r["value"])
    assert meta
    for key, m in meta.items():
        assert {"loss_date", "fnol_date", "loss_type", "loss_description", "claim_status",
                "claim_amount", "name", "siu_referred", "siu_accepted",
                "siu_outcome"} <= set(m), key
        steps = ("siu_referred", "siu_accepted", "siu_outcome")
        yes = [m[a][0] == "Yes" for a in steps]
        assert yes == sorted(yes, reverse=True), key  # no later step without the first
        assert set(m["loss_type"]) <= {"Property Damage", "Bodily Injury"}
        assert date.fromisoformat(m["fnol_date"][0]) >= date.fromisoformat(m["loss_date"][0])
    tags = {tuple(sorted(m["loss_type"])) for m in meta.values()}
    assert ("Bodily Injury", "Property Damage") in tags and ("Property Damage",) in tags


def test_seed_has_fewer_redundant_links() -> None:
    from graphy.scripts.seed_demo import generate_all

    _, rels = generate_all(people=60, rings=2)
    kinds = {r["rel_type"] for r in rels}
    assert "covers" not in kinds  # claim -> policy and claim -> vehicle already say it
    vehicle_ends = {r["to_key"] for r in rels if r["rel_type"] in ("driver", "passenger")}
    assert all(k.startswith("CLM-") for k in vehicle_ends)  # roles attach to claims only


def test_policies_vehicles_and_organizations_carry_their_details() -> None:
    rows = generate(people=60, rings=1)
    have: dict[str, dict[str, set[str]]] = {}
    for r in rows:
        have.setdefault(r["entity_type"], {}).setdefault(r["source_key"], set()).add(r["attr_type"])
    for attrs in have["Policy"].values():
        assert {"policy_inception_date", "policy_expiry_date", "policy_type", "policy_term",
                "policy_status"} <= attrs
    for attrs in have["Vehicle"].values():
        assert {"plate_number", "plate_state", "vehicle_make", "vehicle_model",
                "vehicle_year"} <= attrs
    for attrs in have["Organization"].values():
        assert "incorporation_date" in attrs and "dob" not in attrs
    assert not any(r["attr_type"] == "dob" and r["entity_type"] != "Person" for r in rows)
