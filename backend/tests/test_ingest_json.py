import pytest
from pydantic import ValidationError

from graphy.ingestion.loader import read_json

DOC = b"""{
  "source": "crm",
  "records": [
    {"source_key": "C-1", "entity_type": "Person", "first_seen": "2021-03-01",
     "attributes": {"name": "Jane Doe",
                    "email": ["jane@example.com",
                              {"value": "jd@example.net", "last_seen": "2024-01-02"}],
                    "dob": {"value": "1980-02-29", "first_seen": "2020-01-01"}}},
    {"source_key": "CLM-9", "entity_type": "Claim",
     "attributes": {"name": "CLM-9", "claim_amount": 1200.5}}
  ],
  "relationships": [{"from_key": "C-1", "to_key": "CLM-9", "rel_type": "insured"}]
}"""


def test_json_flattens_to_the_canonical_rows() -> None:
    attrs, rels = read_json(DOC)
    emails = [a for a in attrs if a["attr_type"] == "email"]
    assert [a["value"] for a in emails] == ["jane@example.com", "jd@example.net"]
    assert emails[0]["first_seen"] == "2021-03-01"  # inherited from the record
    assert emails[1]["last_seen"] == "2024-01-02"
    dob = next(a for a in attrs if a["attr_type"] == "dob")
    assert dob["first_seen"] == "2020-01-01"
    assert next(a for a in attrs if a["attr_type"] == "claim_amount")["value"] == "1200.5"
    assert rels == [{"from_key": "C-1", "to_key": "CLM-9", "rel_type": "insured",
                     "first_seen": "", "last_seen": ""}]


def test_json_shape_is_checked() -> None:
    with pytest.raises(ValidationError):
        read_json(b'{"source": "crm", "records": '
                  b'[{"source_key": "", "entity_type": "Person", "attributes": {}}]}')
    with pytest.raises(ValidationError):
        read_json(b'{"records": []}')  # a source is required
