from fastapi import APIRouter, HTTPException, Query

from graphy.api.deps import Graph, Reader
from graphy.schemas.graph import (
    Appearance,
    AttributeVersion,
    EntityDetail,
    GraphResponse,
    MergeExplanation,
)
from graphy.services import graph_queries

router = APIRouter(tags=["entities"])


@router.get("/entities/{entity_id}", response_model=EntityDetail)
async def get_entity(entity_id: str, graph: Graph, _: Reader) -> EntityDetail:
    entity = await graph_queries.entity_detail(graph, entity_id)
    if entity is None:
        raise HTTPException(404, "Entity not found")
    return entity


@router.get("/entities/{entity_id}/attributes", response_model=list[AttributeVersion])
async def get_attributes(entity_id: str, graph: Graph, _: Reader) -> list[AttributeVersion]:
    """Attribute versions: every value, source and first/last seen date (NV-4)."""
    return await graph_queries.attribute_versions(graph, entity_id)


@router.get("/entities/{entity_id}/explain", response_model=list[MergeExplanation])
async def explain(entity_id: str, graph: Graph, _: Reader) -> list[MergeExplanation]:
    """Why these records were merged (ER-6)."""
    return await graph_queries.explain(graph, entity_id)


@router.get("/entities/{entity_id}/appearances", response_model=list[Appearance])
async def get_appearances(entity_id: str, graph: Graph, _: Reader) -> list[Appearance]:
    """Every record of the entity, with the claim and role it was filed under."""
    return await graph_queries.appearances(graph, entity_id)


@router.get("/groups/{group_id}", response_model=GraphResponse)
async def get_group(group_id: str, graph: Graph, _: Reader) -> GraphResponse:
    group = await graph_queries.group_members(graph, group_id, 0, 0)
    if group is None:
        raise HTTPException(404, "Group not found")
    return group


@router.get("/groups/{group_id}/members", response_model=GraphResponse)
async def get_group_members(
    group_id: str, graph: Graph, _: Reader,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> GraphResponse:
    group = await graph_queries.group_members(graph, group_id, skip, limit)
    if group is None:
        raise HTTPException(404, "Group not found")
    return group
