"""Read queries behind the investigation canvas (NV-1..NV-6, GA-10).

All queries are parameterized. Hop counts are validated integers before being written into
the pattern, because Cypher cannot parameterize variable-length bounds.
"""

import re
from typing import Any, Literal

from neo4j import AsyncSession, Query

from graphy.catalog import DEFAULT_CATALOG, PARTY_TYPES
from graphy.config import get_settings
from graphy.resolution.deterministic import _UnionFind
from graphy.schemas.graph import (
    Appearance,
    AttributeVersion,
    EntityDetail,
    GraphEdge,
    GraphNode,
    GraphResponse,
    Hit,
    HitMatch,
    Lead,
    MergeExplanation,
    Network,
    Overview,
    RulePreview,
    RulePreviewHit,
    SearchHit,
)
from graphy.schemas.rules import AnalyticsRuleDocument
from graphy.services.insights import network_insights, severity

_LINKS = "SHARES|RELATED_TO|ALIAS_OF"

AttributeMode = Literal["shared", "all", "none"]

# Attribute types whose shared values link entities. This reads the default catalog; published
# catalog overrides (BRD 9.1) are not applied to the canvas yet.
_LINKING_ATTRS = [k for k, d in DEFAULT_CATALOG.items() if d.link_weight > 0]
# Names and claim details live in the entity's attribute list, not on the canvas.
_DESCRIPTIVE_ATTRS = [k for k, d in DEFAULT_CATALOG.items() if d.descriptive]


def _q(text: str) -> Query:
    return Query(text, timeout=get_settings().graph_query_timeout_s)


def _entity_node(e: dict[str, Any], parent: str | None = None) -> GraphNode:
    return GraphNode(
        id=e["entity_id"], kind="Entity", label=e.get("canonical_name") or e["entity_id"],
        parent=parent, entity_type=e.get("entity_type"), score=e.get("risk_score"),
        status=e.get("status"),
        data={"rule_set_version": e.get("rule_set_version")},
    )


_SIU_ATTRS = ["siu_referred", "siu_accepted", "siu_outcome"]


async def _with_claim_state(session: AsyncSession, nodes: list[GraphNode]) -> list[GraphNode]:
    """Claims carry their status and whether any SIU step happened, so the canvas can colour
    and flag them without a request per claim."""
    claims = {n.id: n for n in nodes if n.entity_type == "Claim"}
    if not claims:
        return nodes
    result = await session.run(_q("""
        MATCH (e:Entity)<-[:RESOLVED_TO]-(:SourceRecord)-[h:HAS_ATTRIBUTE]->(v:AttributeValue)
        WHERE e.entity_id IN $ids AND h.is_current AND v.attr_type IN $attrs
        RETURN e.entity_id AS id, v.attr_type AS attr, v.display AS value
        """), ids=list(claims), attrs=["claim_status", *_SIU_ATTRS])
    async for r in result:
        node = claims[r["id"]]
        if r["attr"] == "claim_status":
            node.data["claim_status"] = r["value"]
        elif r["value"].strip().casefold() == "yes":
            node.data["siu"] = True
    return nodes


def _edge(r: dict[str, Any]) -> GraphEdge:
    props = r["props"] or {}
    label = props.get("attr_type") or props.get("rel_type")
    return GraphEdge(id=r["id"], source=r["source"], target=r["target"], type=r["type"],
                     label=label, data=props)


async def _edges_between(session: AsyncSession, ids: list[str],
                         link_types: str = _LINKS) -> list[GraphEdge]:
    result = await session.run(_q(f"""
        MATCH (a:Entity)-[r:{link_types}]->(b:Entity)
        WHERE a.entity_id IN $ids AND b.entity_id IN $ids
        RETURN elementId(r) AS id, a.entity_id AS source, b.entity_id AS target,
               type(r) AS type, properties(r) AS props
        """), ids=ids)
    return [_edge(r) async for r in result]


async def _with_groups(session: AsyncSession, nodes: list[GraphNode]) -> list[GraphNode]:
    """Nest entities inside their Level 2 groups so the renderer can fold them (NV-2)."""
    ids = [n.id for n in nodes if n.kind == "Entity"]
    result = await session.run(_q("""
        MATCH (e:Entity)-[m:MEMBER_OF]->(g:Group)
        WHERE e.entity_id IN $ids
        RETURN e.entity_id AS entity_id, g.group_id AS group_id, g.group_type AS group_type,
               g.label AS label, m.role AS role
        """), ids=ids)
    parents: dict[str, str] = {}
    groups: dict[str, GraphNode] = {}
    async for r in result:
        parents.setdefault(r["entity_id"], r["group_id"])  # first group wins for nesting
        groups[r["group_id"]] = GraphNode(
            id=r["group_id"], kind="Group", label=r["label"] or r["group_type"],
            data={"group_type": r["group_type"]},
        )
    for n in nodes:
        n.parent = parents.get(n.id)
    return list(groups.values()) + nodes


async def _attribute_layer(
    session: AsyncSession, entity_ids: list[str], focus_id: str, mode: AttributeMode, cap: int
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Attribute values as nodes, each joined to its holders by one edge.

    Joining holders through the value (a star) instead of pairwise SHARES edges (a clique) is
    what keeps a ring of N people at N edges per shared value rather than N*(N-1)/2.
    "shared" keeps values held by two or more visible entities, plus everything the focus
    entity holds; "all" adds every value.
    """
    if mode == "none":
        return [], []
    result = await session.run(_q("""
        MATCH (e:Entity)<-[:RESOLVED_TO]-(:SourceRecord)-[h:HAS_ATTRIBUTE]->(v:AttributeValue)
        WHERE e.entity_id IN $ids
        WITH v, e, min(h.first_seen) AS first_seen, max(h.last_seen) AS last_seen,
             collect(coalesce(h.is_current, false)) AS cur
        WITH v, collect({entity_id: e.entity_id, first_seen: first_seen, last_seen: last_seen,
                         is_current: any(x IN cur WHERE x)}) AS holders
        WITH v, holders, any(x IN holders WHERE x.entity_id = $focus) AS held_by_focus
        WHERE NOT v.attr_type IN $descriptive
          AND ($mode = 'all' OR held_by_focus
               OR (size(holders) > 1 AND v.attr_type IN $linking))
        RETURN properties(v) AS v, holders
        ORDER BY held_by_focus DESC, size(holders) DESC, v.id
        LIMIT $cap
        """), ids=entity_ids, focus=focus_id, mode=mode, linking=_LINKING_ATTRS,
        descriptive=_DESCRIPTIVE_ATTRS, cap=cap)
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    async for r in result:
        v = r["v"]
        nodes.append(GraphNode(
            id=v["id"], kind="AttributeValue", label=v.get("display") or v["id"],
            status="hub" if v.get("is_hub") else None,
            data={"attr_type": v["attr_type"], "holders": len(r["holders"]),
                  "degree": v.get("degree")},
        ))
        for h in r["holders"]:
            edges.append(GraphEdge(
                id=f"{h['entity_id']}|{v['id']}", source=h["entity_id"], target=v["id"],
                type="HAS_ATTRIBUTE", label=v["attr_type"],
                data={"attr_type": v["attr_type"], "first_seen": h["first_seen"],
                      "last_seen": h["last_seen"], "is_current": h["is_current"]},
            ))
    return nodes, edges


async def neighborhood(session: AsyncSession, entity_id: str, hops: int, limit: int,
                       attributes: AttributeMode = "shared") -> GraphResponse | None:
    settings = get_settings()
    hops = max(1, min(int(hops), settings.graph_max_hops))
    limit = max(1, min(int(limit), settings.graph_max_nodes))
    record = await (await session.run(_q(f"""
        MATCH (s:Entity {{entity_id: $id}})
        OPTIONAL MATCH (s)-[:{_LINKS}*1..{hops}]-(n:Entity)
        WHERE n <> s  // a path can leave and return by a second shared value
        WITH s, collect(DISTINCT n) AS ns
        RETURN properties(s) AS start, [x IN ns[..$cap] | properties(x)] AS others,
               size(ns) > $cap AS truncated
        """), id=entity_id, cap=limit - 1)).single()
    if record is None:
        return None
    entities = [_entity_node(record["start"])] + [_entity_node(o) for o in record["others"]]
    ids = [n.id for n in entities]
    # With attribute nodes on the canvas they explain shared-value links, so only supplied
    # relationships (roles, providers) and aliases are drawn entity to entity; otherwise show
    # SHARES too.
    edges = await _edges_between(
        session, ids, "RELATED_TO|ALIAS_OF" if attributes != "none" else _LINKS)
    attr_nodes, attr_edges = await _attribute_layer(session, ids, entity_id, attributes,
                                                    cap=limit * 4)
    nodes = await _with_claim_state(session, await _with_groups(session, entities))
    return GraphResponse(nodes=[*nodes, *attr_nodes], edges=[*edges, *attr_edges],
                         truncated=record["truncated"])


async def shortest_path(session: AsyncSession, source: str, target: str) -> GraphResponse:
    hops = get_settings().graph_max_hops * 2
    record = await (await session.run(_q(f"""
        MATCH (a:Entity {{entity_id: $source}}), (b:Entity {{entity_id: $target}})
        MATCH p = shortestPath((a)-[:{_LINKS}*..{hops}]-(b))
        RETURN [n IN nodes(p) | properties(n)] AS nodes
        """), source=source, target=target)).single()
    if record is None:
        return GraphResponse(nodes=[], edges=[])
    nodes = await _with_claim_state(session, [_entity_node(n) for n in record["nodes"]])
    return GraphResponse(nodes=nodes, edges=await _edges_between(session, [n.id for n in nodes]))


async def entity_records(session: AsyncSession, entity_id: str) -> GraphResponse:
    """Expand an entity into its source records and attribute values (NV-3)."""
    result = await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})<-[x:RESOLVED_TO]-(r:SourceRecord)
        OPTIONAL MATCH (r)-[h:HAS_ATTRIBUTE]->(v:AttributeValue)
        WHERE NOT v.attr_type IN $descriptive
        RETURN r.id AS record_id, r.source_system AS source_system, properties(x) AS resolved,
               collect({value_id: v.id, attr_type: v.attr_type, display: v.display,
                        is_hub: v.is_hub, edge: properties(h), edge_id: elementId(h)}) AS attrs
        """), id=entity_id, descriptive=_DESCRIPTIVE_ATTRS)
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    async for r in result:
        rid = r["record_id"]
        nodes[rid] = GraphNode(id=rid, kind="SourceRecord", label=rid,
                               data={"source_system": r["source_system"], **r["resolved"]})
        edges.append(GraphEdge(id=f"{rid}|{entity_id}", source=rid, target=entity_id,
                               type="RESOLVED_TO", label=r["resolved"].get("method"),
                               data=r["resolved"]))
        for a in r["attrs"]:
            if a["value_id"] is None:
                continue
            nodes.setdefault(a["value_id"], GraphNode(
                id=a["value_id"], kind="AttributeValue", label=a["display"],
                status="hub" if a["is_hub"] else None, data={"attr_type": a["attr_type"]},
            ))
            edges.append(GraphEdge(id=a["edge_id"], source=rid, target=a["value_id"],
                                   type="HAS_ATTRIBUTE", label=a["attr_type"],
                                   data=a["edge"] or {}))
    return GraphResponse(nodes=list(nodes.values()), edges=edges)


async def entity_detail(session: AsyncSession, entity_id: str) -> EntityDetail | None:
    record = await (await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})
        OPTIONAL MATCH (e)<-[:RESOLVED_TO]-(r:SourceRecord)
        WITH e, count(r) AS records
        OPTIONAL MATCH (e)-[m:MEMBER_OF]->(g:Group)
        RETURN properties(e) AS e, records,
               [x IN collect({group_id: g.group_id, group_type: g.group_type, role: m.role})
                WHERE x.group_id IS NOT NULL] AS groups
        """), id=entity_id)).single()
    if record is None:
        return None
    e = record["e"]
    return EntityDetail(
        entity_id=e["entity_id"], entity_type=e["entity_type"],
        canonical_name=e.get("canonical_name"), rule_set_version=e.get("rule_set_version"),
        record_count=record["records"], groups=record["groups"],
    )


async def attribute_versions(session: AsyncSession, entity_id: str) -> list[AttributeVersion]:
    """Every value seen for the entity, with source and validity dates (NV-4)."""
    result = await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})<-[:RESOLVED_TO]-(r:SourceRecord)
              -[h:HAS_ATTRIBUTE]->(v:AttributeValue)
        OPTIONAL MATCH (v)<-[:HAS_ATTRIBUTE]-(:SourceRecord)-[:RESOLVED_TO]->(o:Entity)
        WHERE o <> e
        RETURN v.attr_type AS attr_type, v.id AS value_id, v.display AS display,
               h.source_system AS source_system, r.id AS record_id,
               h.first_seen AS first_seen, h.last_seen AS last_seen,
               coalesce(h.is_current, false) AS is_current, coalesce(v.is_hub, false) AS is_hub,
               CASE WHEN v.attr_type IN $descriptive THEN 0
                    ELSE count(DISTINCT o) END AS shared_with
        ORDER BY attr_type, last_seen DESC
        """), id=entity_id, descriptive=_DESCRIPTIVE_ATTRS)
    return [AttributeVersion(**r.data()) async for r in result]


async def explain(session: AsyncSession, entity_id: str) -> list[MergeExplanation]:
    """Why the entity was formed (ER-6)."""
    result = await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})<-[x:RESOLVED_TO]-(r:SourceRecord)
        RETURN r.id AS record_id, r.source_system AS source_system, x.method AS method,
               x.score AS score, coalesce(x.rules_fired, []) AS rules_fired,
               x.rule_set_version AS rule_set_version
        ORDER BY record_id
        """), id=entity_id)
    return [MergeExplanation(**r.data()) async for r in result]


async def appearances(session: AsyncSession, entity_id: str) -> list[Appearance]:
    """Each source record of the entity with the claims and roles it was filed under."""
    result = await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})<-[:RESOLVED_TO]-(r:SourceRecord)
        CALL (r) {
          OPTIONAL MATCH (r)-[x:REL]-(:SourceRecord)-[:RESOLVED_TO]->
                         (c:Entity {entity_type: 'Claim'})
          RETURN [l IN collect(DISTINCT {claim_id: c.entity_id, claim: c.canonical_name,
                                         role: x.rel_type}) WHERE l.claim_id IS NOT NULL] AS links
        }
        CALL (r) {
          OPTIONAL MATCH (r)-[:HAS_ATTRIBUTE]->(v:AttributeValue)
          RETURN [a IN collect(DISTINCT {attr_type: v.attr_type, display: v.display})
                  WHERE a.attr_type IS NOT NULL] AS attrs
        }
        RETURN r.id AS record_id, r.source_system AS source_system, links, attrs
        ORDER BY record_id
        """), id=entity_id)
    out = []
    async for r in result:
        attrs = r["attrs"]
        out.append(Appearance(
            record_id=r["record_id"], source_system=r["source_system"], links=r["links"],
            name=next((a["display"] for a in attrs if a["attr_type"] == "name"), None),
            attributes=[a for a in attrs if a["attr_type"] not in _DESCRIPTIVE_ATTRS],
        ))
    return out


async def group_members(session: AsyncSession, group_id: str, skip: int,
                        limit: int) -> GraphResponse | None:
    record = await (await session.run(_q("""
        MATCH (g:Group {group_id: $id})
        OPTIONAL MATCH (e:Entity)-[:MEMBER_OF]->(g)
        WITH g, e ORDER BY e.entity_id
        WITH g, collect(properties(e)) AS members
        RETURN properties(g) AS g, members[$skip..$skip + $limit] AS page,
               size(members) > $skip + $limit AS truncated
        """), id=group_id, skip=skip, limit=limit)).single()
    if record is None:
        return None
    g = record["g"]
    group = GraphNode(id=g["group_id"], kind="Group",
                      label=g.get("label") or g.get("group_type", "Group"),
                      data={"group_type": g.get("group_type")})
    nodes = [_entity_node(m, parent=group.id) for m in record["page"]]
    edges = await _edges_between(session, [n.id for n in nodes])
    return GraphResponse(nodes=[group, *nodes], edges=edges, truncated=record["truncated"])


_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def lucene_terms(q: str) -> str:
    """Escape user input for Lucene; longer terms get fuzzy matching for typos.

    Terms are lowercased so AND/OR/NOT are searched as words, never parsed as operators
    (the full-text analyzer lowercases the index anyway)."""
    return " ".join(
        _LUCENE_SPECIAL.sub(r"\\\1", t) + ("~" if len(t) > 3 else "")
        for t in q.lower().split()
    )


async def search(session: AsyncSession, q: str, entity_type: str | None, limit: int,
                 hashed_ids: list[str]) -> list[SearchHit]:
    """Full-text search over names and attribute display values, plus exact lookup of hashed
    identifiers (so a full SSN or account number finds its entity without being stored)."""
    terms = lucene_terms(q)
    result = await session.run(_q("""
        CALL () {
          CALL db.index.fulltext.queryNodes('entity_search', $terms) YIELD node, score
          RETURN node AS e, 'name' AS matched_on, score
          UNION ALL
          CALL db.index.fulltext.queryNodes('attribute_search', $terms) YIELD node, score
          MATCH (node)<-[:HAS_ATTRIBUTE]-(:SourceRecord)-[:RESOLVED_TO]->(e:Entity)
          RETURN e, node.attr_type AS matched_on, score
          UNION ALL
          MATCH (v:AttributeValue)<-[:HAS_ATTRIBUTE]-(:SourceRecord)-[:RESOLVED_TO]->(e:Entity)
          WHERE v.id IN $hashed_ids
          RETURN e, v.attr_type AS matched_on, 100.0 AS score
        }
        WITH e, matched_on, score
        WHERE $etype IS NULL OR e.entity_type = $etype
        WITH e, max(score) AS score, collect(DISTINCT matched_on)[0] AS matched_on
        RETURN e.entity_id AS entity_id, coalesce(e.canonical_name, e.entity_id) AS label,
               e.entity_type AS entity_type, matched_on, score
        ORDER BY score DESC LIMIT $limit
        """), terms=terms or '""', hashed_ids=hashed_ids, etype=entity_type, limit=limit)
    return [SearchHit(**r.data()) async for r in result]


async def leads(session: AsyncSession, entity_type: str | None, limit: int) -> list[Lead]:
    """Most-connected people and companies, counting only links to other people and companies
    (not claims, policies or vehicles). A stand-in for the outlier list, computed on demand;
    Phase 2 replaces it with precomputed cluster scores (GA-4, GA-5), which scale better."""
    result = await session.run(_q(f"""
        MATCH (e:Entity)-[s:{_LINKS}]-(o:Entity)
        WHERE e.entity_type IN $parties AND o.entity_type IN $parties
          AND ($etype IS NULL OR e.entity_type = $etype)
        WITH e, count(DISTINCT o) AS connections,
             collect(DISTINCT coalesce(s.attr_type, s.rel_type)) AS via
        ORDER BY connections DESC, e.entity_id
        LIMIT $limit
        RETURN e.entity_id AS entity_id, coalesce(e.canonical_name, e.entity_id) AS label,
               e.entity_type AS entity_type, connections, via
        """), etype=entity_type, limit=limit, parties=list(PARTY_TYPES))
    return [Lead(**r.data()) async for r in result]


async def overview(session: AsyncSession) -> Overview:
    """Counts across the whole graph: what is in it, how it clusters, and what resolution merged."""
    counts = {r["t"]: r["n"] async for r in await session.run(_q(
        "MATCH (e:Entity) RETURN e.entity_type AS t, count(*) AS n"))}
    resolved = await (await session.run(_q("""
        MATCH (e:Entity {entity_type: 'Person'})
        OPTIONAL MATCH (e)<-[:RESOLVED_TO]-(r:SourceRecord)
        WITH e, count(r) AS k
        RETURN sum(k) AS records, sum(CASE WHEN k > 1 THEN 1 ELSE 0 END) AS merged,
               sum(CASE WHEN k > 1 THEN k ELSE 0 END) AS merged_records
        """))).single()
    _, uf = await _components(session)
    groups = [m for m in uf.members.values() if len(m) >= 2] if uf else []
    return Overview(
        claims=counts.get("Claim", 0), policies=counts.get("Policy", 0),
        people=counts.get("Person", 0),
        companies=sum(n for t, n in counts.items() if t in PARTY_TYPES and t != "Person"),
        groups=len(groups), largest_group=max(map(len, groups), default=0),
        people_records=resolved["records"] or 0, merged_people=resolved["merged"] or 0,
        merged_records=resolved["merged_records"] or 0,
    )


async def _components(session: AsyncSession) -> tuple[list[Any], _UnionFind | None]:
    """Every entity link, and the connected components over them."""
    rows = [r async for r in await session.run(_q(f"""
        MATCH (a:Entity)-[r:{_LINKS}]->(b:Entity)
        RETURN a.entity_id AS a, b.entity_id AS b, type(r) AS type,
               coalesce(r.attr_type, r.rel_type) AS via, r.attr_type AS attr_type,
               r.attr_value_id AS value_id, r.first_seen AS first_seen
        """))]
    if not rows:
        return rows, None
    uf = _UnionFind(sorted({x for r in rows for x in (r["a"], r["b"])}))
    for r in rows:
        uf.union(r["a"], r["b"])
    return rows, uf


async def _score(session: AsyncSession, rows: list[Any], uf: _UnionFind, roots: set[str],
                 rules: list[AnalyticsRuleDocument] | None, with_members: bool) -> list[Network]:
    degree: dict[str, int] = {}
    per_net: dict[str, list[Any]] = {root: [] for root in roots}
    for r in rows:
        root = uf.find(r["a"])
        if root in per_net:
            per_net[root].append(r)
            for x in (r["a"], r["b"]):
                degree[x] = degree.get(x, 0) + 1
    info = {r["id"]: {"type": r["type"], "label": r["label"]} async for r in await session.run(
        _q("""
        MATCH (e:Entity) WHERE e.entity_id IN $ids
        RETURN e.entity_id AS id, e.entity_type AS type,
               coalesce(e.canonical_name, e.entity_id) AS label
        """), ids=[m for root in roots for m in uf.members[root]])}
    out = []
    for root in roots:
        members, edges = uf.members[root], per_net[root]
        alias_pairs = [(r["a"], r["b"]) for r in edges if r["type"] == "ALIAS_OF"]
        score, found = network_insights(
            {m: dict(info[m]) for m in members},
            [{"src": r["a"], "dst": r["b"], "rel_type": r["via"], "first_seen": r["first_seen"]}
             for r in edges if r["type"] == "RELATED_TO"],
            [{"a": r["a"], "b": r["b"], "attr_type": r["attr_type"], "value_id": r["value_id"]}
             for r in edges if r["type"] == "SHARES"],
            alias_pairs, rules,
        )
        types: dict[str, int] = {}
        for m in members:
            types[info[m]["type"]] = types.get(info[m]["type"], 0) + 1
        focus = max(members, key=lambda m: (degree.get(m, 0), m))
        out.append(Network(
            network_id=root, size=len(members), types=types,
            links=sum(1 for r in edges if info[r["a"]]["type"] in PARTY_TYPES
                      and info[r["b"]]["type"] in PARTY_TYPES),
            aliases=len(alias_pairs), focus_id=focus, focus_label=info[focus]["label"],
            via=sorted({r["via"] or "alias" for r in edges}),
            score=score, severity=severity(score), flags=[f.detail for f in found],
            hits=[Hit(rule_id=f.rule_id, title=f.title, severity=f.severity, points=f.points,
                      detail=f.detail, entities=f.entities, condition=f.condition,
                      matches=[HitMatch(kind=m.kind, entities=m.entities, claims=m.claims,  # type: ignore[arg-type]
                                        attr_type=m.attr_type, value_id=m.value_id, note=m.note)
                               for m in f.matches])
                  for f in found],
            members=sorted(members) if with_members else [],
        ))
    await _show_values(session, out)
    return out


async def _show_values(session: AsyncSession, nets: list[Network]) -> None:
    """Fill in how each matched value is shown on the graph (secret values arrive masked)."""
    ids = sorted({m.value_id for n in nets for h in n.hits for m in h.matches if m.value_id})
    if not ids:
        return
    shown = {r["id"]: r["display"] async for r in await session.run(_q("""
        MATCH (v:AttributeValue) WHERE v.id IN $ids
        RETURN v.id AS id, v.display AS display
        """), ids=ids)}
    for n in nets:
        for h in n.hits:
            for m in h.matches:
                if m.value_id:
                    m.value = shown.get(m.value_id)


async def networks(session: AsyncSession, min_size: int, limit: int,
                   rules: list[AnalyticsRuleDocument] | None = None,
                   with_members: bool = False) -> list[Network]:
    """Connected components over every entity link, scored by fraud indicators and ranked by
    score, then size. Hub values create no SHARES links, so a registered-agent address does not
    fuse unrelated rings into one network.

    Computed on demand in memory; precompute it with the Phase 2 analytics run once the graph
    outgrows a few hundred thousand links."""
    rows, uf = await _components(session)
    if uf is None:
        return []
    roots = {root for root, m in uf.members.items() if len(m) >= min_size}
    out = await _score(session, rows, uf, roots, rules, with_members=with_members)
    out.sort(key=lambda n: (-n.score, -n.size, n.network_id))
    return out[:limit]


async def members_of(session: AsyncSession, ids: list[str]) -> list[dict[str, Any]]:
    """The entities of a network with what they are on: how many claims they are tied to, and
    the roles they hold (insured, driver, represents...)."""
    return [r.data() async for r in await session.run(_q("""
        MATCH (e:Entity) WHERE e.entity_id IN $ids
        CALL (e) {
          OPTIONAL MATCH (e)-[:RELATED_TO]-(c:Entity {entity_type: 'Claim'})
          RETURN count(DISTINCT c) AS claims
        }
        CALL (e) {
          OPTIONAL MATCH (e)-[r:RELATED_TO]->(c:Entity {entity_type: 'Claim'})
          RETURN [x IN collect(DISTINCT r.rel_type) WHERE x IS NOT NULL] AS roles
        }
        RETURN e.entity_id AS entity_id, coalesce(e.canonical_name, e.entity_id) AS label,
               e.entity_type AS entity_type, claims, roles
        ORDER BY label
        """), ids=ids)]


_CLAIM_ATTRS = ["loss_date", "fnol_date", "loss_type", "loss_description", "claim_status",
                "claim_amount", "siu_referred", "siu_accepted", "siu_outcome"]


async def claim_amounts(session: AsyncSession) -> dict[str, float]:
    """What each claim in the graph is for, by entity id."""
    out: dict[str, float] = {}
    async for r in await session.run(_q("""
        MATCH (c:Entity {entity_type: 'Claim'})<-[:RESOLVED_TO]-(:SourceRecord)
              -[h:HAS_ATTRIBUTE]->(v:AttributeValue {attr_type: 'claim_amount'})
        WHERE h.is_current
        RETURN c.entity_id AS id, v.normalized AS amount
        """)):
        try:
            out[r["id"]] = float(r["amount"])
        except (TypeError, ValueError):
            continue
    return out


async def claims_of(session: AsyncSession, ids: list[str],
                    limit: int) -> tuple[int, list[dict[str, Any]]]:
    """The claims among the given entities with their details and who is on each, newest loss
    first."""
    claims: dict[str, dict[str, Any]] = {}
    async for r in await session.run(_q("""
        MATCH (c:Entity {entity_type: 'Claim'}) WHERE c.entity_id IN $ids
        OPTIONAL MATCH (c)<-[:RESOLVED_TO]-(:SourceRecord)-[h:HAS_ATTRIBUTE]->(v:AttributeValue)
        WHERE h.is_current AND v.attr_type IN $attrs
        RETURN c.entity_id AS id, coalesce(c.canonical_name, c.entity_id) AS claim,
               v.attr_type AS attr, v.display AS display, v.normalized AS norm
        """), ids=ids, attrs=_CLAIM_ATTRS):
        c = claims.setdefault(r["id"], {
            "entity_id": r["id"], "claim": r["claim"], "loss_date": None, "fnol_date": None,
            "loss_types": [], "description": None, "status": None, "amount": None,
            "siu_referred": False, "siu_accepted": False, "siu_outcome": None, "parties": []})
        match r["attr"]:
            case "loss_date" | "fnol_date":
                c[r["attr"]] = r["display"]
            case "loss_type":
                c["loss_types"].append(r["display"])
            case "loss_description":
                c["description"] = r["display"]
            case "claim_status":
                c["status"] = r["display"]
            case "claim_amount":
                try:
                    c["amount"] = float(r["norm"])
                except (TypeError, ValueError):
                    pass
            case "siu_referred" | "siu_accepted":
                c[r["attr"]] = str(r["display"]).strip().casefold() == "yes"
            case "siu_outcome":
                c["siu_outcome"] = r["display"]
    async for r in await session.run(_q("""
        MATCH (p:Entity)-[r:RELATED_TO]->(c:Entity {entity_type: 'Claim'})
        WHERE c.entity_id IN $ids
        RETURN c.entity_id AS claim, p.entity_id AS id,
               coalesce(p.canonical_name, p.entity_id) AS label, p.entity_type AS type,
               r.rel_type AS role
        ORDER BY label
        """), ids=ids):
        claims[r["claim"]]["parties"].append({
            "entity_id": r["id"], "label": r["label"], "entity_type": r["type"],
            "role": r["role"]})
    rows = sorted(claims.values(), key=lambda c: (c["loss_date"] or "", c["claim"]), reverse=True)
    return len(rows), rows[:limit]


async def entity_network(session: AsyncSession, entity_id: str,
                         rules: list[AnalyticsRuleDocument] | None = None) -> Network | None:
    """The network the entity belongs to, scored on its own. An entity with no links is a
    network of one with no indicators; an unknown entity is None."""
    rows, uf = await _components(session)
    if uf is not None and entity_id in uf.parent:
        return (await _score(session, rows, uf, {uf.find(entity_id)}, rules, True))[0]
    record = await (await session.run(_q("""
        MATCH (e:Entity {entity_id: $id})
        RETURN coalesce(e.canonical_name, e.entity_id) AS label, e.entity_type AS type
        """), id=entity_id)).single()
    if record is None:
        return None
    return Network(network_id=entity_id, size=1, links=0, types={record["type"]: 1}, aliases=0,
                   focus_id=entity_id, focus_label=record["label"], via=[], score=0,
                   severity="low", flags=[], hits=[], members=[entity_id])


async def rule_preview(session: AsyncSession, rule: AnalyticsRuleDocument,
                       limit: int = 8) -> RulePreview:
    """Run one rule over every network of three or more entities and report where it fires."""
    rows, uf = await _components(session)
    if uf is None:
        return RulePreview(networks_checked=0, networks_hit=0, examples=[])
    roots = {root for root, m in uf.members.items() if len(m) >= 3}
    hits = []
    for n in await _score(session, rows, uf, roots, [rule], False):
        mine = [h for h in n.hits if h.rule_id == rule.rule_id]
        hits += [(h.points, n, h) for h in mine[:1]]
    hits.sort(key=lambda t: (-t[1].size, t[1].network_id))
    return RulePreview(
        networks_checked=len(roots), networks_hit=len(hits),
        examples=[RulePreviewHit(network_id=n.network_id, focus_id=n.focus_id,
                                 focus_label=n.focus_label, size=n.size, detail=h.detail)
                  for _, n, h in hits[:limit]])
