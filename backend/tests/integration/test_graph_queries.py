"""Graph queries against a real Neo4j that has been seeded (make seed / the CI integration job).

Skipped unless GRAPHY_INTEGRATION=1, because the unit suite must run with no databases.
"""

import os

import pytest
from neo4j import AsyncGraphDatabase

from graphy.config import get_settings
from graphy.services import graph_queries

pytestmark = pytest.mark.skipif(
    os.environ.get("GRAPHY_INTEGRATION") != "1",
    reason="needs a seeded Neo4j (GRAPHY_INTEGRATION=1)",
)


@pytest.fixture
async def session():
    s = get_settings()
    driver = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    async with driver.session(database=s.neo4j_database) as session:
        yield session
    await driver.close()


async def _busiest(session) -> str:
    leads = await graph_queries.leads(session, None, 1)
    assert leads, "no entities: seed the database first"
    return leads[0].entity_id


@pytest.mark.parametrize("mode", ["shared", "all", "none"])
async def test_neighborhood_is_well_formed(session, mode) -> None:
    root = await _busiest(session)
    g = await graph_queries.neighborhood(session, root, hops=2, limit=500, attributes=mode)
    assert g is not None
    ids = [n.id for n in g.nodes]
    assert len(ids) == len(set(ids)), "a node was returned twice"
    edge_ids = [e.id for e in g.edges]
    assert len(edge_ids) == len(set(edge_ids)), "an edge was returned twice"
    known = set(ids)
    assert all(e.source in known and e.target in known for e in g.edges), "dangling edge"
    assert root in known


async def test_attribute_nodes_replace_pairwise_links(session) -> None:
    """The reason attribute nodes exist: N holders cost N edges, not N*(N-1)/2."""
    root = await _busiest(session)
    plain = await graph_queries.neighborhood(session, root, 2, 500, "none")
    starred = await graph_queries.neighborhood(session, root, 2, 500, "shared")
    assert plain and starred
    assert len(starred.edges) < len(plain.edges)


async def test_leads_are_ranked(session) -> None:
    leads = await graph_queries.leads(session, None, 5)
    counts = [lead.connections for lead in leads]
    assert counts == sorted(counts, reverse=True)


async def test_networks_are_ranked_and_typed(session) -> None:
    nets = await graph_queries.networks(session, min_size=3, limit=10)
    assert nets, "no networks: seed the database first"
    assert [n.score for n in nets] == sorted((n.score for n in nets), reverse=True)
    assert all(sum(n.types.values()) == n.size for n in nets)
    # The seed plants staged-accident rings: claims, providers and aliases in one network.
    top = nets[0]
    assert {"Person", "Claim"} <= set(top.types) and top.aliases > 0
    assert top.severity == "high" and top.flags


async def test_roles_and_aliases_reach_the_canvas(session) -> None:
    net = (await graph_queries.networks(session, 3, 1))[0]
    g = await graph_queries.neighborhood(session, net.focus_id, hops=2, limit=500)
    assert g is not None
    kinds = {e.type for e in g.edges}
    assert "RELATED_TO" in kinds
    roles = {e.label for e in g.edges if e.type == "RELATED_TO"}
    assert roles & {"witness", "passenger", "driver", "claimant", "insured"}


async def test_entity_network_lists_the_hits_behind_the_score(session) -> None:
    top = (await graph_queries.networks(session, 3, 1))[0]
    net = await graph_queries.entity_network(session, top.focus_id)
    assert net is not None and net.score == top.score
    assert {h.rule_id for h in net.hits} >= {"medical-and-legal-on-three-claims"}
    assert top.focus_id in net.members and all(h.entities for h in net.hits)
    assert await graph_queries.entity_network(session, "E-does-not-exist") is None


async def test_names_and_claim_details_are_not_canvas_nodes(session) -> None:
    from graphy.catalog import DEFAULT_CATALOG

    descriptive = {k for k, d in DEFAULT_CATALOG.items() if d.descriptive}
    focus = (await graph_queries.networks(session, 3, 1))[0].focus_id
    g = await graph_queries.neighborhood(session, focus, hops=2, limit=500, attributes="all")
    assert g is not None
    shown = {n.data.get("attr_type") for n in g.nodes if n.kind == "AttributeValue"}
    assert shown and not shown & descriptive
    claims = [n.id for n in g.nodes if n.entity_type == "Claim"]
    assert claims, "the top network should include claims"
    versions = await graph_queries.attribute_versions(session, claims[0])
    assert {v.attr_type for v in versions} >= {"loss_date", "loss_type", "name"}
    assert all(v.shared_with == 0 for v in versions if v.attr_type in descriptive)


async def test_appearances_list_each_record_with_its_claim_and_role(session) -> None:
    root = await _busiest(session)
    rows = await graph_queries.appearances(session, root)
    assert rows
    assert len({r.record_id for r in rows}) == len(rows)
    assert any(r.name for r in rows)
    assert all("name" not in {a.attr_type for a in r.attributes} for r in rows)


async def test_leads_are_people_and_companies(session) -> None:
    from graphy.catalog import PARTY_TYPES

    leads = await graph_queries.leads(session, None, 25)
    assert leads
    assert all(lead.entity_type in PARTY_TYPES and lead.connections >= 1 for lead in leads)


async def test_overview_counts_are_consistent(session) -> None:
    o = await graph_queries.overview(session)
    assert o.people > 0 and o.groups > 0
    assert o.largest_group >= 2
    assert o.merged_people <= o.people
    assert o.merged_records >= 2 * o.merged_people
    assert o.people_records >= o.people
