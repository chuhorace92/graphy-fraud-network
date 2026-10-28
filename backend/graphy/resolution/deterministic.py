"""Level 1 resolution (ER-1, ER-6, ER-7, ER-8, TRD 4 steps 3-7).

Pairs of source records are scored against the published rule set of their entity type
(resolution.scoring): a pair that matches on a key that merges on its own (a tax ID, an email, a
VIN), or scores high enough where the rule set lets a score merge, is merged; a borderline pair
is queued for a person and drawn on the graph as a probable alias (ALIAS_OF), never merged.
Manual merges and known-different decisions from resolution_override always win, and a
cluster-size cap guards against chaining.

Source records and attribute edges are never modified; only Entity nodes and RESOLVED_TO
edges are rewritten, so any merge can be undone by re-running with an override.
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from neo4j import Driver
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from graphy.catalog import AttributeDefinition
from graphy.config import Settings
from graphy.db.models import ResolutionOverride, ReviewPair, RuleSet
from graphy.resolution.scoring import PairScore, Record, Value, rule_id, score_all
from graphy.schemas.resolution import SimGroup, SimReview, Simulation
from graphy.schemas.rules import (
    SCORED_ATTRIBUTES,
    RuleSetDocument,
    default_rule_set,
    effective_scoring,
)

log = logging.getLogger(__name__)


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {i: i for i in items}
        self.members: dict[str, set[str]] = {i: {i} for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> str:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        return ra


@dataclass
class ResolutionStats:
    records: int = 0
    entities: int = 0
    merged_records: int = 0
    blocked_known_different: int = 0
    blocked_size_cap: int = 0
    skipped_oversized_blocks: int = 0
    skipped_rules: list[str] = field(default_factory=list)
    pairs_compared: int = 0
    pairs_merged: int = 0
    pairs_review: int = 0
    alias_links: int = 0
    blocked_by_conflict: int = 0
    no_identity_match: int = 0

    def counts(self) -> dict[str, Any]:
        return self.__dict__.copy()


def published_rule_set(session: Session, entity_type: str) -> tuple[RuleSetDocument, str]:
    row = session.scalars(
        select(RuleSet)
        .where(RuleSet.entity_type == entity_type, RuleSet.state == "published")
        .order_by(RuleSet.published_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return default_rule_set(entity_type), "default"
    return RuleSetDocument.model_validate(row.document), f"{row.name}@v{row.version}"


def _entity_id(record_ids: set[str]) -> str:
    # Keyed on the smallest member so an entity keeps its id while it only gains records.
    return "E-" + hashlib.sha1(min(record_ids).encode(), usedforsecurity=False).hexdigest()[:16]


def load_records(session: Any, entity_type: str) -> dict[str, Record]:
    """Every source record of the type with the current values of the attributes we compare."""
    records: dict[str, Record] = {}
    rows = session.run(
        """
        MATCH (r:SourceRecord {entity_type: $etype})
        OPTIONAL MATCH (r)-[h:HAS_ATTRIBUTE]->(v:AttributeValue) WHERE h.is_current
        RETURN r.id AS rid, v.attr_type AS attr, v.id AS vid, v.normalized AS norm,
               coalesce(v.raw, v.display) AS display  // as written; secret values stay masked
        """,
        etype=entity_type,
    )
    for row in rows:
        rec = records.setdefault(row["rid"], {})
        if row["attr"] in SCORED_ATTRIBUTES:
            rec.setdefault(row["attr"], []).append(
                Value(row["vid"], row["norm"], row["display"] or ""))
    return records


@dataclass
class Computed:
    """What a rule set does to a set of records, before anything is written."""

    uf: _UnionFind
    stats: ResolutionStats
    fired: dict[str, set[str]]
    best: dict[str, PairScore]  # per record: the strongest pair that merged it
    manual: set[str]
    review: list[PairScore]
    labels: dict[str, str]
    # Entity-level links for the review pairs: (entity a, entity b, score, why), a < b.
    aliases: list[tuple[str, str, int, str]] = field(default_factory=list)


MAX_REVIEW_PAIRS = 500


def compute(records: dict[str, Record], doc: RuleSetDocument,
            overrides: list[ResolutionOverride]) -> Computed:
    """Score every candidate pair, merge what the rule set says to merge (manual decisions
    first, and never past a known-different decision or the group-size cap), and list the
    borderline pairs a person should look at."""
    stats = ResolutionStats(records=len(records))
    uf = _UnionFind(list(records))
    known = set(records)
    known_different: dict[str, set[str]] = defaultdict(set)
    for o in overrides:
        if o.kind == "known_different":
            ids = [i for i in o.record_ids if i in known]
            for a in ids:
                known_different[a].update(x for x in ids if x != a)

    fired: dict[str, set[str]] = defaultdict(set)
    best: dict[str, PairScore] = {}
    manual: set[str] = set()

    def blocked(a: str, b: str) -> bool:
        left, right = uf.members[uf.find(a)], uf.members[uf.find(b)]
        return any(known_different[x] & right for x in left)

    def try_union(a: str, b: str) -> bool:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            return True
        if blocked(a, b):
            stats.blocked_known_different += 1
            return False
        if len(uf.members[ra]) + len(uf.members[rb]) > doc.constraints.max_cluster_size:
            stats.blocked_size_cap += 1
            return False
        uf.union(a, b)
        return True

    # Manual merges first so automatic links cannot block them through the size cap.
    for o in overrides:
        if o.kind == "merge":
            ids = [i for i in o.record_ids if i in known]
            for other in ids[1:]:
                if try_union(ids[0], other):
                    manual.update((ids[0], other))

    if doc.scoring is None:  # a rule set from before scoring: keys it cannot express are skipped
        stats.skipped_rules.extend(r.rule_id for r in doc.deterministic_rules
                                   if len(r.attrs) != 1)
    scored, cands = score_all(records, effective_scoring(doc), doc.constraints.max_block_size)
    stats.pairs_compared = len(scored)
    stats.skipped_oversized_blocks = cands.skipped_blocks
    stats.blocked_by_conflict = sum(p.code == "blocked" for p in scored)
    stats.no_identity_match = sum(p.code == "no_identity" for p in scored)

    merging = sorted((p for p in scored if p.decision == "merge"),
                     key=lambda p: (not p.merge_alone, -p.score, p.a, p.b))
    for p in merging:
        if not try_union(p.a, p.b):
            continue
        stats.pairs_merged += 1
        ids = [rule_id(c.attr) for c in p.contributions if c.merges_alone] or ["scored-match"]
        for rid in (p.a, p.b):
            fired[rid].update(ids)
            if rid not in best or p.score > best[rid].score:
                best[rid] = p

    candidates = sorted((p for p in scored if p.decision == "review"
                         and uf.find(p.a) != uf.find(p.b) and not blocked(p.a, p.b)),
                        key=lambda p: (-p.score, p.a, p.b))
    review = candidates[:MAX_REVIEW_PAIRS]
    stats.pairs_review = len(review)
    # The same pairs, seen between the entities they belong to: probable aliases.
    links: dict[tuple[str, str], tuple[int, str]] = {}
    for p in candidates:
        ea, eb = _entity_id(uf.members[uf.find(p.a)]), _entity_id(uf.members[uf.find(p.b)])
        key = (min(ea, eb), max(ea, eb))
        if key not in links:  # candidates are strongest first
            links[key] = (p.score, "; ".join(p.lines()))
    aliases = [(a, b, score, why) for (a, b), (score, why) in sorted(links.items())]
    stats.alias_links = len(aliases)
    labels = {rid: (rec["name"][0].display if rec.get("name") else rid)
              for rid, rec in records.items()}
    return Computed(uf, stats, fired, best, manual, review, labels, aliases)


def simulate(*, entity_type: str, doc: RuleSetDocument, driver: Driver, pg: Session,
             settings: Settings) -> Simulation:
    """Run the rule set over today's records and report what would change, writing nothing."""
    with driver.session(database=settings.neo4j_database) as session:
        records = load_records(session, entity_type)
        if not records:
            return Simulation(records=0, entities=0, merged_records=0, merge_pairs=0,
                              review_pairs=0, blocked_by_conflict=0, no_identity_match=0,
                              current_entities=0, changed_groups=0, merges=[], reviews=[])
        overrides = list(pg.scalars(select(ResolutionOverride).where(
            ResolutionOverride.active.is_(True))))
        out = compute(records, doc, overrides)
        now = [frozenset(r["recs"]) for r in session.run(
            """
            MATCH (r:SourceRecord {entity_type: $etype})-[:RESOLVED_TO]->(e:Entity)
            RETURN e.entity_id AS e, collect(r.id) AS recs
            """, etype=entity_type)]
    groups = [frozenset(m) for m in out.uf.members.values()]
    merged = [g for g in groups if len(g) > 1]
    changed = sorted((g for g in merged if g not in set(now)), key=lambda g: (-len(g), min(g)))
    return Simulation(
        records=len(records), entities=len(groups), merged_records=sum(len(g) for g in merged),
        merge_pairs=out.stats.pairs_merged, review_pairs=out.stats.pairs_review,
        blocked_by_conflict=out.stats.blocked_by_conflict,
        no_identity_match=out.stats.no_identity_match, current_entities=len(now),
        changed_groups=len(changed),
        merges=[SimGroup(labels=sorted(out.labels[r] for r in g)[:6], records=len(g))
                for g in changed[:8]],
        reviews=[SimReview(label_a=out.labels[p.a], label_b=out.labels[p.b], score=p.score,
                           reason=p.reason) for p in out.review[:8]])


def review_payload(p: PairScore, labels: dict[str, str], entity_type: str) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "label_a": labels.get(p.a, p.a), "label_b": labels.get(p.b, p.b), "reason": p.reason,
        "attrs": [{"attr": c.attr, "outcome": c.outcome, "similarity": round(c.similarity, 3),
                   "points": round(c.points, 1), "left": c.left, "right": c.right,
                   "text": c.text()} for c in p.contributions],
    }


def resolve_entity_type(
    *,
    entity_type: str,
    run_id: str,
    driver: Driver,
    pg: Session,
    settings: Settings,
) -> ResolutionStats:
    doc, version = published_rule_set(pg, entity_type)

    with driver.session(database=settings.neo4j_database) as session:
        records = load_records(session, entity_type)
        if not records:
            return ResolutionStats()
        overrides = list(pg.scalars(select(ResolutionOverride).where(
            ResolutionOverride.active.is_(True))))
        out = compute(records, doc, overrides)
        stats, uf = out.stats, out.uf

        entities = []
        for root in {uf.find(r) for r in records}:
            members = uf.members[root]
            if len(members) > 1:
                stats.merged_records += len(members)
            entities.append({
                "entity_id": _entity_id(members),
                "members": [
                    {
                        "record_id": m,
                        "score": out.best[m].score / 100 if m in out.best else 1.0,
                        "rules_fired": sorted(out.fired[m]) or (
                            ["manual"] if m in out.manual else ["singleton"]),
                        "method": "manual" if m in out.manual else "auto",
                        "contributions": out.best[m].lines() if m in out.best else (
                            ["A manual decision by an analyst"] if m in out.manual else []),
                    }
                    for m in sorted(members)
                ],
            })
        stats.entities = len(entities)
        _publish(session, entities, entity_type=entity_type, version=version, run_id=run_id)
        _publish_aliases(session, out.aliases, entity_type=entity_type)

    # The queue is rebuilt each run from what is borderline now; decisions already made live
    # on as overrides. Only this type's pending pairs are replaced.
    pg.execute(delete(ReviewPair).where(
        ReviewPair.status == "pending",
        ReviewPair.contributions["entity_type"].as_string() == entity_type))
    for p in out.review:
        pg.add(ReviewPair(record_a=p.a, record_b=p.b, score=p.score, status="pending",
                          contributions=review_payload(p, out.labels, entity_type)))
    log.info("resolution %s %s: %s", entity_type, run_id, stats.counts())
    return stats


def _publish(session: Any, entities: list[dict[str, Any]], *, entity_type: str, version: str,
             run_id: str) -> None:
    for i in range(0, len(entities), 2_000):
        session.execute_write(lambda tx, batch=entities[i : i + 2_000]: tx.run(
            """
            UNWIND $entities AS e
            MERGE (n:Entity {entity_id: e.entity_id})
            ON CREATE SET n.created_at = datetime()
            SET n.entity_type = $etype, n.rule_set_version = $version, n.run_id = $run_id
            WITH n, e
            UNWIND e.members AS m
            MATCH (r:SourceRecord {id: m.record_id})
            MERGE (r)-[x:RESOLVED_TO]->(n)
            SET x.score = m.score, x.rules_fired = m.rules_fired, x.method = m.method,
                x.contributions = m.contributions,
                x.rule_set_version = $version, x.run_id = $run_id
            """,
            entities=batch, etype=entity_type, version=version, run_id=run_id,
        ).consume())

    # Retire what this run no longer produces. Not yet a single atomic swap (TRD 4 step 7):
    # readers can briefly see both generations between the writes above and this cleanup.
    session.run(
        """
        MATCH (:SourceRecord {entity_type: $etype})-[x:RESOLVED_TO]->(:Entity)
        WHERE x.run_id <> $run_id
        DELETE x
        """,
        etype=entity_type, run_id=run_id,
    ).consume()
    session.run(
        "MATCH (n:Entity {entity_type: $etype}) WHERE n.run_id <> $run_id DETACH DELETE n",
        etype=entity_type, run_id=run_id,
    ).consume()
    session.run(
        """
        MATCH (n:Entity {entity_type: $etype, run_id: $run_id})
              <-[:RESOLVED_TO]-(:SourceRecord)-[:HAS_ATTRIBUTE]->(v:AttributeValue)
        WHERE v.attr_type = 'name'
        WITH n, coalesce(v.raw, v.display) AS name, count(*) AS seen
        ORDER BY seen DESC, name
        WITH n, collect(name)[0] AS best
        SET n.canonical_name = best
        """,
        etype=entity_type, run_id=run_id,
    ).consume()


def _publish_aliases(session: Any, links: list[tuple[str, str, int, str]], *,
                     entity_type: str) -> None:
    """Replace the type's ALIAS_OF links with the pairs found now: entities a person is asked
    about, drawn on the graph, never merged."""
    session.run("MATCH (:Entity {entity_type: $etype})-[x:ALIAS_OF]->() DELETE x",
                etype=entity_type).consume()
    session.run(
        """
        UNWIND $links AS l
        MATCH (a:Entity {entity_id: l.a}), (b:Entity {entity_id: l.b})
        CREATE (a)-[:ALIAS_OF {rel_type: 'alias', score: l.score, reason: l.why}]->(b)
        """,
        links=[{"a": a, "b": b, "score": score / 100, "why": why} for a, b, score, why in links],
    ).consume()


def rebuild_shares(*, driver: Driver, catalog: dict[str, AttributeDefinition],
                   settings: Settings) -> dict[str, int]:
    """Derive SHARES edges between entities holding the same value (TRD 3).

    Values held by more entities than the attribute's hub_threshold are flagged is_hub and
    create no links, so a registered-agent address does not join hundreds of companies.
    """
    counts: dict[str, int] = {}
    with driver.session(database=settings.neo4j_database) as session:
        session.run(
            "MATCH ()-[s:SHARES]->() CALL (s) { DELETE s } IN TRANSACTIONS OF 10000 ROWS"
        ).consume()
        for attr, defn in catalog.items():
            if defn.link_weight == 0:
                continue
            summary = session.run(
                """
                MATCH (v:AttributeValue {attr_type: $attr})
                      <-[:HAS_ATTRIBUTE]-(:SourceRecord)-[:RESOLVED_TO]->(e:Entity)
                WITH v, collect(DISTINCT e) AS ents
                SET v.degree = size(ents),
                    v.is_hub = $threshold IS NOT NULL AND size(ents) > $threshold
                WITH v, ents WHERE NOT v.is_hub AND size(ents) > 1
                UNWIND ents AS a
                UNWIND ents AS b
                WITH v, a, b WHERE a.entity_id < b.entity_id
                CREATE (a)-[:SHARES {attr_type: v.attr_type, attr_value_id: v.id,
                                     weight: $weight}]->(b)
                """,
                attr=attr, threshold=defn.hub_threshold, weight=defn.link_weight,
            ).consume()
            counts[attr] = summary.counters.relationships_created
    return counts
