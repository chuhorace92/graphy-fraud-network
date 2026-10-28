from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from graphy.api.deps import Graph, Pg, Reader
from graphy.catalog import EntityType
from graphy.schemas.graph import GraphResponse, Lead, Network, Overview
from graphy.services import graph_queries
from graphy.services.analytics_rules import published_rules

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/neighborhood", response_model=GraphResponse)
async def neighborhood(
    graph: Graph,
    _: Reader,
    id: str = Query(min_length=1),
    hops: int = Query(1, ge=1, le=6),
    limit: int = Query(500, ge=1, le=5_000),
    attributes: Literal["shared", "all", "none"] = "shared",
) -> GraphResponse:
    """N-hop subgraph around an entity; server caps hops and nodes (NV-6, NV-8, GA-10).

    `limit` counts entities; attribute nodes come on top (see `attributes`)."""
    result = await graph_queries.neighborhood(graph, id, hops, limit, attributes)
    if result is None:
        raise HTTPException(404, "Entity not found")
    return result


@router.get("/path", response_model=GraphResponse)
async def path(graph: Graph, _: Reader, from_: str = Query(alias="from"),
               to: str = Query()) -> GraphResponse:
    return await graph_queries.shortest_path(graph, from_, to)


@router.get("/entities/{entity_id}/records", response_model=GraphResponse)
async def entity_records(entity_id: str, graph: Graph, _: Reader) -> GraphResponse:
    """Drill from an entity to its source records and attribute values (NV-3)."""
    return await graph_queries.entity_records(graph, entity_id)


@router.get("/overview", response_model=Overview)
async def overview(graph: Graph, _: Reader) -> Overview:
    """Whole-database counts for the Investigate landing page."""
    return await graph_queries.overview(graph)


@router.get("/leads", response_model=list[Lead])
async def leads(
    graph: Graph, _: Reader,
    type: EntityType | None = None,
    limit: int = Query(8, ge=1, le=50),
) -> list[Lead]:
    """Most-connected entities: where to start when there is no alert to follow yet."""
    return await graph_queries.leads(graph, type, limit)


@router.get("/networks", response_model=list[Network])
async def networks(
    graph: Graph, pg: Pg, _: Reader,
    min_size: int = Query(3, ge=2, le=1_000),
    limit: int = Query(10, ge=1, le=50),
) -> list[Network]:
    """Connected networks ranked by size: the biggest rings, with aliases and providers counted."""
    return await graph_queries.networks(graph, min_size, limit, await published_rules(pg))


@router.get("/entities/{entity_id}/network", response_model=Network)
async def entity_network(entity_id: str, graph: Graph, pg: Pg, _: Reader) -> Network:
    """The network this entity belongs to, with the analytics indicators that fired on it."""
    result = await graph_queries.entity_network(graph, entity_id, await published_rules(pg))
    if result is None:
        raise HTTPException(404, "Entity not found")
    return result
