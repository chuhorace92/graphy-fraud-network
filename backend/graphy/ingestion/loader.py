"""Batch ingestion into Neo4j (TRD section 8, X-1, X-2).

Phase 1 accepts one canonical "long" CSV layout, one attribute value per row:

    source_key,entity_type,attr_type,value,first_seen,last_seen

A second layout links records, one relationship per row (roles, policies, providers):

    from_key,to_key,rel_type,first_seen,last_seen

Relationship rows load after the records they name. Per-source column mappings (stored on
ingestion_source.mapping) come later; until then sources are converted to these layouts
before upload.
"""

import csv
import io
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from neo4j import Driver

from graphy.catalog import ENTITY_TYPES, REL_TYPES, AttributeDefinition
from graphy.config import Settings
from graphy.ingestion.normalize import NormalizationError, normalize

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"source_key", "entity_type", "attr_type", "value"}
REL_COLUMNS = {"from_key", "to_key", "rel_type"}
BATCH_SIZE = 5_000

Row = dict[str, str]

_LOAD_CYPHER = """
UNWIND $rows AS row
MERGE (r:SourceRecord {id: row.record_id})
  ON CREATE SET r.source_system = row.source_system, r.source_key = row.source_key,
                r.entity_type = row.entity_type, r.batch_id = $batch_id,
                r.ingested_at = datetime()
MERGE (v:AttributeValue {id: row.value_id})
  ON CREATE SET v.attr_type = row.attr_type, v.raw = row.raw, v.normalized = row.normalized,
                v.hash = row.hash, v.display = row.display, v.is_hub = false
MERGE (r)-[h:HAS_ATTRIBUTE]->(v)
  ON CREATE SET h.first_seen = row.first_seen, h.last_seen = row.last_seen,
                h.source_system = row.source_system, h.is_current = true
  ON MATCH SET h.first_seen = CASE WHEN row.first_seen < h.first_seen
                                   THEN row.first_seen ELSE h.first_seen END,
               h.last_seen = CASE WHEN row.last_seen > h.last_seen
                                  THEN row.last_seen ELSE h.last_seen END
"""

# Attribute history is kept by closing older edges, never deleting them. For each record and
# single-valued attribute type, only the most recently seen value stays current.
_CURRENT_CYPHER = """
UNWIND $record_ids AS rid
MATCH (r:SourceRecord {id: rid})-[h:HAS_ATTRIBUTE]->(v:AttributeValue)
WHERE NOT v.attr_type IN $multi_valued
WITH r, v.attr_type AS t, collect(h) AS edges
WITH edges, reduce(m = head(edges), x IN edges |
       CASE WHEN x.last_seen > m.last_seen THEN x ELSE m END) AS cur
UNWIND edges AS h
SET h.is_current = (h = cur)
"""


# Relationships live between source records, so entity resolution can still merge either end;
# entity-level RELATED_TO edges are derived from them after each resolution run.
_REL_CYPHER = """
UNWIND $rows AS row
MATCH (a:SourceRecord {id: row.from_id}), (b:SourceRecord {id: row.to_id})
WHERE a.entity_type IN $from_types AND b.entity_type IN $to_types
MERGE (a)-[x:REL {rel_type: $rel_type}]->(b)
  ON CREATE SET x.first_seen = row.first_seen, x.last_seen = row.last_seen,
                x.source_system = $source_system
RETURN row.line AS line
"""


@dataclass
class LoadResult:
    rows_read: int = 0
    rows_loaded: int = 0
    records: int = 0
    rejects: list[dict[str, Any]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "rows_read": self.rows_read,
            "rows_loaded": self.rows_loaded,
            "records": self.records,
            "rows_rejected": len(self.rejects),
        }


def _validate(
    row: dict[str, str],
    source_system: str,
    catalog: dict[str, AttributeDefinition],
    hash_key: str,
) -> dict[str, Any]:
    entity_type = (row.get("entity_type") or "").strip()
    if entity_type not in ENTITY_TYPES:
        raise NormalizationError(f"entity_type must be one of {', '.join(ENTITY_TYPES)}")
    source_key = (row.get("source_key") or "").strip()
    if not source_key:
        raise NormalizationError("source_key is required")
    attr_type = (row.get("attr_type") or "").strip()
    defn = catalog.get(attr_type)
    if defn is None:
        raise NormalizationError(f"unknown attr_type {attr_type!r}")
    if entity_type not in defn.applies_to:
        raise NormalizationError(f"{attr_type} does not apply to {entity_type}")

    value = normalize(defn, row.get("value") or "", hash_key)
    today = date.today().isoformat()
    first_seen = (row.get("first_seen") or "").strip() or today
    last_seen = (row.get("last_seen") or "").strip() or first_seen
    for label, d in (("first_seen", first_seen), ("last_seen", last_seen)):
        try:
            date.fromisoformat(d)
        except ValueError as exc:
            raise NormalizationError(f"{label} must be YYYY-MM-DD") from exc

    return {
        "record_id": f"{source_system}:{source_key}",
        "source_system": source_system,
        "source_key": source_key,
        "entity_type": entity_type,
        "attr_type": attr_type,
        "value_id": value.value_id,
        "raw": value.raw,
        "normalized": value.normalized,
        "hash": value.hash,
        "display": value.display,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_rows(
    rows: Iterable[dict[str, str]],
    *,
    source_system: str,
    batch_id: str,
    catalog: dict[str, AttributeDefinition],
    driver: Driver,
    settings: Settings,
) -> LoadResult:
    """Validate, normalize and MERGE rows. Replaying a batch does not duplicate data."""
    result = LoadResult()
    valid: list[dict[str, Any]] = []
    for line_no, row in enumerate(rows, start=2):  # line 1 is the header
        result.rows_read += 1
        try:
            valid.append(_validate(row, source_system, catalog, settings.hash_key))
        except NormalizationError as exc:
            # Rejects never echo the value itself: it may be a national ID.
            result.rejects.append(
                {"line": line_no, "source_key": row.get("source_key"),
                 "attr_type": row.get("attr_type"), "reason": str(exc)}
            )

    record_ids = sorted({r["record_id"] for r in valid})
    multi_valued = [k for k, d in catalog.items() if d.versioning == "multi"]
    with driver.session(database=settings.neo4j_database) as session:
        for chunk in _chunks(valid, BATCH_SIZE):
            session.execute_write(lambda tx, c=chunk: tx.run(_LOAD_CYPHER, rows=c,
                                                             batch_id=batch_id).consume())
        for ids in _chunks(record_ids, BATCH_SIZE):
            session.execute_write(lambda tx, i=ids: tx.run(
                _CURRENT_CYPHER, record_ids=i, multi_valued=multi_valued).consume())

    result.rows_loaded = len(valid)
    result.records = len(record_ids)
    log.info("batch %s: %s", batch_id, result.counts())
    return result


def load_relationships(
    rows: Iterable[dict[str, str]],
    *,
    source_system: str,
    batch_id: str,
    catalog: dict[str, AttributeDefinition],  # noqa: ARG001 - same signature as load_rows
    driver: Driver,
    settings: Settings,
) -> LoadResult:
    """MERGE relationship rows between already-loaded records. Unknown or mistyped ends reject."""
    result = LoadResult()
    by_type: dict[str, list[dict[str, Any]]] = {}
    for line_no, row in enumerate(rows, start=2):
        result.rows_read += 1
        rel_type = (row.get("rel_type") or "").strip().lower()
        a, b = (row.get("from_key") or "").strip(), (row.get("to_key") or "").strip()
        first = (row.get("first_seen") or "").strip() or date.today().isoformat()
        last = (row.get("last_seen") or "").strip() or first
        reason = None
        if rel_type not in REL_TYPES:
            reason = f"unknown rel_type {rel_type!r}"
        elif not a or not b:
            reason = "from_key and to_key are required"
        else:
            try:
                date.fromisoformat(first), date.fromisoformat(last)
            except ValueError:
                reason = "dates must be YYYY-MM-DD"
        if reason:
            result.rejects.append({"line": line_no, "source_key": a, "attr_type": rel_type,
                                   "reason": reason})
            continue
        by_type.setdefault(rel_type, []).append(
            {"line": line_no, "from_id": f"{source_system}:{a}", "to_id": f"{source_system}:{b}",
             "first_seen": first, "last_seen": last})

    with driver.session(database=settings.neo4j_database) as session:
        for rel_type, batch in by_type.items():
            params = dict(zip(("from_types", "to_types"), REL_TYPES[rel_type], strict=True),
                          rel_type=rel_type, source_system=source_system)
            for chunk in _chunks(batch, BATCH_SIZE):
                matched = session.execute_write(lambda tx, c=chunk, p=params: {
                    r["line"] for r in tx.run(_REL_CYPHER, rows=c, **p)})
                result.rows_loaded += len(matched)
                result.rejects.extend(
                    {"line": r["line"], "source_key": r["from_id"], "attr_type": rel_type,
                     "reason": "record not found, or wrong entity type for this relationship"}
                    for r in chunk if r["line"] not in matched)
    log.info("batch %s relationships: %s", batch_id, result.counts())
    return result


def read_csv(data: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    fields = set(reader.fieldnames or [])
    missing = REL_COLUMNS - fields if "from_key" in fields else REQUIRED_COLUMNS - fields
    if missing:
        raise NormalizationError(f"missing columns: {', '.join(sorted(missing))}")
    return list(reader)


def read_json(data: bytes) -> tuple[list[Row], list[Row]]:
    """A JSON batch (graphy.schemas.ingestion) as attribute rows and relationship rows."""
    from graphy.schemas.ingestion import BatchIn  # deferred: that module imports this one

    return BatchIn.model_validate_json(data).to_rows()


def load_json(data: bytes, **kw: Any) -> LoadResult:
    """Attributes first, then the relationships that point at them. A reject's `line` is the
    row's position within its own list, since JSON has no lines."""
    attrs, rels = read_json(data)
    a, r = load_rows(attrs, **kw), load_relationships(rels, **kw)
    return LoadResult(a.rows_read + r.rows_read, a.rows_loaded + r.rows_loaded, a.records,
                      a.rejects + r.rejects)

