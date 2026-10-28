from fastapi import APIRouter, Query

from graphy.api.deps import Graph, Pg, Reader
from graphy.catalog import DEFAULT_CATALOG, EntityType
from graphy.config import get_settings
from graphy.ingestion.normalize import NormalizationError, normalize
from graphy.schemas.graph import SearchHit
from graphy.services import audit, graph_queries

router = APIRouter(tags=["search"])


def _hashed_candidates(q: str) -> list[str]:
    """Secret identifiers are stored only as keyed hashes, so hash the query the same way."""
    ids = []
    for defn in DEFAULT_CATALOG.values():
        if defn.sensitivity != "secret":
            continue
        try:
            ids.append(normalize(defn, q, get_settings().hash_key).value_id)
        except NormalizationError:
            pass
    return ids


@router.get("/search", response_model=list[SearchHit])
async def search(
    graph: Graph, pg: Pg, user: Reader,
    q: str = Query(min_length=2, max_length=200),
    type: EntityType | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> list[SearchHit]:
    hits = await graph_queries.search(graph, q, type, limit, _hashed_candidates(q))
    # Searches on individuals are audited (X-5). The query itself may be an SSN, so only its
    # length and the result ids are kept.
    await audit.record(pg, user, "search", "entity", None,
                       after={"q_len": len(q), "type": type,
                              "results": [h.entity_id for h in hits]})
    await pg.commit()
    return hits
