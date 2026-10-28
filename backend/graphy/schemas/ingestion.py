"""JSON ingestion payload: records with their attributes, and the relationships between them.

    {
      "source": "crm",
      "records": [
        {"source_key": "C-1001", "entity_type": "Person",
         "attributes": {"name": "Jane Doe",
                        "email": ["jane@example.com", "jd@example.net"],
                        "phone": {"value": "(555) 010-2000", "first_seen": "2021-03-01"}}}
      ],
      "relationships": [{"from_key": "C-1001", "to_key": "CLM-9", "rel_type": "insured"}]
    }

An attribute is a value, a list of values, or {value, first_seen, last_seen}. It flattens to the
same rows the CSV layouts use, so validation, history and resolution behave identically.
"""

from pydantic import BaseModel, Field

from graphy.ingestion.loader import Row

Scalar = str | int | float
MAX_RECORDS = 20_000


class Dated(BaseModel):
    value: Scalar
    first_seen: str | None = None
    last_seen: str | None = None


AttributeValue = Scalar | Dated


class RecordIn(BaseModel):
    source_key: str = Field(min_length=1, max_length=256)
    entity_type: str
    attributes: dict[str, AttributeValue | list[AttributeValue]]
    first_seen: str | None = None  # defaults for every attribute of this record
    last_seen: str | None = None


class RelationshipIn(BaseModel):
    from_key: str = Field(min_length=1)
    to_key: str = Field(min_length=1)
    rel_type: str
    first_seen: str | None = None
    last_seen: str | None = None


class BatchIn(BaseModel):
    source: str
    resolve_after: bool = True
    records: list[RecordIn] = Field(default=[], max_length=MAX_RECORDS)
    relationships: list[RelationshipIn] = Field(default=[], max_length=MAX_RECORDS * 5)

    def to_rows(self) -> tuple[list[Row], list[Row]]:
        """(attribute rows, relationship rows) in the canonical CSV layouts."""
        attrs: list[Row] = []
        for rec in self.records:
            for attr_type, given in rec.attributes.items():
                for item in given if isinstance(given, list) else [given]:
                    d = item if isinstance(item, Dated) else Dated(value=item)
                    attrs.append({
                        "source_key": rec.source_key, "entity_type": rec.entity_type,
                        "attr_type": attr_type, "value": str(d.value),
                        "first_seen": d.first_seen or rec.first_seen or "",
                        "last_seen": d.last_seen or rec.last_seen or "",
                    })
        rels = [{k: v or "" for k, v in r.model_dump().items()} for r in self.relationships]
        return attrs, rels
