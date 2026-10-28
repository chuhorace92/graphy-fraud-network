import pytest

from graphy.catalog import DEFAULT_CATALOG
from graphy.ingestion.normalize import NormalizationError, normalize, standardize

KEY = "test-key"


@pytest.mark.parametrize(
    ("attr", "raw", "expected"),
    [
        ("phone", "(415) 555-0132", "+14155550132"),
        ("phone", "+44 20 7946 0958", "+442079460958"),
        ("email", "  Jane.Doe@Example.COM ", "jane.doe@example.com"),
        ("name", "José  O'Brien-Núñez", "jose o'brien-nunez"),
        ("address", "12 Oak Street, Apartment 4", "12 OAK ST APT 4"),
        ("tax_id", "900-12-3456", "900123456"),
        ("dob", "1980-02-29", "1980-02-29"),
        ("loss_type", "  Bodily   Injury ", "bodily injury"),
        ("claim_amount", "$12,500.5", "12500.50"),
    ],
)
def test_standardize(attr: str, raw: str, expected: str) -> None:
    assert standardize(DEFAULT_CATALOG[attr], raw) == expected


@pytest.mark.parametrize(("attr", "raw"), [("email", "not-an-email"), ("dob", "02/29/1980"),
                                          ("phone", "12"), ("name", "   ")])
def test_rejects_bad_values(attr: str, raw: str) -> None:
    with pytest.raises(NormalizationError):
        standardize(DEFAULT_CATALOG[attr], raw)


def test_secret_values_are_never_kept_in_clear() -> None:
    v = normalize(DEFAULT_CATALOG["tax_id"], "900-12-3456", KEY)
    assert v.raw is None and v.normalized is None
    assert v.display == "•••3456"
    assert "900123456" not in v.value_id


def test_same_value_same_id_regardless_of_formatting() -> None:
    a = normalize(DEFAULT_CATALOG["phone"], "(415) 555-0132", KEY)
    b = normalize(DEFAULT_CATALOG["phone"], "+1 415 555 0132", KEY)
    assert a.value_id == b.value_id


def test_hash_is_keyed() -> None:
    a = normalize(DEFAULT_CATALOG["tax_id"], "900123456", "key-one")
    b = normalize(DEFAULT_CATALOG["tax_id"], "900123456", "key-two")
    assert a.hash != b.hash


def test_text_and_amount_display_as_written() -> None:
    desc = normalize(DEFAULT_CATALOG["loss_description"], "Rear-ended  at Oak St.", KEY)
    assert desc.display == "Rear-ended at Oak St."
    assert normalize(DEFAULT_CATALOG["claim_amount"], "12500", KEY).display == "$12,500.00"


def test_claim_type_is_a_multi_valued_tag() -> None:
    assert DEFAULT_CATALOG["loss_type"].versioning == "multi"
    assert DEFAULT_CATALOG["loss_type"].applies_to == ["Claim"]


def test_claim_amount_rejects_junk() -> None:
    with pytest.raises(NormalizationError):
        standardize(DEFAULT_CATALOG["claim_amount"], "n/a")


def test_descriptive_attributes_describe_the_entity_itself() -> None:
    descriptive = {k for k, d in DEFAULT_CATALOG.items() if d.descriptive}
    assert descriptive == {
        "name", "loss_date", "fnol_date", "loss_type", "loss_description", "claim_status",
        "claim_amount", "incorporation_date", "policy_inception_date", "policy_expiry_date",
        "policy_type", "policy_term", "policy_status", "plate_state", "vehicle_make",
        "vehicle_model", "vehicle_year", "siu_referred", "siu_accepted", "siu_outcome",
    }
    assert all(DEFAULT_CATALOG[k].link_weight == 0 for k in descriptive)  # never link anyone
